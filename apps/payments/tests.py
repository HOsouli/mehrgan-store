from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
import requests
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework import status
from apps.accounts.models import CustomUser
from apps.orders.models import Order, OrderAddress
from apps.payments.models import Payment
from apps.payments.services import ZibalService
from apps.payments.tasks import reverify_pending_payments
from apps.invoices.models import Invoice
from apps.shipments.models import Shipment
from django.test import override_settings


@override_settings(ZIBAL_MERCHANT_ID="test-merchant")
class RequestPaymentTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(phone_number="09123456789")
        self.order = Order.objects.create(
            user=self.user,
            subtotal=Decimal(100000),
            discount_amount=Decimal(0),
            shipping_amount=Decimal(0),
            total_amount=Decimal(100000),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        OrderAddress.objects.create(
            order=self.order,
            first_name="Test",
            last_name="User",
            province="تهران",
            city="تهران",
            address="آدرس آزمایشی",
            postal_code="1234567890",
            recipient_phone="09123456789",
        )

    @patch("apps.payments.services.settings.ZIBAL_MERCHANT_ID", "test-merchant")
    @patch("apps.payments.services.requests.post")
    def test_successful_request_creates_pending_payment(self, post):
        post.return_value.json.return_value = {
            "result": 100,
            "trackId": 12345,
            "message": "Success",
        }
        payment, pay_url = ZibalService.request_payment(self.order)
        self.assertEqual(payment.status, Payment.PaymentStatus.PENDING)
        self.assertEqual(payment.gateway, "zibal")
        self.assertEqual(payment.transaction_id, "12345")
        self.assertEqual(payment.amount, self.order.total_amount)
        self.assertEqual(pay_url, "https://gateway.zibal.ir/start/12345")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["merchant"], "test-merchant")
        self.assertEqual(payload["amount"], 1000000)
        self.assertEqual(payload["orderId"], str(payment.pk))
        self.assertIn("payment_id=", payload["callbackUrl"])

    @patch("apps.payments.services.settings.ZIBAL_MERCHANT_ID", "test-merchant")
    @patch("apps.payments.services.requests.post")
    def test_existing_pending_payment_reuses_transaction(self, post):
        payment = Payment.objects.create(
            order=self.order,
            amount=self.order.total_amount,
            gateway="zibal",
            status=Payment.PaymentStatus.PENDING,
            transaction_id="12345",
        )
        result, pay_url = ZibalService.request_payment(self.order)
        self.assertEqual(result.pk, payment.pk)
        self.assertEqual(pay_url, "https://gateway.zibal.ir/start/12345")
        post.assert_not_called()

    @patch("apps.payments.services.requests.post", side_effect=requests.exceptions.Timeout)
    def test_network_error_keeps_payment_pending(self, post):
        with self.assertRaises(ValidationError):
            ZibalService.request_payment(self.order)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.PaymentStatus.PENDING)
        self.assertEqual(payment.gateway, "zibal")
        self.assertFalse(payment.transaction_id)
        self.assertTrue(payment.gateway_response_message)

    @patch("apps.payments.services.settings.ZIBAL_MERCHANT_ID", "test-merchant")
    @patch("apps.payments.services.requests.post")
    def test_successful_gateway_response_without_track_id_fails_safely(self, post):
        post.return_value.json.return_value = {"result": 100, "message": "Success"}
        with self.assertRaises(ValidationError):
            ZibalService.request_payment(self.order)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.PaymentStatus.PENDING)
        self.assertEqual(payment.gateway_response_code, "100")
        self.assertFalse(payment.transaction_id)
    @patch("apps.payments.services.settings.ZIBAL_MERCHANT_ID", "test-merchant")
    @patch("apps.payments.services.requests.post")
    def test_gateway_rejection_marks_payment_failed(self, post):
        post.return_value.json.return_value = {"result": 102, "message": "Invalid merchant"}
        with self.assertRaises(ValidationError):
            ZibalService.request_payment(self.order)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.PaymentStatus.FAILED)
        self.assertEqual(payment.gateway, "zibal")
        self.assertEqual(payment.gateway_response_code, "102")


@override_settings(ZIBAL_MERCHANT_ID="test-merchant")
class VerifyPaymentDatabaseTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(phone_number="09123456789")
        self.order = Order.objects.create(
            user=self.user,
            status=Order.OrderStatus.PROCESSING,
            subtotal=100000,
            discount_amount=0,
            shipping_amount=0,
            total_amount=100000,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            amount=100000,
            gateway="zibal",
            status=Payment.PaymentStatus.SUCCESS,
            transaction_id="123456",
            tracking_code="123456789",
            paid_at=timezone.now(),
        )

    def test_repeated_successful_verification_does_not_duplicate_invoice_or_shipment(self):
        service = ZibalService()
        service.verify_payment(self.payment.pk, self.payment.transaction_id)
        service.verify_payment(self.payment.pk, self.payment.transaction_id)
        self.assertEqual(Invoice.objects.filter(order=self.order).count(), 1)
        self.assertEqual(Shipment.objects.filter(order=self.order).count(), 1)

    @patch("apps.payments.services.requests.post")
    def test_successful_payment_for_cancelled_order_does_not_reactivate_order(self, post):
        self.order.status = Order.OrderStatus.CANCELLED
        self.order.save(update_fields=["status", "updated_at"])
        self.payment.status = Payment.PaymentStatus.PENDING
        self.payment.save(update_fields=["status", "updated_at"])
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_CANCELLED_123",
            "message": "Success",
        }
        result = ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(result.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.order.status, Order.OrderStatus.CANCELLED)
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())
        self.assertFalse(Shipment.objects.filter(order=self.order).exists())

    @patch("apps.payments.services.requests.post")
    def test_late_success_after_payment_cancelled_does_not_reactivate_order(self, post):
        self.order.status = Order.OrderStatus.CANCELLED
        self.order.save(update_fields=["status", "updated_at"])
        self.payment.status = Payment.PaymentStatus.CANCELLED
        self.payment.save(update_fields=["status", "updated_at"])
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_LATE_SUCCESS_123",
            "message": "Success",
        }
        ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.order.status, Order.OrderStatus.CANCELLED)
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())
        self.assertFalse(Shipment.objects.filter(order=self.order).exists())

    @patch("apps.payments.services.requests.post")
    def test_invalid_gateway_response_marks_payment_for_review(self, post):
        self.payment.status = Payment.PaymentStatus.PENDING
        self.payment.gateway_response_code = ""
        self.payment.save(update_fields=["status", "gateway_response_code", "updated_at"])
        post.return_value.json.return_value = {}
        with self.assertRaises(ValidationError):
            ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.assertEqual(self.payment.gateway_response_code, "invalid_response")

    @patch("apps.payments.services.requests.post")
    def test_reverify_task_retries_pending_payment(self, post):
        self.payment.status = Payment.PaymentStatus.PENDING
        self.payment.gateway_response_code = "net"
        self.payment.save(update_fields=["status", "gateway_response_code", "updated_at"])
        Payment.objects.filter(pk=self.payment.pk).update(updated_at=timezone.now() - timedelta(minutes=6))
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_RETRY_123",
            "message": "Success",
        }
        checked = reverify_pending_payments()
        self.payment.refresh_from_db()
        self.assertEqual(checked, 1)
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.payment.tracking_code, "REF_RETRY_123")


@override_settings(ZIBAL_MERCHANT_ID="test-merchant")
class VerifyPaymentFailureAfterTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(phone_number="09123456789")
        self.order = Order.objects.create(
            user=self.user,
            subtotal=100000,
            discount_amount=0,
            shipping_amount=0,
            total_amount=100000,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            amount=100000,
            gateway="zibal",
            status=Payment.PaymentStatus.PENDING,
            transaction_id="123456789",
        )

    def age_payment(self, minutes):
        created_at = timezone.now() - timedelta(minutes=minutes)
        Payment.objects.filter(pk=self.payment.pk).update(created_at=created_at)

    @patch("apps.payments.services.requests.post")
    def test_result_202_with_inquiry_status_minus_one_keeps_payment_pending(self, mock_post):
        verify_response = {"result": 202, "message": "Not paid"}
        inquiry_response = {
            "result": 100,
            "status": -1,
            "message": "Waiting for payment",
        }
        mock_post.side_effect = [MagicMock(status_code=200, json=lambda: verify_response), MagicMock(
            status_code=200, json=lambda: inquiry_response
            )
        ]
        ZibalService.verify_payment(self.payment.id, self.payment.transaction_id)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)

    @patch("apps.payments.services.requests.post")
    def test_result_202_with_inquiry_status_three_marks_payment_failed(self, mock_post):
        verify_response = {"result": 202, "message": "Not paid"}
        inquiry_response = {
            "result": 100,
            "status": 3,
            "message": "User cancelled",
        }
        mock_post.side_effect = [MagicMock(status_code=200, json=lambda: verify_response), MagicMock(
            status_code=200, json=lambda: inquiry_response
            )
        ]
        ZibalService.verify_payment(self.payment.id, self.payment.transaction_id)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.FAILED)

    @patch("apps.payments.services.requests.post")
    def test_inquiry_statuses_7_to_12_do_not_fail_pending_payment(self, post):
        for inquiry_status in range(7, 13):
            with self.subTest(inquiry_status=inquiry_status):
                Payment.objects.filter(pk=self.payment.pk).update(status=Payment.PaymentStatus.PENDING, gateway_response_code="")
                post.side_effect = [
                    MagicMock(status_code=200, json=lambda: {"result": 202, "message": "Not paid"}),
                    MagicMock(status_code=200, json=lambda s=inquiry_status: {"result": 100,"status": s,"message": "Inquiry status"}),
                ]
                ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
                self.payment.refresh_from_db()
                self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
                self.assertEqual(self.payment.gateway_response_code, f"s{inquiry_status}")

    @patch("apps.payments.services.requests.post")
    def test_inquiry_statuses_7_to_12_do_not_change_cancelled_payment(self, post):
        for inquiry_status in range(7, 13):
            with self.subTest(inquiry_status=inquiry_status):
                Payment.objects.filter(pk=self.payment.pk).update(
                    status=Payment.PaymentStatus.CANCELLED,
                    gateway_response_code="",
                )
                post.side_effect = [
                    MagicMock(status_code=200, json=lambda: {"result": 202, "message": "Not paid"},),
                    MagicMock(status_code=200, json=lambda s=inquiry_status: {"result": 100, "status": s, "message": "Inquiry status"},),
                ]
                ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
                self.payment.refresh_from_db()
                self.assertEqual(self.payment.status, Payment.PaymentStatus.CANCELLED)
                self.assertEqual(self.payment.gateway_response_code, f"s{inquiry_status}")

    @patch("apps.payments.services.requests.post")
    def test_result_201_is_preserved_when_inquiry_network_fails(self, post):
        post.side_effect = [
            MagicMock(status_code=200, json=lambda: {"result": 201, "message": "Already verified"}),
            requests.exceptions.ConnectionError("Inquiry connection failed"),
        ]
        with self.assertRaises(ValidationError):
            ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.gateway_response_code, "201")
        self.assertEqual(self.payment.status,Payment.PaymentStatus.PENDING)

    @patch("apps.payments.services.requests.post")
    def test_result_202_does_not_change_cancelled_payment(self, post):
        Payment.objects.filter(pk=self.payment.pk).update(status=Payment.PaymentStatus.CANCELLED)
        post.side_effect = [
            MagicMock(status_code=200, json=lambda: {"result": 202, "message": "Not paid"}),
            MagicMock(status_code=200, json=lambda: {"result": 100, "status": -1, "message": "Waiting"}),
        ]
        result = ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
        self.assertEqual(result.status, Payment.PaymentStatus.CANCELLED)
        self.assertEqual(result.gateway_response_code, "s-1")

    @patch("apps.payments.services.requests.post")
    def test_result_202_with_inquiry_status_two_keeps_payment_pending(self, post):
        post.side_effect = [
            MagicMock(status_code=200, json=lambda: {"result": 202, "message": "Not paid"}),
            MagicMock(status_code=200, json=lambda: {"result": 100, "status": 2, "message": "Paid but unconfirmed"}),
        ]
        ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.assertEqual(self.payment.gateway_response_code, "s2")

    @patch("apps.payments.services.requests.post")
    def test_inquiry_refund_and_reversal_statuses_require_review(self, post):
        for inquiry_status in (15, 16, 18):
            with self.subTest(inquiry_status=inquiry_status):
                Payment.objects.filter(pk=self.payment.pk).update(status=Payment.PaymentStatus.PENDING, gateway_response_code="")
                post.side_effect = [
                    MagicMock(status_code=200, json=lambda: {"result": 202, "message": "Not paid"}),
                    MagicMock(status_code=200, json=lambda s=inquiry_status: {"result": 100, "status": s, "message": "Inquiry status"}),
                ]
                ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
                self.payment.refresh_from_db()
                self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
                self.assertEqual(self.payment.gateway_response_code, f"s{inquiry_status}")

    @patch("apps.payments.services.requests.post")
    def test_inquiry_status_21_keeps_payment_pending(self, post):
        post.side_effect = [
            MagicMock(status_code=200, json=lambda: {"result": 202, "message": "Not paid"}),
            MagicMock(status_code=200, json=lambda: {"result": 100, "status": 21, "message": "Invalid merchant"},),
        ]
        ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id,)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.assertEqual(self.payment.gateway_response_code, "s21")

    @patch("apps.payments.services.requests.post")
    def test_result_201_with_inquiry_status_one_confirms_payment(self, post):
        post.side_effect = [
            MagicMock(status_code=200, json=lambda: {"result": 201, "message": "Already verified",}),
            MagicMock(
                status_code=200,
                json=lambda: {
                    "result": 100,
                    "status": 1,
                    "amount": 1000000,
                    "orderId": str(self.payment.pk),
                    "paidAt": timezone.now().isoformat(),
                    "refNumber": "REF_201_SUCCESS",
                    "message": "Success",
                },
            ),
        ]
        result = ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(result.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.payment.tracking_code, "REF_201_SUCCESS")
        self.assertEqual(self.order.status, Order.OrderStatus.PROCESSING)
        self.assertTrue(Invoice.objects.filter(order=self.order).exists())
        self.assertTrue(Shipment.objects.filter(order=self.order).exists())


    @patch("apps.payments.services.requests.post")
    def test_invalid_payment_details_require_review(self, post):
        invalid_responses = [
            {
                "amount": 999999,
                "orderId": str(self.payment.pk),
                "refNumber": "REF_INVALID_AMOUNT",
            },
            {
                "amount": 1000000,
                "orderId": "WRONG_ORDER",
                "refNumber": "REF_INVALID_ORDER",
            },
            {
                "amount": 1000000,
                "orderId": str(self.payment.pk),
                "refNumber": "",
            },
        ]

        for details in invalid_responses:
            with self.subTest(details=details):
                post.return_value = MagicMock(
                    status_code=200,
                    json=lambda: {
                        "result": 100,
                        "status": 1,
                        "amount": details["amount"],
                        "orderId": details["orderId"],
                        "paidAt": timezone.now().isoformat(),
                        "refNumber": details["refNumber"],
                        "message": "Success",
                    },
                )

                with self.assertRaises(ValidationError):
                    ZibalService.verify_payment(
                        self.payment.pk,
                        self.payment.transaction_id,
                    )

                self.payment.refresh_from_db()
                self.assertEqual(
                    self.payment.status,
                    Payment.PaymentStatus.PENDING,
                )
                self.assertFalse(Invoice.objects.filter(order=self.order).exists())
                self.assertFalse(Shipment.objects.filter(order=self.order).exists())

    @patch("apps.payments.services.requests.post")
    def test_invalid_paid_at_requires_review(self, post):
        post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "result": 100,
                "status": 1,
                "amount": 1000000,
                "orderId": str(self.payment.pk),
                "paidAt": "invalid-date",
                "refNumber": "REF_INVALID_DATE",
                "message": "Success",
            },
        )
        with self.assertRaises(ValidationError):
            ZibalService.verify_payment(self.payment.pk, self.payment.transaction_id)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())
        self.assertFalse(Shipment.objects.filter(order=self.order).exists())


class PaymentViewsTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(phone_number="09123456789")
        self.client.force_authenticate(user=self.user)
        self.request_url = reverse("payments:request")
        self.callback_url = reverse("payments:callback")

    def create_successful_payment(self, order_status, suffix):
        order = Order.objects.create(
            user=self.user,
            status=order_status,
            subtotal=100000,
            discount_amount=0,
            shipping_amount=0,
            total_amount=100000,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        return Payment.objects.create(
            order=order,
            amount=100000,
            gateway="zibal",
            status=Payment.PaymentStatus.SUCCESS,
            transaction_id=f"123456{Payment.objects.count() + 1}",
            tracking_code=f"REF_STATUS_{suffix}",
            paid_at=timezone.now(),
        )

    def test_payment_status_returns_owned_payment_details(self):
        payment = self.create_successful_payment(Order.OrderStatus.PROCESSING, "OWNER")
        url = reverse("payments:status", kwargs={"payment_id": payment.pk})
        response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["payment_id"], str(payment.pk))
        self.assertEqual(response.data["order_id"], str(payment.order_id))
        self.assertEqual(response.data["tracking_code"], payment.tracking_code)

    def test_payment_status_hides_another_users_payment(self):
        payment = self.create_successful_payment(Order.OrderStatus.PROCESSING, "OTHER")
        other_user = CustomUser.objects.create_user(phone_number="09123456780")
        self.client.force_authenticate(user=other_user)
        url = reverse("payments:status", kwargs={"payment_id": payment.pk})
        response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_payment_status_requires_authentication(self):
        payment = self.create_successful_payment(Order.OrderStatus.PROCESSING, "AUTH")
        self.client.force_authenticate(user=None)
        url = reverse("payments:status", kwargs={"payment_id": payment.pk})
        response = self.client.get(url, secure=True)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_payment_status_accepts_normal_post_payment_order_states(self):
        for order_status in (
            Order.OrderStatus.PROCESSING,
            Order.OrderStatus.SHIPPED,
            Order.OrderStatus.DELIVERED,
        ):
            with self.subTest(order_status=order_status):
                payment = self.create_successful_payment(order_status, order_status)
                url = reverse("payments:status", kwargs={"payment_id": payment.pk})
                response = self.client.get(url, secure=True)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["status"], "success")

    def test_payment_status_marks_cancelled_or_pending_order_for_review(self):
        for order_status in (Order.OrderStatus.PENDING, Order.OrderStatus.CANCELLED):
            with self.subTest(order_status=order_status):
                payment = self.create_successful_payment(order_status, f"REVIEW_{order_status}")
                url = reverse("payments:status", kwargs={"payment_id": payment.pk})
                response = self.client.get(url, secure=True)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["status"], "review")

    def test_payment_request_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.request_url,
            {"order_id": "00000000-0000-0000-0000-000000000001"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_payment_callback_with_invalid_payment_id_redirects_to_failure(self):
        response = self.client.get(
            self.callback_url,
            {"payment_id": "invalid", "trackId": "123456", "Status": "OK"},
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("status=failed", response.url)

    def test_payment_callback_without_track_id_redirects_to_pending(self):
        order = Order.objects.create(
            user=self.user,
            subtotal=100000,
            discount_amount=0,
            shipping_amount=0,
            total_amount=100000,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        payment = Payment.objects.create(
            order=order,
            amount=100000,
            gateway="zibal",
            status=Payment.PaymentStatus.PENDING,
        )
        with patch("apps.payments.views.ZibalService.verify_payment") as verify_payment:
            response = self.client.get(
                self.callback_url,
                {
                    "payment_id": str(payment.pk),
                    "orderId": str(payment.pk),
                },
                secure=True,
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("status=pending", response.url)
        self.assertIn(f"payment_id={payment.pk}", response.url)
        verify_payment.assert_not_called()

    def test_payment_request_rejects_another_users_order(self):
        other_user = CustomUser.objects.create_user(phone_number="09123456780")
        order = Order.objects.create(
            user=other_user,
            subtotal=Decimal(100000),
            discount_amount=Decimal(0),
            shipping_amount=Decimal(0),
            total_amount=Decimal(100000),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        response = self.client.post(
            self.request_url,
            {"order_id": str(order.pk)},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("apps.payments.views.ZibalService.verify_payment")
    def test_payment_callback_failed_verification_redirects_to_failure(self, verify_payment):
        order = Order.objects.create(
            user=self.user,
            subtotal=100000,
            discount_amount=0,
            shipping_amount=0,
            total_amount=100000,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        payment = Payment.objects.create(
            order=order,
            amount=100000,
            gateway="zibal",
            status=Payment.PaymentStatus.FAILED,
            transaction_id="123456789",
        )
        verify_payment.return_value = payment
        response = self.client.get(
            self.callback_url,
            {
                "payment_id": str(payment.pk),
                "orderId": str(payment.pk),
                "trackId": "123456789",
                "Status": "OK",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("status=failed", response.url)
        verify_payment.assert_called_once_with(payment_id=payment.pk, track_id="123456789")


@override_settings(ZIBAL_MERCHANT_ID="test-merchant")
class PaymentRecoveryTaskTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(phone_number="09123456789")
        self.order = Order.objects.create(
            user=self.user,
            subtotal=100000,
            discount_amount=0,
            shipping_amount=0,
            total_amount=100000,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            amount=100000,
            gateway="zibal",
            status=Payment.PaymentStatus.PENDING,
            transaction_id="123456789",
        )
        self.age(10)

    def age(self, minutes):
        moment = timezone.now() - timedelta(minutes=minutes)
        Payment.objects.filter(pk=self.payment.pk).update(created_at=moment, updated_at=moment)

    def set_order_status(self, order_status):
        Order.objects.filter(pk=self.order.pk).update(status=order_status)

    def refresh(self):
        self.payment.refresh_from_db()
        self.order.refresh_from_db()

    @patch("apps.payments.services.requests.post")
    def test_paid_in_gateway_but_callback_lost_completes_order(self, post):
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_RECOVERY_1",
            "message": "Success",
        }
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.payment.tracking_code, "REF_RECOVERY_1")
        self.assertEqual(self.order.status, Order.OrderStatus.PROCESSING)
        self.assertTrue(Invoice.objects.filter(order=self.order).exists())
        self.assertTrue(Shipment.objects.filter(order=self.order).exists())

    @patch("apps.payments.services.requests.post")
    def test_unresolved_verify_response_keeps_payment_pending(self, post):
        old_updated_at = Payment.objects.get(pk=self.payment.pk).updated_at
        post.return_value.json.return_value = {"result": 102, "message": "Unknown response"}
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.assertGreater(self.payment.updated_at, old_updated_at)
        post.assert_called_once()

    @patch("apps.payments.services.requests.post")
    def test_invalid_verify_response_keeps_payment_pending(self, post):
        post.return_value.json.return_value = {}
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.assertEqual(self.payment.gateway_response_code, "invalid_response")
        post.assert_called_once()

    @patch("apps.payments.services.requests.post")
    def test_late_payment_for_cancelled_order_is_not_reactivated(self, post):
        self.set_order_status(Order.OrderStatus.CANCELLED)
        Payment.objects.filter(pk=self.payment.pk).update(status=Payment.PaymentStatus.CANCELLED)
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_LATE_1",
            "message": "Success",
        }
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.order.status, Order.OrderStatus.CANCELLED)
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())
        self.assertFalse(Shipment.objects.filter(order=self.order).exists())

    @patch("apps.payments.tasks.ZibalService.verify_payment")
    def test_too_old_or_too_recent_payments_are_not_rechecked(self, verify_payment):
        for minutes in (25 * 60, 2):
            with self.subTest(minutes=minutes):
                self.age(minutes)
                reverify_pending_payments()
        verify_payment.assert_not_called()

    @patch("apps.payments.services.requests.post")
    def test_paid_order_without_invoice_or_shipment_is_completed(self, post):
        self.set_order_status(Order.OrderStatus.PROCESSING)
        Payment.objects.filter(pk=self.payment.pk).update(
            status=Payment.PaymentStatus.SUCCESS,
            tracking_code="REF_DONE_1",
            paid_at=timezone.now(),
        )
        result = reverify_pending_payments()
        self.assertEqual(result, 1)
        self.assertTrue(Invoice.objects.filter(order=self.order).exists())
        self.assertTrue(Shipment.objects.filter(order=self.order).exists())
        post.assert_not_called()

    @patch("apps.payments.tasks.cache.add")
    def test_manual_review_cases_are_logged_once(self, add):
        self.set_order_status(Order.OrderStatus.CANCELLED)
        Payment.objects.filter(pk=self.payment.pk).update(
            status=Payment.PaymentStatus.SUCCESS,
            tracking_code="REF_REVIEW_1",
            paid_at=timezone.now(),
        )
        add.return_value = True
        with self.assertLogs("apps.payments.tasks", level="ERROR") as logs:
            reverify_pending_payments()
        self.assertTrue(any(str(self.payment.pk) in line for line in logs.output))
        add.return_value = False
        with self.assertNoLogs("apps.payments.tasks", level="ERROR"):
            reverify_pending_payments()

    @patch("apps.payments.tasks.cache.add", return_value=True)
    def test_previously_verified_payment_is_reported_for_manual_review(self, add):
        Payment.objects.filter(pk=self.payment.pk).update(status=Payment.PaymentStatus.CANCELLED, gateway_response_code="201")
        with self.assertLogs("apps.payments.tasks", level="ERROR") as logs:
            reverify_pending_payments()
        self.assertTrue(any("قبلاً در زیبال تأیید شده" in line for line in logs.output))

    @patch("apps.payments.tasks.cache.add", return_value=True)
    def test_old_manual_review_cases_are_reported(self, add):
        self.age(25 * 60)
        self.set_order_status(Order.OrderStatus.CANCELLED)
        old_paid_at = timezone.now() - timedelta(days=8)
        paid_payment = Payment.objects.create(
            order=self.order,
            amount=100000,
            gateway="zibal",
            status=Payment.PaymentStatus.SUCCESS,
            transaction_id="123456780",
            tracking_code="REF_OLD_PAID",
            paid_at=old_paid_at,
        )
        reversed_payment = Payment.objects.create(
            order=self.order,
            amount=100000,
            gateway="zibal",
            status=Payment.PaymentStatus.CANCELLED,
            transaction_id="123456781",
            gateway_response_code="201",
        )
        Payment.objects.filter(pk=reversed_payment.pk).update(updated_at=timezone.now() - timedelta(days=8))
        with self.assertLogs("apps.payments.tasks", level="ERROR") as logs:
            reverify_pending_payments()
        output = "\n".join(logs.output)
        self.assertIn(str(self.payment.pk), output)
        self.assertIn(str(paid_payment.pk), output)
        self.assertIn(str(reversed_payment.pk), output)

    def test_task_skips_when_lock_is_already_held(self):
        with (
            patch("apps.payments.tasks._acquire_lock", return_value=None),
            patch("apps.payments.tasks._recheck_unsettled") as recheck,
            patch("apps.payments.tasks._complete_paid_orders") as complete,
            patch("apps.payments.tasks._report_manual_review") as report,
        ):
            result = reverify_pending_payments()
        self.assertEqual(result, 0)
        recheck.assert_not_called()
        complete.assert_not_called()
        report.assert_not_called()

    def test_task_releases_lock_after_success(self):
        token = "test-lock-token"
        with (
            patch("apps.payments.tasks._acquire_lock", return_value=token),
            patch("apps.payments.tasks._recheck_unsettled", return_value=2),
            patch("apps.payments.tasks._complete_paid_orders", return_value=3),
            patch("apps.payments.tasks._report_manual_review"),
            patch("apps.payments.tasks._release_lock") as release,
        ):
            result = reverify_pending_payments()
        self.assertEqual(result, 5)
        release.assert_called_once_with(token)

    def test_task_releases_lock_when_processing_raises(self):
        token = "test-lock-token"
        with (
            patch("apps.payments.tasks._acquire_lock", return_value=token),
            patch("apps.payments.tasks._recheck_unsettled", side_effect=RuntimeError("Test error")),
            patch("apps.payments.tasks._release_lock") as release,
            self.assertRaises(RuntimeError),
        ):
            reverify_pending_payments()
        release.assert_called_once_with(token)


@override_settings(ZIBAL_MERCHANT_ID="test-merchant")
class PaymentCallbackFlowTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(phone_number="09123456789")
        self.order = Order.objects.create(
            user=self.user,
            subtotal=100000,
            discount_amount=0,
            shipping_amount=0,
            total_amount=100000,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            amount=100000,
            gateway="zibal",
            status=Payment.PaymentStatus.PENDING,
            transaction_id="123456",
        )
        self.callback_url = reverse("payments:callback")

    def call_callback(self, track_id="123456", gateway_status="OK"):
        return self.client.get(
            self.callback_url,
            {
                "payment_id": str(self.payment.pk),
                "trackId": track_id,
                "orderId": str(self.payment.pk),
                "Status": gateway_status,
            },
            secure=True,
        )

    @patch("apps.payments.services.requests.post")
    def test_wrong_track_id_redirects_to_failure_without_gateway_call(self, post):
        response = self.call_callback(track_id="999999")
        self.assertIn("status=review", response.url)
        post.assert_not_called()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)

    @patch("apps.payments.services.requests.post")
    def test_successful_verification_redirects_to_success(self, post):
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_CB_1",
            "message": "Success",
        }
        response = self.call_callback()
        self.assertIn("status=success", response.url)
        self.assertIn("tracking_code=REF_CB_1", response.url)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.PROCESSING)

    @patch("apps.payments.services.requests.post", side_effect=requests.exceptions.Timeout)
    def test_network_error_redirects_to_pending(self, post):
        response = self.call_callback()
        self.assertIn("status=pending", response.url)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)

    @patch("apps.payments.services.requests.post")
    def test_unresolved_gateway_response_redirects_to_pending(self, post):
        post.return_value.json.return_value = {"result": 102, "message": "Unknown response"}
        response = self.call_callback()
        self.assertIn("status=pending", response.url)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)

    @patch("apps.payments.services.requests.post")
    def test_success_for_cancelled_order_is_not_shown_as_success(self, post):
        Order.objects.filter(pk=self.order.pk).update(status=Order.OrderStatus.CANCELLED)
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_CB_2",
            "message": "Success",
        }
        response = self.call_callback()
        self.assertIn("status=review", response.url)
        self.assertNotIn("status=success", response.url)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CANCELLED)

    @patch("apps.payments.services.requests.post")
    def test_repeated_callback_does_not_call_gateway_twice(self, post):
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_CB_3",
            "message": "Success",
        }
        first = self.call_callback()
        second = self.call_callback()
        self.assertIn("status=success", first.url)
        self.assertIn("status=success", second.url)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(Invoice.objects.filter(order=self.order).count(), 1)
        self.assertEqual(Shipment.objects.filter(order=self.order).count(), 1)

    @patch("apps.payments.services.requests.post")
    def test_success_for_expired_order_within_grace_redirects_to_success(self, post):
        Order.objects.filter(pk=self.order.pk).update(expires_at=timezone.now() - timedelta(minutes=15))
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_EXPIRED_1",
            "message": "Success",
        }
        response = self.call_callback()
        self.assertIn("status=success", response.url)
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.order.status, Order.OrderStatus.PROCESSING)
        self.assertTrue(Invoice.objects.filter(order=self.order).exists())
        self.assertTrue(Shipment.objects.filter(order=self.order).exists())

    @patch("apps.payments.services.requests.post")
    def test_success_for_expired_order_after_grace_redirects_to_review(self, post):
        Order.objects.filter(pk=self.order.pk).update(expires_at=timezone.now() - timedelta(minutes=15))
        Payment.objects.filter(pk=self.payment.pk).update(created_at=timezone.now() - timedelta(hours=2))
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_EXPIRED_2",
            "message": "Success",
        }
        response = self.call_callback()
        self.assertIn("status=review", response.url)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.PENDING)
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())
        self.assertFalse(Shipment.objects.filter(order=self.order).exists())

    @patch("apps.payments.services.requests.post")
    def test_gateway_failure_status_does_not_override_successful_verification(self, post):
        post.return_value.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1000000,
            "orderId": str(self.payment.pk),
            "paidAt": timezone.now().isoformat(),
            "refNumber": "REF_NOK_PAID",
            "message": "Success",
        }
        response = self.call_callback(gateway_status="NOK")
        self.assertIn("status=success", response.url)
        self.assertIn("tracking_code=REF_NOK_PAID", response.url)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.order.status, Order.OrderStatus.PROCESSING)
        self.assertEqual(post.call_count, 1)

    @patch("apps.payments.services.requests.post")
    def test_invalid_verify_response_redirects_to_pending(self, post):
        post.return_value.json.return_value = {}
        response = self.call_callback()
        self.assertIn("status=pending", response.url)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
