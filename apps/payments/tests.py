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

    @patch("apps.payments.services.transaction.atomic", return_value=nullcontext())
    @patch("apps.payments.services.Invoice.objects.get_or_create")
    @patch("apps.payments.services.Shipment.objects.get_or_create")
    @patch("apps.payments.services.Payment.objects.select_for_update")
    @patch("apps.payments.services.Order.objects.select_for_update")
    @patch("apps.payments.services.Payment.objects.select_related")
    @patch("apps.payments.services.ZarinpalService._parse_response", return_value=({"ref_id": 123456}, 100, "success"))
    @patch("apps.payments.services.requests.post")
    def test_successful_gateway_response_marks_payment_success(self, post, parse_response, select_related, lock_order, lock_payment, get_shipment, get_invoice, atomic):
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
        self.assertEqual(self.order.status, Payment.order.field.related_model.OrderStatus.PROCESSING)
        self.assertTrue(result.paid_at)
        post.assert_called_once()
        get_shipment.assert_called_once()
        get_invoice.assert_called_once()

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
            subtotal=Decimal("100000"),
            discount_amount=Decimal("0"),
            shipping_amount=Decimal("0"),
            total_amount=Decimal("100000"),
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
    def test_reverify_task_retries_pending_payment(self, post):
        self.payment.status = Payment.PaymentStatus.PENDING
        self.payment.gateway_response_code = "net"
        self.payment.save(update_fields=["status", "gateway_response_code", "updated_at"])

        # Make the payment eligible for retry after five minutes.
        Payment.objects.filter(pk=self.payment.pk).update(updated_at=timezone.now() - timedelta(minutes=6))
        post.return_value.json.return_value = {
            "data": {
                "code": 100,
                "ref_id": "REF_RETRY_123",
            }
        }
        checked = reverify_pending_payments()
        self.payment.refresh_from_db()
        self.assertEqual(checked, 1)
        self.assertEqual(self.payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(self.payment.tracking_code, "REF_RETRY_123")
