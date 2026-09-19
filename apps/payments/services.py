import requests
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import Payment


class ZarinpalService:

    @staticmethod
    def _base_url():
        return "https://sandbox.zarinpal.com" if settings.ZARINPAL_SANDBOX else "https://payment.zarinpal.com"

    @staticmethod
    def request_payment(order):
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

        response = requests.post(url, json=payload, timeout=10)
        data = response.json()

        if data.get("data", {}).get("code") != 100:
            payment.status = Payment.PaymentStatus.FAILED
            payment.save(update_fields=["status"])
            raise ValidationError("خطا در اتصال به درگاه پرداخت.")

        authority = data["data"]["authority"]
        payment.transaction_id = authority
        payment.save(update_fields=["transaction_id"])

        pay_url = f"{ZarinpalService._base_url()}/pg/StartPay/{authority}"
        return payment, pay_url

    @staticmethod
    def verify_payment(payment_id, authority):
        try:
            payment = Payment.objects.select_related("order").get(id=payment_id, transaction_id=authority)
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

        response = requests.post(url, json=payload, timeout=10)
        data = response.json()

        if data.get("data", {}).get("code") in (100, 101):
            payment.status = Payment.PaymentStatus.SUCCESS
            payment.tracking_code = str(data["data"]["ref_id"])
            payment.paid_at = timezone.now()
            payment.save(update_fields=["status", "tracking_code", "paid_at"])
        else:
            payment.status = Payment.PaymentStatus.FAILED
            payment.save(update_fields=["status"])
            raise ValidationError("تراکنش ناموفق بود.")

        return payment
