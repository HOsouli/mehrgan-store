import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.orders.models import Order
from apps.shipments.models import Shipment
from .models import Payment
from apps.invoices.models import Invoice, InvoiceItem
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class ZarinpalService:

    @staticmethod
    def _base_url():
        return "https://sandbox.zarinpal.com" if settings.ZARINPAL_SANDBOX else "https://payment.zarinpal.com"

    @staticmethod
    def _parse_response(data):
        info = data.get("data") if isinstance(data.get("data"), dict) else {}
        err = data.get("errors") if isinstance(data.get("errors"), dict) else {}
        code = info.get("code", err.get("code"))
        message = info.get("message") or err.get("message", "")
        return info, code, str(message)[:255]

    @staticmethod
    def request_payment(order):
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            if order.status == Order.OrderStatus.CANCELLED:
                raise ValidationError("این سفارش لغو شده است.")
            if timezone.now() > order.expires_at:
                raise ValidationError("مهلت این سفارش به پایان رسیده است.")
            if order.status != Order.OrderStatus.PENDING:
                raise ValidationError("این سفارش در وضعیت قابل پرداخت نیست.")
            if order.payments.filter(status=Payment.PaymentStatus.SUCCESS).exists():
                raise ValidationError("این سفارش قبلاً پرداخت شده است.")
            order.expires_at = max(order.expires_at, timezone.now() + timedelta(minutes=15))
            order.save(update_fields=["expires_at", "updated_at"])
            existing_pending = order.payments.filter(status=Payment.PaymentStatus.PENDING).first()
            if existing_pending and existing_pending.transaction_id:
                pay_url = f"{ZarinpalService._base_url()}/pg/StartPay/{existing_pending.transaction_id}"
                return existing_pending, pay_url
            if existing_pending:
                existing_pending.status = Payment.PaymentStatus.FAILED
                existing_pending.gateway_response_message = "درخواست قبلی پرداخت بدون دریافت شناسه تراکنش باقی مانده بود."
                existing_pending.save(update_fields=["status", "gateway_response_message", "updated_at"])
            payment = Payment.objects.create(
                order=order,
                amount=order.total_amount,
                gateway="zarinpal",
                status=Payment.PaymentStatus.PENDING,
            )
        url = f"{ZarinpalService._base_url()}/pg/v4/payment/request.json"
        payload = {
            "merchant_id": settings.ZARINPAL_MERCHANT_ID,
            "amount": int(order.total_amount),
            "callback_url": f"{settings.ZARINPAL_CALLBACK_URL}?payment_id={payment.id}",
            "description": f"پرداخت سفارش شماره {order.order_number}",
            "metadata": {"mobile": order.address.recipient_phone},
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            data = response.json()
        except requests.exceptions.RequestException:
            payment.gateway_response_message = "خطا در ارتباط با درگاه پرداخت."
            payment.save(update_fields=["gateway_response_message", "updated_at"])
            raise ValidationError("خطا در ارتباط با درگاه پرداخت. لطفاً دوباره تلاش کنید.")
        info, code, message = ZarinpalService._parse_response(data)
        payment.gateway_response_code = str(code or "")
        payment.gateway_response_message = message
        if code != 100:
            payment.status = Payment.PaymentStatus.FAILED
            payment.save(update_fields=["status", "gateway_response_code", "gateway_response_message", "updated_at"])
            raise ValidationError("خطا در اتصال به درگاه پرداخت.")
        authority = info["authority"]
        payment.transaction_id = authority
        payment.save(update_fields=["transaction_id", "gateway_response_code", "gateway_response_message", "updated_at"])
        pay_url = f"{ZarinpalService._base_url()}/pg/StartPay/{authority}"
        return payment, pay_url

    @staticmethod
    def verify_payment(payment_id, authority):
        try:
            payment = Payment.objects.select_related("order").get(id=payment_id, transaction_id=authority)
        except Payment.DoesNotExist:
            raise ValidationError("پرداخت یافت نشد.")
        if payment.status != Payment.PaymentStatus.SUCCESS:
            url = f"{ZarinpalService._base_url()}/pg/v4/payment/verify.json"
            payload = {
                "merchant_id": settings.ZARINPAL_MERCHANT_ID,
                "amount": int(payment.amount),
                "authority": authority,
            }
            try:
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                data = response.json()
            except (requests.exceptions.RequestException, ValueError):
                raise ValidationError("خطا در ارتباط با درگاه پرداخت. لطفاً بعداً دوباره تلاش کنید.")
            info, code, message = ZarinpalService._parse_response(data)
            if code is None:
                raise ValidationError("پاسخ نامعتبر از درگاه پرداخت. لطفاً بعداً دوباره تلاش کنید.")
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=payment.order_id)
                payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if payment.status != Payment.PaymentStatus.SUCCESS:
                    payment.gateway_response_code = str(code)
                    payment.gateway_response_message = message
                    if code not in (100, 101):
                        if payment.status == Payment.PaymentStatus.PENDING:
                            payment.status = Payment.PaymentStatus.FAILED
                        payment.save(update_fields=["status", "gateway_response_code", "gateway_response_message", "updated_at"])
                        return payment
                    ref_id = info.get("ref_id")
                    if not ref_id:
                        payment.gateway_response_message = "درگاه پرداخت را موفق اعلام کرده اما کد رهگیری موجود نیست؛ بررسی دستی لازم است."
                        payment.save(update_fields=["gateway_response_code", "gateway_response_message", "updated_at"])
                        raise ValidationError("کد رهگیری پرداخت در پاسخ درگاه وجود ندارد؛ پرداخت نیاز به بررسی دارد.")
                    payment.status = Payment.PaymentStatus.SUCCESS
                    payment.tracking_code = str(ref_id)
                    payment.paid_at = timezone.now()
                    if order.status == Order.OrderStatus.PENDING:
                        order.status = Order.OrderStatus.PROCESSING
                        order.save(update_fields=["status", "updated_at"])
                    else:
                        payment.gateway_response_message = "پرداخت موفق است؛ وضعیت سفارش نیاز به بررسی دستی دارد."
                    payment.save(update_fields=["status", "tracking_code", "paid_at", "gateway_response_code", "gateway_response_message", "updated_at"])
        payment.refresh_from_db()
        if payment.status != Payment.PaymentStatus.SUCCESS:
            return payment
        order = payment.order
        if order.status != Order.OrderStatus.PROCESSING:
            logger.error("پرداخت %s موفق است اما سفارش %s در وضعیت %s قرار دارد؛ بررسی دستی لازم است.", payment.pk, order.pk, order.status)
            return payment
        try:
            with transaction.atomic():
                Shipment.objects.get_or_create(
                    order=order,
                    defaults={
                        "method": Shipment.ShipmentMethod.OTHER,
                        "carrier": "",
                        "shipping_cost": order.shipping_amount,
                        "status": Shipment.ShipmentStatus.PENDING,
                    },
                )
                invoice, created = Invoice.objects.get_or_create(
                    order=order,
                    defaults={
                        "subtotal": order.subtotal,
                        "discount_amount": order.discount_amount,
                        "shipping_amount": order.shipping_amount,
                        "total_amount": order.total_amount,
                        "status": Invoice.InvoiceStatus.ISSUED,
                        "issued_at": timezone.now(),
                    },
                )
                if created:
                    for item in order.items.select_related("product").all():
                        InvoiceItem.objects.create(
                            invoice=invoice,
                            product=item.product,
                            product_name=item.product.name[:100],
                            quantity=item.quantity,
                            unit_price=item.unit_price,
                            discount_amount=item.discount_amount,
                            total_price=item.total_price,
                        )
        except Exception as exc:
            logger.exception("ساخت مرسوله یا فاکتور برای سفارش %s ناموفق بود", order.pk)
            raise ValidationError("پرداخت موفق است، اما تکمیل فاکتور یا مرسوله ناموفق بود؛ لطفاً دوباره تلاش کنید.") from exc
        return payment

