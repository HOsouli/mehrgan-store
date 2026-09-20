import requests
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import Payment
from apps.orders.models import Order
from django.db import transaction


class ZarinpalService:

    @staticmethod
    def _base_url():
        return "https://sandbox.zarinpal.com" if settings.ZARINPAL_SANDBOX else "https://payment.zarinpal.com"

    @staticmethod
    def request_payment(order):
        if order.status == Order.OrderStatus.CANCELLED:
            raise ValidationError("این سفارش لغو شده است.")

        if timezone.now() > order.expires_at:
            raise ValidationError("مهلت این سفارش به پایان رسیده است.")

        if order.payments.filter(status=Payment.PaymentStatus.SUCCESS).exists():
            raise ValidationError("این سفارش قبلاً پرداخت شده است.")

        existing_pending = order.payments.filter(status=Payment.PaymentStatus.PENDING).first()
        if existing_pending and existing_pending.transaction_id:
            pay_url = f"{ZarinpalService._base_url()}/pg/StartPay/{existing_pending.transaction_id}"
            return existing_pending, pay_url

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
            raise ValidationError("خطا در ارتباط با درگاه پرداخت. لطفاً دوباره تلاش کنید.")

        payment.gateway_response_code = str(data.get("data", {}).get("code", ""))
        payment.gateway_response_message = data.get("data", {}).get("message", "") or str(data.get("errors", ""))

        if data.get("data", {}).get("code") != 100:
            payment.status = Payment.PaymentStatus.FAILED
            payment.save(update_fields=["status", "gateway_response_code", "gateway_response_message"])
            raise ValidationError("خطا در اتصال به درگاه پرداخت.")

        authority = data["data"]["authority"]
        payment.transaction_id = authority
        payment.save(update_fields=["transaction_id", "gateway_response_code", "gateway_response_message"])

        pay_url = f"{ZarinpalService._base_url()}/pg/StartPay/{authority}"
        return payment, pay_url


    @staticmethod
    @transaction.atomic
    def verify_payment(payment_id, authority):
        try:
            payment = Payment.objects.select_for_update().select_related("order").get(id=payment_id, transaction_id=authority)
        except Payment.DoesNotExist:
            raise ValidationError("پرداخت یافت نشد.")

        if payment.status == Payment.PaymentStatus.SUCCESS:
            return payment

        url = f"{ZarinpalService._base_url()}/pg/v4/payment/verify.json"
        payload = {
            "merchant_id": settings.ZARINPAL_MERCHANT_ID,
            "amount": int(payment.amount),
            "authority": authority,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            data = response.json()
        except requests.exceptions.RequestException:
            raise ValidationError("خطا در ارتباط با درگاه پرداخت. لطفاً بعداً دوباره تلاش کنید.")

        payment.gateway_response_code = str(data.get("data", {}).get("code", ""))
        payment.gateway_response_message = data.get("data", {}).get("message", "") or str(data.get("errors", ""))

        if data.get("data", {}).get("code") in (100, 101):
            payment.status = Payment.PaymentStatus.SUCCESS
            payment.tracking_code = str(data["data"]["ref_id"])
            payment.paid_at = timezone.now()
            payment.save(update_fields=["status", "tracking_code", "paid_at", "gateway_response_code", "gateway_response_message"])

            order = payment.order
            order.status = Order.OrderStatus.PROCESSING
            order.save(update_fields=["status"])
        else:
            payment.status = Payment.PaymentStatus.FAILED
            payment.save(update_fields=["status", "gateway_response_code", "gateway_response_message"])
            raise ValidationError("تراکنش ناموفق بود.")

        return payment

