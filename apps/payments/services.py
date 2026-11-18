import logging
from datetime import timedelta
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.orders.models import Order
from apps.shipments.models import Shipment
from apps.invoices.models import Invoice, InvoiceItem
from .models import Payment
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from django.utils.dateparse import parse_datetime


logger = logging.getLogger(__name__)
ZIBAL_API_URL = "https://gateway.zibal.ir/v1"
ZIBAL_START_URL = "https://gateway.zibal.ir/start"

ZIBAL_REQUEST_REJECTED_RESULTS = frozenset({102, 103, 104, 105, 106, 113})
ZIBAL_MIN_AMOUNT_RIAL = 1000

class ZibalService:

    @staticmethod
    def _merchant():
        merchant = settings.ZIBAL_MERCHANT_ID
        if not merchant:
            raise ValidationError("شناسه پذیرنده زیبال تنظیم نشده است.")
        return merchant

    @staticmethod
    def _parse_response(response):
        if not isinstance(response, dict):
            return None, "", {}
        result = response.get("result")
        message = str(response.get("message") or "")[:255]
        try:
            result = int(result)
        except (TypeError, ValueError):
            result = None
        return result, message, response

    @staticmethod
    def _mark_payment_for_review(payment_id, message, code="net"):
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment_id)
            if payment.status == Payment.PaymentStatus.SUCCESS:
                return
            payment.gateway_response_message = message[:255]
            update_fields = ["gateway_response_message", "updated_at"]
            if not payment.gateway_response_code:
                payment.gateway_response_code = str(code)
                update_fields.append("gateway_response_code")
            payment.save(update_fields=update_fields)

    @staticmethod
    def _update_request_state(
        payment_id,
        request_state,
        message="",
        code="",
        status=None,
        transaction_id=None,
    ):
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment_id)
            if payment.status == Payment.PaymentStatus.SUCCESS:
                return payment
            payment.request_state = request_state
            update_fields = ["request_state", "updated_at"]
            if status is not None:
                payment.status = status
                update_fields.append("status")
            if transaction_id is not None:
                payment.transaction_id = transaction_id
                update_fields.append("transaction_id")
            if code:
                payment.gateway_response_code = str(code)
                update_fields.append("gateway_response_code")
            if message:
                payment.gateway_response_message = str(message)[:255]
                update_fields.append("gateway_response_message")
            payment.save(update_fields=update_fields)
        return payment

    @staticmethod
    def inquiry_payment(payment_id, track_id):
        try:
            normalized_track_id = int(track_id)
            if normalized_track_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError("شناسه تراکنش معتبر نیست.")
        try:
            payment = Payment.objects.get(
                pk=payment_id,
                transaction_id=str(normalized_track_id),
                gateway="zibal",
            )
        except Payment.DoesNotExist:
            raise ValidationError("پرداخت یافت نشد.")
        if payment.status == Payment.PaymentStatus.SUCCESS:
            return 100, "success", {}
        payload = {
            "merchant": ZibalService._merchant(),
            "trackId": normalized_track_id,
        }
        try:
            response = requests.post(f"{ZIBAL_API_URL}/inquiry", json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
        except (requests.exceptions.RequestException, ValueError) as exc:
            ZibalService._mark_payment_for_review(payment.pk, "نتیجه استعلام Inquiry به دلیل خطای ارتباطی مشخص نشد.")
            logger.warning("استعلام پرداخت %s نامشخص ماند: %s", payment.pk, exc)
            raise ValidationError("نتیجه استعلام پرداخت مشخص نشد؛ بررسی مجدد لازم است.") from exc
        result, message, info = ZibalService._parse_response(data)
        if result is None:
            ZibalService._mark_payment_for_review(payment.pk, "پاسخ Inquiry فاقد کد وضعیت معتبر است.")
            raise ValidationError("پاسخ Inquiry معتبر نیست.")
        if result != 100:
            ZibalService._mark_payment_for_review(payment.pk, message or "استعلام Inquiry موفق نبود.", code=result)
        return result, message, info

    @staticmethod
    def request_payment(order):
        merchant = ZibalService._merchant()
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            if order.status == Order.OrderStatus.CANCELLED:
                raise ValidationError("این سفارش لغو شده است.")
            now = timezone.now()
            if now > order.expires_at:
                raise ValidationError("مهلت این سفارش به پایان رسیده است.")
            if order.status != Order.OrderStatus.PENDING:
                raise ValidationError("این سفارش در وضعیت قابل پرداخت نیست.")
            amount_rial = int(order.total_amount) * 10
            if amount_rial < ZIBAL_MIN_AMOUNT_RIAL:
                raise ValidationError("مبلغ سفارش کمتر از حداقل مبلغ مجاز درگاه است.")
            if order.payments.filter(status=Payment.PaymentStatus.SUCCESS).exists():
                raise ValidationError("این سفارش قبلاً پرداخت شده است.")
            existing_pending = order.payments.filter(status=Payment.PaymentStatus.PENDING).first()
            if existing_pending:
                if existing_pending.transaction_id:
                    pay_url = f"{ZIBAL_START_URL}/{existing_pending.transaction_id}"
                    return existing_pending, pay_url
                raise ValidationError("درخواست پرداخت قبلی نتیجه مشخصی ندارد؛ امکان ثبت درخواست جدید وجود ندارد.")
            hard_limit = order.created_at + timedelta(hours=1)
            if order.expires_at < hard_limit:
                new_expiry = min(
                    max(order.expires_at, now + timedelta(minutes=15)),
                    hard_limit,
                )
                if new_expiry != order.expires_at:
                    order.expires_at = new_expiry
                    order.save(update_fields=["expires_at", "updated_at"])
            payment = Payment.objects.create(
                order=order,
                amount=order.total_amount,
                gateway="zibal",
                status=Payment.PaymentStatus.PENDING,
                request_state=Payment.RequestState.SUBMITTING,
            )
            callback_parts = urlsplit(settings.ZIBAL_CALLBACK_URL)
            callback_query = dict(parse_qsl(callback_parts.query))
            callback_query["payment_id"] = str(payment.id)
            callback_url = urlunsplit((
                callback_parts.scheme,
                callback_parts.netloc,
                callback_parts.path,
                urlencode(callback_query),
                callback_parts.fragment,
            ))
        payload = {
            "merchant": merchant,
            "amount": amount_rial,
            "callbackUrl": callback_url,
            "description": f"پرداخت سفارش شماره {order.order_number}",
            "orderId": str(order.order_number),
            "mobile": order.address.recipient_phone,
        }
        try:
            response = requests.post(
                f"{ZIBAL_API_URL}/request",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.exceptions.RequestException, ValueError) as exc:
            ZibalService._update_request_state(
                payment.pk,
                Payment.RequestState.UNKNOWN,
                message="نتیجه درخواست پرداخت مشخص نیست؛ بررسی مجدد لازم است.",
                code="req_unknown",
            )
            logger.warning("درخواست پرداخت %s نامشخص ماند: %s", payment.pk, exc)
            raise ValidationError("نتیجه درخواست پرداخت مشخص نیست؛ لطفاً برای بررسی مجدد اقدام کنید.") from exc
        result, message, info = ZibalService._parse_response(data)
        if result is None:
            ZibalService._update_request_state(
                payment.pk,
                Payment.RequestState.UNKNOWN,
                message="پاسخ درخواست پرداخت فاقد کد وضعیت معتبر است.",
                code="req_unknown",
            )
            raise ValidationError("پاسخ درگاه معتبر نیست؛ نتیجه پرداخت نیاز به بررسی دارد.")
        if result != 100:
            if result in ZIBAL_REQUEST_REJECTED_RESULTS:
                ZibalService._update_request_state(
                    payment.pk,
                    Payment.RequestState.REJECTED,
                    message=message or "درگاه درخواست پرداخت را نپذیرفت.",
                    code=result,
                    status=Payment.PaymentStatus.FAILED,
                )
                raise ValidationError(
                    "درگاه پرداخت درخواست را نپذیرفت؛ لطفاً دوباره تلاش کنید."
                )
            ZibalService._update_request_state(
                payment.pk,
                Payment.RequestState.UNKNOWN,
                message=message or "کد پاسخ درخواست پرداخت ناشناخته است.",
                code=result,
            )
            raise ValidationError("پاسخ درگاه مشخص نیست؛ پرداخت نیاز به بررسی دارد.")
        track_id = info.get("trackId")
        try:
            normalized_track_id = int(track_id)
            if normalized_track_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            ZibalService._update_request_state(
                payment.pk,
                Payment.RequestState.UNKNOWN,
                message="شناسه تراکنش در پاسخ درگاه معتبر نیست.",
                code=result,
            )
            raise ValidationError("شناسه تراکنش در پاسخ درگاه معتبر نیست.")
        payment = ZibalService._update_request_state(
            payment.pk,
            Payment.RequestState.ACCEPTED,
            message=message,
            code=result,
            transaction_id=str(normalized_track_id),
        )
        return payment, f"{ZIBAL_START_URL}/{normalized_track_id}"

    @staticmethod
    def verify_payment(payment_id, track_id):
        try:
            payment = Payment.objects.select_related("order").get(pk=payment_id, transaction_id=str(track_id), gateway="zibal")
        except Payment.DoesNotExist:
            raise ValidationError("پرداخت یافت نشد.")
        if payment.status == Payment.PaymentStatus.SUCCESS:
            ZibalService.complete_paid_payment(payment.pk)
            return Payment.objects.get(pk=payment.pk)
        try:
            normalized_track_id = int(track_id)
            if normalized_track_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError("شناسه تراکنش معتبر نیست.")
        payload = {
            "merchant": ZibalService._merchant(),
            "trackId": normalized_track_id,
        }
        try:
            response = requests.post(f"{ZIBAL_API_URL}/verify", json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
        except (requests.exceptions.RequestException, ValueError) as exc:
            ZibalService._mark_payment_for_review(payment.pk, "نتیجه تأیید پرداخت به دلیل خطای ارتباطی مشخص نشد.")
            logger.warning("تأیید پرداخت %s نامشخص ماند: %s", payment.pk, exc)
            raise ValidationError("نتیجه پرداخت مشخص نشد؛ بررسی مجدد لازم است.") from exc
        result, message, info = ZibalService._parse_response(data)
        if result is None:
            ZibalService._mark_payment_for_review(payment.pk, "پاسخ Verify فاقد کد وضعیت معتبر است.", code="invalid_response")
            raise ValidationError("پاسخ Verify معتبر نیست؛ بررسی مجدد لازم است.")
        if result == 201:
            ZibalService._mark_payment_for_review(
                payment.pk,
                message or "پرداخت قبلاً در زیبال تأیید شده؛ نتیجه Inquiry در حال بررسی است.",
                code=201,
            )
        if result in (201, 202):
            inquiry_result, inquiry_message, inquiry_info = (
                ZibalService.inquiry_payment(payment_id=payment.pk, track_id=normalized_track_id)
            )
            if inquiry_result != 100:
                return Payment.objects.get(pk=payment.pk)
            try:
                inquiry_status = int(inquiry_info.get("status"))
            except (TypeError, ValueError):
                inquiry_status = None

            # Payment is confirmed by Zibal.
            if inquiry_status == 1:
                info = inquiry_info
                result = 100
                message = inquiry_message

            # Definitive user-cancelled or payment-failed statuses.
            elif inquiry_status is not None and 3 <= inquiry_status <= 6:
                with transaction.atomic():
                    locked = Payment.objects.select_for_update().get(pk=payment.pk)
                    if locked.status == Payment.PaymentStatus.PENDING:
                        locked.status = Payment.PaymentStatus.FAILED
                    if locked.status != Payment.PaymentStatus.SUCCESS:
                        locked.gateway_response_code = f"s{inquiry_status}"
                        locked.gateway_response_message = (
                            inquiry_message or
                            f"وضعیت نهایی تراکنش در زیبال: {inquiry_status}"
                        )[:255]
                        locked.save(update_fields=[
                            "status",
                            "gateway_response_code",
                            "gateway_response_message",
                            "updated_at",
                        ])
                return Payment.objects.get(pk=payment.pk)

            # Pending, paid-unconfirmed, internal error, refund or unknown.
            else:
                ZibalService._mark_payment_for_review(
                    payment.pk,
                    f"وضعیت تراکنش در Inquiry نیازمند بررسی مجدد است: {inquiry_status}",
                    code=f"s{inquiry_status}" if inquiry_status is not None else "inq",
                )
                return Payment.objects.get(pk=payment.pk)
        if result != 100:
            ZibalService._mark_payment_for_review(payment.pk, message or "پاسخ Verify زیبال موفق نبود.", code=result)
            return Payment.objects.get(pk=payment.pk)
        try:
            verified_status = int(info.get("status"))
        except (TypeError, ValueError):
            verified_status = None
        if verified_status != 1:
            ZibalService._mark_payment_for_review(
                payment.pk,"وضعیت تراکنش در پاسخ Verify تأییدشده نیست؛ بررسی مالی لازم است.", code=result)
            return Payment.objects.get(pk=payment.pk)
        expected_amount = int(payment.amount) * 10
        try:
            verified_amount = int(info.get("amount"))
        except (TypeError, ValueError):
            verified_amount = None
        ref_number = info.get("refNumber")
        expected_order_id = str(payment.order.order_number)
        returned_order_id = str(info.get("orderId") or "")
        if (
            verified_amount != expected_amount
            or not ref_number
            or returned_order_id != expected_order_id
        ):
            ZibalService._mark_payment_for_review(
                payment.pk,"مبلغ، شماره سفارش یا کد رهگیری پاسخ درگاه معتبر نیست؛ تطبیق مالی لازم است.",
                code=result,
            )
            raise ValidationError("اطلاعات تأیید پرداخت با سفارش مطابقت ندارد.")
        paid_at = parse_datetime(str(info.get("paidAt") or ""))
        if paid_at is None:
            ZibalService._mark_payment_for_review(
                payment.pk,
                "زمان پرداخت در پاسخ درگاه معتبر نیست؛ تطبیق مالی لازم است.",
                code=result,
            )
            raise ValidationError("زمان پرداخت در پاسخ درگاه معتبر نیست.")
        if timezone.is_naive(paid_at):
            paid_at = timezone.make_aware(paid_at)
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=payment.order_id)
            locked = Payment.objects.select_for_update().get(pk=payment.pk)
            if locked.status != Payment.PaymentStatus.SUCCESS:
                now = timezone.now()
                reservation_active = (
                    order.expires_at > now
                    or locked.created_at >= now - Order.PAYMENT_GRACE
                )
                locked.status = Payment.PaymentStatus.SUCCESS
                locked.tracking_code = str(ref_number)
                locked.paid_at = paid_at
                locked.gateway_response_code = str(result)
                locked.gateway_response_message = message
                if order.status == Order.OrderStatus.PENDING and reservation_active:
                    order.status = Order.OrderStatus.PROCESSING
                    order.save(update_fields=["status", "updated_at"])
                else:
                    locked.gateway_response_message = ("پرداخت موفق است اما وضعیت سفارش نیازمند بررسی دستی است.")
                locked.save(update_fields=[
                    "status",
                    "tracking_code",
                    "paid_at",
                    "gateway_response_code",
                    "gateway_response_message",
                    "updated_at",
                ])
        payment.refresh_from_db()
        if payment.status == Payment.PaymentStatus.SUCCESS:
            ZibalService.complete_paid_payment(payment.pk)
        return payment

    @staticmethod
    def complete_paid_payment(payment_id):
        with transaction.atomic():
            payment_order_id = Payment.objects.values_list("order_id", flat=True).get(pk=payment_id)
            order = Order.objects.select_for_update().get(pk=payment_order_id)
            payment = Payment.objects.select_for_update().get(pk=payment_id)
            if payment.status != Payment.PaymentStatus.SUCCESS:
                return payment
            if order.status != Order.OrderStatus.PROCESSING:
                logger.error(
                    "پرداخت %s موفق است اما سفارش %s در وضعیت %s است؛ "
                    "تکمیل سفارش نیازمند بازیابی است.",
                    payment.pk,
                    order.pk,
                    order.status,
                )
                return payment
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
                    "shipping_amount": 0,
                    "total_amount": order.subtotal - order.discount_amount,
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
        return payment
