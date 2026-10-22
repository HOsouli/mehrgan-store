from contextlib import nullcontext
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from apps.payments.models import Payment
from apps.payments.services import ZarinpalService
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
import requests


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
        result = ZarinpalService.verify_payment(self.payment.pk, "authority")
        self.assertEqual(result.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(result.tracking_code, "123456")
        self.assertEqual(self.order.status, Payment.order.field.related_model.OrderStatus.PENDING)
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
