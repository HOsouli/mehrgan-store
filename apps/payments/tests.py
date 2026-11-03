from contextlib import nullcontext
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from apps.payments.models import Payment
from apps.payments.services import ZarinpalService
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
import requests
from django.test import TestCase
from django.conf import settings
from apps.accounts.models import CustomUser
from apps.orders.models import Order, OrderAddress, OrderItem
from apps.catalog.models import Product, Category, Brand
from decimal import Decimal
from apps.invoices.models import Invoice
from apps.shipments.models import Shipment
from apps.payments.tasks import reverify_pending_payments
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse


class VerifyPaymentTests(SimpleTestCase):
    def setUp(self):
        self.order = MagicMock()
        self.order.pk = "order-id"
        self.order.status = Payment.order.field.related_model.OrderStatus.PROCESSING
        self.order.shipping_amount = 0
        self.order.subtotal = 100
        self.order.discount_amount = 0
        self.order.total_amount = 100
        self.payment = MagicMock()
        self.payment.pk = "payment-id"
        self.payment.order_id = self.order.pk
        self.payment.order = self.order
        self.payment.transaction_id = "authority"
        self.payment.amount = 100
        self.payment.status = Payment.PaymentStatus.SUCCESS
        self.order.expires_at = timezone.now() + timedelta(minutes=15)

    @patch("apps.payments.services.transaction.atomic", return_value=nullcontext())
    @patch("apps.payments.services.Invoice.objects.get_or_create")
    @patch("apps.payments.services.Shipment.objects.get_or_create")
    @patch("apps.payments.services.Payment.objects.select_related")
    @patch("apps.payments.services.requests.post")
    def test_successful_payment_retry_completes_invoice_and_shipment(self, post, select_related, get_shipment, get_invoice, atomic):
        select_related.return_value.get.return_value = self.payment
        get_invoice.return_value = (MagicMock(), False)
        result = ZarinpalService.verify_payment(self.payment.pk, "authority")
        self.assertEqual(result, self.payment)
        post.assert_not_called()
        get_shipment.assert_called_once()
        get_invoice.assert_called_once()

    @patch("apps.payments.services.transaction.atomic", return_value=nullcontext())
    @patch("apps.payments.services.Shipment.objects.get_or_create")
    @patch("apps.payments.services.Payment.objects.select_for_update")
    @patch("apps.payments.services.Order.objects.select_for_update")
    @patch("apps.payments.services.Payment.objects.select_related")
    @patch("apps.payments.services.ZarinpalService._parse_response", return_value=({}, 99, "failed"))
    @patch("apps.payments.services.requests.post")
    def test_failed_payment_does_not_create_invoice_or_shipment(self, post, parse_response, select_related, lock_order, lock_payment, get_shipment, atomic):
        self.payment.status = Payment.PaymentStatus.PENDING
        self.order.status = Payment.order.field.related_model.OrderStatus.PENDING
        select_related.return_value.get.return_value = self.payment
        lock_order.return_value.get.return_value = self.order
        lock_payment.return_value.get.return_value = self.payment
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {}
        result = ZarinpalService.verify_payment(self.payment.pk, "authority")
        self.assertEqual(result.status, Payment.PaymentStatus.FAILED)
        get_shipment.assert_not_called()

    @patch("apps.payments.services.transaction.atomic", return_value=nullcontext())
    @patch("apps.payments.services.Payment.objects.select_for_update")
    @patch("apps.payments.services.Order.objects.select_for_update")
    @patch("apps.payments.services.Payment.objects.select_related")
    @patch("apps.payments.services.ZarinpalService._parse_response", return_value=({}, 100, "success"))
    @patch("apps.payments.services.requests.post")
    def test_successful_gateway_response_without_ref_id_does_not_mark_payment_success(self, post, parse_response, select_related, lock_order, lock_payment, atomic):
        self.payment.status = Payment.PaymentStatus.PENDING
        self.payment.tracking_code = None
        self.order.status = Payment.order.field.related_model.OrderStatus.PENDING
        select_related.return_value.get.return_value = self.payment
        lock_order.return_value.get.return_value = self.order
        lock_payment.return_value.get.return_value = self.payment
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {}
        with self.assertRaisesMessage(ValidationError, "کد رهگیری پرداخت در پاسخ درگاه وجود ندارد"):
            ZarinpalService.verify_payment(self.payment.pk, "authority")
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.assertIsNone(self.payment.tracking_code)
        self.payment.save.assert_called_once()

    @patch("apps.payments.services.Invoice.objects.get_or_create")
    @patch("apps.payments.services.Shipment.objects.get_or_create")
    @patch("apps.payments.services.transaction.atomic", return_value=nullcontext())
    @patch("apps.payments.services.Payment.objects.select_for_update")
    @patch("apps.payments.services.Order.objects.select_for_update")
    @patch("apps.payments.services.Payment.objects.select_related")
    @patch("apps.payments.services.ZarinpalService._parse_response", return_value=({"ref_id": 123456}, 100, "success"))
    @patch("apps.payments.services.requests.post")
    def test_successful_gateway_response_marks_payment_success(self, post, parse_response, select_related, lock_order, lock_payment, atomic, get_shipment, get_invoice):
        self.payment.status = Payment.PaymentStatus.PENDING
        self.order.status = Payment.order.field.related_model.OrderStatus.PENDING
        select_related.return_value.get.return_value = self.payment
        lock_order.return_value.get.return_value = self.order
        lock_payment.return_value.get.return_value = self.payment
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {}
        get_invoice.return_value = (MagicMock(), False)
        result = ZarinpalService.verify_payment(self.payment.pk, "authority")
        self.assertEqual(result.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(result.tracking_code, "123456")
        self.assertEqual(self.order.status, Payment.order.field.related_model.OrderStatus.PROCESSING)
        self.assertTrue(result.paid_at)
        get_shipment.assert_called_once()
        get_invoice.assert_called_once()

    @patch("apps.payments.services.Invoice.objects.get_or_create")
    @patch("apps.payments.services.Shipment.objects.get_or_create")
    @patch("apps.payments.services.transaction.atomic", return_value=nullcontext())
    @patch("apps.payments.services.Payment.objects.select_for_update")
    @patch("apps.payments.services.Order.objects.select_for_update")
    @patch("apps.payments.services.Payment.objects.select_related")
    @patch("apps.payments.services.ZarinpalService._parse_response", return_value=({"ref_id": 123456}, 100, "success"))
    @patch("apps.payments.services.requests.post")
    def test_successful_payment_for_expired_order(self, post, parse_response, select_related, lock_order, lock_payment, atomic, get_shipment, get_invoice):
        self.payment.status = Payment.PaymentStatus.PENDING
        self.order.status = Payment.order.field.related_model.OrderStatus.PENDING
        self.order.expires_at = timezone.now() - timedelta(minutes=15)
        select_related.return_value.get.return_value = self.payment
        lock_order.return_value.get.return_value = self.order
        lock_payment.return_value.get.return_value = self.payment
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {}
        get_invoice.return_value = (MagicMock(), False)
        result = ZarinpalService.verify_payment(self.payment.pk, "authority")
        self.assertEqual(result.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(result.tracking_code, "123456")
        self.assertEqual(self.order.status, Payment.order.field.related_model.OrderStatus.PENDING)
        self.assertTrue(result.paid_at)
        post.assert_called_once()
        get_shipment.assert_not_called()
        get_invoice.assert_not_called()

    @patch("apps.payments.services.transaction.atomic", return_value=nullcontext())
    @patch("apps.payments.services.Payment.objects.select_for_update")
    @patch("apps.payments.services.Payment.objects.select_related")
    @patch("apps.payments.services.requests.post", side_effect=requests.exceptions.Timeout)
    def test_network_error_keeps_payment_pending(self, post, select_related, lock_payment, atomic):
        self.payment.status = Payment.PaymentStatus.PENDING
        select_related.return_value.get.return_value = self.payment
        lock_payment.return_value.get.return_value = self.payment
        with self.assertRaises(ValidationError):
            ZarinpalService.verify_payment(self.payment.pk, "authority")
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.payment.save.assert_called_once()


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

    @patch("apps.payments.services.requests.post")
    def test_successful_request_creates_pending_payment(self, post):
        post.return_value.json.return_value = {
            "data": {"code": 100, "authority": "AUTH_TEST_123"}
        }
        payment, pay_url = ZarinpalService.request_payment(self.order)
        self.assertEqual(payment.status, Payment.PaymentStatus.PENDING)
        self.assertEqual(payment.transaction_id, "AUTH_TEST_123")
        self.assertIn("AUTH_TEST_123", pay_url)
        self.assertEqual(payment.amount, self.order.total_amount)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["amount"], 100000)
        self.assertEqual(payload["merchant_id"], settings.ZARINPAL_MERCHANT_ID)

    @patch("apps.payments.services.requests.post")
    def test_existing_pending_payment_reuses_transaction(self, post):
        payment = Payment.objects.create(
            order=self.order,
            amount=self.order.total_amount,
            gateway="zarinpal",
            status=Payment.PaymentStatus.PENDING,
            transaction_id="AUTH_EXISTING_123",
        )
        result, pay_url = ZarinpalService.request_payment(self.order)
        self.assertEqual(result.pk, payment.pk)
        self.assertIn("AUTH_EXISTING_123", pay_url)
        post.assert_not_called()

    @patch("apps.payments.services.requests.post", side_effect=requests.exceptions.Timeout,)
    def test_network_error_keeps_payment_pending(self, post):
        with self.assertRaises(ValidationError):
            ZarinpalService.request_payment(self.order)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.PaymentStatus.PENDING)
        self.assertFalse(payment.transaction_id)
        self.assertTrue(payment.gateway_response_message)

    @patch("apps.payments.services.requests.post")
    def test_successful_gateway_response_without_authority_fails_safely(self, post):
        post.return_value.json.return_value = {
            "data": {"code": 100}
        }
        with self.assertRaises(ValidationError):
            ZarinpalService.request_payment(self.order)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.PaymentStatus.PENDING)
        self.assertFalse(payment.transaction_id)


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
            gateway="zarinpal",
            status=Payment.PaymentStatus.SUCCESS,
            transaction_id="AUTH_TEST_123",
            tracking_code="123456789",
            paid_at=timezone.now(),
        )

    def test_repeated_successful_verification_does_not_duplicate_invoice_or_shipment(self):
        service = ZarinpalService()
        service.verify_payment(self.payment.pk, self.payment.transaction_id)
        service.verify_payment(self.payment.pk, self.payment.transaction_id)
        self.assertEqual(Invoice.objects.filter(order=self.order).count(), 1)
        self.assertEqual(Shipment.objects.filter(order=self.order).count(), 1)

    @patch("apps.payments.services.requests.post")
    def test_successful_payment_for_cancelled_order_does_not_reactivate_order(self, post):
        self.order.status = Order.OrderStatus.CANCELLED
        self.order.save(update_fields=["status", "updated_at"])
        post.return_value.json.return_value = {"data": {"code": 100, "ref_id": "REF_CANCELLED_123"}}
        payment = self.payment
        payment.status = Payment.PaymentStatus.PENDING
        payment.save(update_fields=["status", "updated_at"])
        result = ZarinpalService.verify_payment(payment.pk, payment.transaction_id)
        self.order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.PaymentStatus.SUCCESS)
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
            "data": {
                "code": 100,
                "ref_id": "REF_LATE_SUCCESS_123",
            }
        }
        ZarinpalService.verify_payment(self.payment.pk, self.payment.transaction_id)
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
        self.payment.save(update_fields=[
            "status", "gateway_response_code", "updated_at"
        ])
        post.return_value.json.return_value = {"data": {}}
        with self.assertRaisesMessage(ValidationError, "پاسخ درگاه معتبر نیست"):
            ZarinpalService.verify_payment(
                self.payment.pk,
                self.payment.transaction_id,
            )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.assertEqual(self.payment.gateway_response_code, "net")

    @patch("apps.payments.services.requests.post")
    @patch("apps.payments.tasks.ZarinpalService.inquire_payment", return_value="PAID")
    def test_reverify_task_retries_pending_payment(self, inquire, post):
        self.payment.status = Payment.PaymentStatus.PENDING
        self.payment.gateway_response_code = "net"
        self.payment.save(update_fields=["status", "gateway_response_code", "updated_at"])
        Payment.objects.filter(pk=self.payment.pk).update(updated_at=timezone.now() - timedelta(minutes=6))
        post.return_value.json.return_value = {"data": {"code": 100, "ref_id": "REF_RETRY_123"}}
        checked = reverify_pending_payments()
        self.payment.refresh_from_db()
        self.assertEqual(checked, 1)
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.payment.tracking_code, "REF_RETRY_123")


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
            gateway="zarinpal",
            status=Payment.PaymentStatus.SUCCESS,
            transaction_id=f"AUTH_STATUS_{suffix}",
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
            {"payment_id": "invalid", "Authority": "AUTH_TEST", "Status": "OK"},
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("status=failed", response.url)

    @patch("apps.payments.views.ZarinpalService.verify_payment")
    def test_payment_callback_with_failed_gateway_status_does_not_verify(self, verify_payment):
        response = self.client.get(
            self.callback_url,
            {
                "payment_id": "00000000-0000-0000-0000-000000000001",
                "Authority": "AUTH_TEST",
                "Status": "NOK",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("status=failed", response.url)
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

    @patch("apps.payments.views.ZarinpalService.verify_payment")
    def test_payment_callback_failed_verification_redirects_to_failure(self, verify_payment):
        payment = MagicMock()
        payment.status = Payment.PaymentStatus.FAILED
        verify_payment.return_value = payment
        response = self.client.get(
            self.callback_url,
            {
                "payment_id": "00000000-0000-0000-0000-000000000001",
                "Authority": "AUTH_TEST",
                "Status": "OK",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("status=failed", response.url)
        verify_payment.assert_called_once()


class InquirePaymentTests(SimpleTestCase):
    @patch("apps.payments.services.requests.post")
    def test_returns_status_and_sends_authority(self, post):
        post.return_value.json.return_value = {"data": {"status": "PAID", "code": 100}}
        self.assertEqual(ZarinpalService.inquire_payment("AUTH_1"), "PAID")
        args, kwargs = post.call_args
        self.assertTrue(args[0].endswith("/pg/v4/payment/inquiry.json"))
        self.assertEqual(kwargs["json"]["authority"], "AUTH_1")
        self.assertEqual(kwargs["json"]["merchant_id"], settings.ZARINPAL_MERCHANT_ID)

    @patch("apps.payments.services.requests.post")
    def test_http_error_returns_none(self, post):
        post.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError
        self.assertIsNone(ZarinpalService.inquire_payment("AUTH_1"))

    @patch("apps.payments.services.requests.post", side_effect=requests.exceptions.Timeout)
    def test_network_error_returns_none(self, post):
        self.assertIsNone(ZarinpalService.inquire_payment("AUTH_1"))

    @patch("apps.payments.services.requests.post")
    def test_invalid_body_returns_none(self, post):
        post.return_value.json.return_value = {"errors": {"code": -54}}
        self.assertIsNone(ZarinpalService.inquire_payment("AUTH_1"))


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
            gateway="zarinpal",
            status=Payment.PaymentStatus.PENDING,
            transaction_id="AUTH_RECOVERY_1",
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
    @patch("apps.payments.tasks.ZarinpalService.inquire_payment", return_value="PAID")
    def test_paid_in_gateway_but_callback_lost_completes_order(self, inquire, post):
        post.return_value.json.return_value = {"data": {"code": 100, "ref_id": "REF_1"}}
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.payment.tracking_code, "REF_1")
        self.assertEqual(self.order.status, Order.OrderStatus.PROCESSING)
        self.assertTrue(Invoice.objects.filter(order=self.order).exists())
        self.assertTrue(Shipment.objects.filter(order=self.order).exists())

    @patch("apps.payments.services.requests.post")
    @patch("apps.payments.tasks.ZarinpalService.inquire_payment", return_value="IN_BANK")
    def test_in_bank_keeps_payment_pending_and_postpones_next_check(self, inquire, post):
        old_updated_at = Payment.objects.get(pk=self.payment.pk).updated_at
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.assertGreater(self.payment.updated_at, old_updated_at)
        post.assert_not_called()

    @patch("apps.payments.services.requests.post")
    @patch("apps.payments.tasks.ZarinpalService.inquire_payment", return_value=None)
    def test_unknown_inquiry_keeps_payment_pending(self, inquire, post):
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        post.assert_not_called()

    @patch("apps.payments.tasks.ZarinpalService.inquire_payment", return_value="FAILED")
    def test_failed_inquiry_closes_payment_only_after_grace(self, inquire):
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)
        self.age(31)
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.FAILED)
        self.assertEqual(self.payment.gateway_response_code, "FAILED")

    @patch("apps.payments.tasks.ZarinpalService.inquire_payment", return_value="REVERSED")
    def test_reversed_inquiry_is_recorded_and_order_not_reactivated(self, inquire):
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.FAILED)
        self.assertEqual(self.payment.gateway_response_code, "REVERSED")
        self.assertIn("برگشت", self.payment.gateway_response_message)
        self.assertEqual(self.order.status, Order.OrderStatus.PENDING)
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())

    @patch("apps.payments.services.requests.post")
    @patch("apps.payments.tasks.ZarinpalService.inquire_payment", return_value="PAID")
    def test_late_payment_for_cancelled_order_is_not_reactivated(self, inquire, post):
        self.set_order_status(Order.OrderStatus.CANCELLED)
        Payment.objects.filter(pk=self.payment.pk).update(status=Payment.PaymentStatus.CANCELLED)
        post.return_value.json.return_value = {"data": {"code": 100, "ref_id": "REF_LATE_1"}}
        reverify_pending_payments()
        self.refresh()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.order.status, Order.OrderStatus.CANCELLED)
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())
        self.assertFalse(Shipment.objects.filter(order=self.order).exists())

    @patch("apps.payments.tasks.ZarinpalService.inquire_payment", return_value="PAID")
    def test_too_old_or_too_recent_payments_are_not_inquired(self, inquire):
        for minutes in (25 * 60, 2):
            with self.subTest(minutes=minutes):
                self.age(minutes)
                reverify_pending_payments()
                inquire.assert_not_called()

    @patch("apps.payments.services.requests.post")
    @patch("apps.payments.tasks.ZarinpalService.inquire_payment", return_value=None)
    def test_paid_order_without_invoice_or_shipment_is_completed(self, inquire, post):
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
        inquire.assert_not_called()

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
    def test_reversed_payment_is_reported_for_review(self, add):
        Payment.objects.filter(pk=self.payment.pk).update(
            status=Payment.PaymentStatus.FAILED,
            gateway_response_code="REVERSED",
            updated_at=timezone.now(),
        )
        with self.assertLogs("apps.payments.tasks", level="ERROR") as logs:
            reverify_pending_payments()
        self.assertTrue(any("تطبیق مالی" in line for line in logs.output))

    @patch("apps.payments.tasks.cache.add", return_value=True)
    def test_old_manual_review_cases_are_reported(self, add):
        self.age(25 * 60)
        self.set_order_status(Order.OrderStatus.CANCELLED)
        old_paid_at = timezone.now() - timedelta(days=8)
        paid_payment = Payment.objects.create(
            order=self.order,
            amount=100000,
            gateway="zarinpal",
            status=Payment.PaymentStatus.SUCCESS,
            transaction_id="AUTH_OLD_PAID",
            tracking_code="REF_OLD_PAID",
            paid_at=old_paid_at,
        )
        reversed_payment = Payment.objects.create(
            order=self.order,
            amount=100000,
            gateway="zarinpal",
            status=Payment.PaymentStatus.FAILED,
            transaction_id="AUTH_OLD_REVERSED",
            gateway_response_code="REVERSED",
        )
        Payment.objects.filter(pk=reversed_payment.pk).update(updated_at=timezone.now() - timedelta(days=8))
        with self.assertLogs("apps.payments.tasks", level="ERROR") as logs:
            reverify_pending_payments()
        output = "\n".join(logs.output)
        self.assertIn(str(self.payment.pk), output)
        self.assertIn(str(paid_payment.pk), output)
        self.assertIn(str(reversed_payment.pk), output)


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
            gateway="zarinpal",
            status=Payment.PaymentStatus.PENDING,
            transaction_id="AUTH_CB_1",
        )
        self.callback_url = reverse("payments:callback")

    def call_callback(self, authority="AUTH_CB_1", gateway_status="OK"):
        return self.client.get(
            self.callback_url,
            {"payment_id": str(self.payment.pk), "Authority": authority, "Status": gateway_status},
            secure=True,
        )

    @patch("apps.payments.services.requests.post")
    def test_wrong_authority_redirects_to_failure_without_gateway_call(self, post):
        response = self.call_callback(authority="WRONG_AUTHORITY")
        self.assertIn("status=failed", response.url)
        post.assert_not_called()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.PENDING)

    @patch("apps.payments.services.requests.post")
    def test_successful_verification_redirects_to_success(self, post):
        post.return_value.json.return_value = {"data": {"code": 100, "ref_id": "REF_CB_1"}}
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
    def test_definite_gateway_failure_redirects_to_failure(self, post):
        post.return_value.json.return_value = {"data": {}, "errors": {"code": -51, "message": "failed"}}
        response = self.call_callback()
        self.assertIn("status=failed", response.url)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.FAILED)

    @patch("apps.payments.services.requests.post")
    def test_success_for_cancelled_order_is_not_shown_as_success(self, post):
        Order.objects.filter(pk=self.order.pk).update(status=Order.OrderStatus.CANCELLED)
        post.return_value.json.return_value = {"data": {"code": 100, "ref_id": "REF_CB_2"}}
        response = self.call_callback()
        self.assertIn("status=review", response.url)
        self.assertNotIn("status=success", response.url)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CANCELLED)

    @patch("apps.payments.services.requests.post")
    def test_repeated_callback_does_not_call_gateway_twice(self, post):
        post.return_value.json.return_value = {"data": {"code": 100, "ref_id": "REF_CB_3"}}
        first = self.call_callback()
        second = self.call_callback()
        self.assertIn("status=success", first.url)
        self.assertIn("status=success", second.url)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(Invoice.objects.filter(order=self.order).count(), 1)
        self.assertEqual(Shipment.objects.filter(order=self.order).count(), 1)

    @patch("apps.payments.services.requests.post")
    def test_success_for_expired_pending_order_redirects_to_review(self, post):
        Order.objects.filter(pk=self.order.pk).update(expires_at=timezone.now() - timedelta(minutes=15))
        post.return_value.json.return_value = {"data": {"code": 100, "ref_id": "REF_EXPIRED_1"}}
        response = self.call_callback()
        self.assertIn("status=review", response.url)
        self.assertNotIn("status=success", response.url)
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.order.status, Order.OrderStatus.PENDING)
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())
        self.assertFalse(Shipment.objects.filter(order=self.order).exists())
