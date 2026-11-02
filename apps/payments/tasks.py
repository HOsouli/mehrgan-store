import logging
from datetime import timedelta
from celery import shared_task
from django.core.cache import cache
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from apps.invoices.models import Invoice
from apps.orders.models import Order
from apps.shipments.models import Shipment
from .models import Payment
from .services import ZarinpalService

logger = logging.getLogger(__name__)

LOOKBACK = timedelta(hours=24)
REVIEW_WINDOW = timedelta(days=7)
FAIL_AFTER = timedelta(minutes=30)
RECHECK_AFTER = timedelta(minutes=5)
UNSETTLED = (Payment.PaymentStatus.PENDING, Payment.PaymentStatus.CANCELLED)


def _touch(payment_id, statuses):
    """It postpones the review so that a problematic payment does not hold up the others."""
    Payment.objects.filter(pk=payment_id, status__in=statuses).update(updated_at=timezone.now())

def _close(payment_id, state, message):
    Payment.objects.filter(pk=payment_id, status__in=UNSETTLED).update(
        status=Payment.PaymentStatus.FAILED,
        gateway_response_code=state,
        gateway_response_message=message[:255],
        updated_at=timezone.now(),
    )

def _first_time(key):
    """To prevent duplicate logs, a log entry is recorded if the cache is corrupted."""
    try:
        return cache.add(key, 1, int(REVIEW_WINDOW.total_seconds()))
    except Exception:
        return True

def _recheck_unsettled(now, batch_size):
    rows = list(
        Payment.objects.filter(
            status__in=UNSETTLED,
            transaction_id__isnull=False,
            updated_at__lte=now - RECHECK_AFTER,
            created_at__gte=now - LOOKBACK,
        )
        .exclude(transaction_id="")
        .order_by("updated_at")
        .values_list("id", "transaction_id", "created_at")[:batch_size]
    )
    for payment_id, authority, created_at in rows:
        try:
            state = ZarinpalService.inquire_payment(authority)
            if state in ("PAID", "VERIFIED"):
                ZarinpalService.verify_payment(payment_id=payment_id, authority=authority)
            elif state == "REVERSED":
                logger.warning("پرداخت %s توسط درگاه برگشت خورده است.", payment_id)
                _close(payment_id, "REVERSED", "برگشت وجه اعلام‌شده توسط درگاه؛ نیازمند تطبیق مالی.")
            elif state == "FAILED" and now - created_at >= FAIL_AFTER:
                _close(payment_id, "FAILED", "استعلام درگاه: تراکنش ناموفق است.")
            # IN_BANK، پاسخ نامشخص یا خطای شبکه: وضعیت بدون تغییر می‌ماند
        except Exception:
            logger.exception("بازبینی پرداخت %s ناموفق بود", payment_id)
        finally:
            _touch(payment_id, UNSETTLED)
    return len(rows)

def _complete_paid_orders(now, batch_size):
    rows = list(
        Payment.objects.filter(
            status=Payment.PaymentStatus.SUCCESS,
            order__status=Order.OrderStatus.PROCESSING,
            updated_at__lte=now - RECHECK_AFTER,
        )
        .annotate(
            has_invoice=Exists(Invoice.objects.filter(order=OuterRef("order_id"))),
            has_shipment=Exists(Shipment.objects.filter(order=OuterRef("order_id"))),
        )
        .filter(Q(has_invoice=False) | Q(has_shipment=False))
        .order_by("updated_at")
        .values_list("id", "transaction_id")[:batch_size]
    )
    for payment_id, authority in rows:
        try:
            ZarinpalService.verify_payment(payment_id=payment_id, authority=authority)
        except Exception:
            logger.exception("تکمیل سفارش پرداخت %s ناموفق بود", payment_id)
        finally:
            _touch(payment_id, (Payment.PaymentStatus.SUCCESS,))
    return len(rows)

def _report_manual_review(now):
    try:
        since = now - REVIEW_WINDOW
        late_paid = list(
            Payment.objects.filter(
                status=Payment.PaymentStatus.SUCCESS,
                order__status=Order.OrderStatus.CANCELLED,
                paid_at__gte=since,
            ).values_list("id", flat=True)
        )
        reversed_ids = list(
            Payment.objects.filter(
                status=Payment.PaymentStatus.FAILED,
                gateway_response_code="REVERSED",
                updated_at__gte=since,
            ).values_list("id", flat=True)
        )
        for payment_id in late_paid:
            if _first_time(f"payment-review-late-{payment_id}"):
                logger.error("پرداخت %s موفق است اما سفارش لغو شده؛ بررسی دستی و برگشت وجه لازم است.", payment_id)
        for payment_id in reversed_ids:
            if _first_time(f"payment-review-reversed-{payment_id}"):
                logger.error("پرداخت %s برگشت وجه اعلام‌شده توسط درگاه دارد؛ نیازمند تطبیق مالی.", payment_id)
    except Exception:
        logger.exception("گزارش بررسی دستی ناموفق بود")

@shared_task(name="apps.payments.tasks.reverify_pending_payments")
def reverify_pending_payments(batch_size=10):
    now = timezone.now()
    checked = _recheck_unsettled(now, batch_size)
    completed = _complete_paid_orders(now, batch_size)
    _report_manual_review(now)
    logger.info("Rechecked %s unsettled, completed %s paid", checked, completed)
    return checked + completed
