
import logging
from datetime import timedelta
import uuid
from celery import shared_task
from django.core.cache import cache
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from apps.invoices.models import Invoice
from apps.orders.models import Order
from apps.shipments.models import Shipment
from .models import Payment
from .services import ZibalService


logger = logging.getLogger(__name__)
LOOKBACK = timedelta(hours=24)
REVIEW_WINDOW = timedelta(days=7)
RECHECK_AFTER = timedelta(minutes=5)
UNSETTLED = (
    Payment.PaymentStatus.PENDING,
    Payment.PaymentStatus.CANCELLED,
)
LOCK_KEY = "payments:reverify_pending_payments:lock"
LOCK_TIMEOUT = 600


def _acquire_lock():
    token = uuid.uuid4().hex
    client = cache._cache.get_client(LOCK_KEY)
    acquired = client.set(LOCK_KEY, token, nx=True, ex=LOCK_TIMEOUT)
    return token if acquired else None


def _release_lock(token):
    client = cache._cache.get_client(LOCK_KEY)
    client.eval(
        """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        end
        return 0
        """,
        1,
        LOCK_KEY,
        token,
    )


def _touch(payment_id, statuses):
    """Postpone the next review attempt."""
    Payment.objects.filter(pk=payment_id, status__in=statuses,).update(updated_at=timezone.now())


def _first_time(key):
    """Prevent duplicate review logs."""
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
            gateway="zibal",
        )
        .exclude(transaction_id="")
        .order_by("updated_at")
        .values_list("id", "transaction_id")[:batch_size]
    )
    for payment_id, track_id in rows:
        try:
            ZibalService.verify_payment(payment_id=payment_id, track_id=track_id)
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
            gateway="zibal",
            updated_at__lte=now - RECHECK_AFTER,
        )
        .annotate(
            has_invoice=Exists(Invoice.objects.filter(order=OuterRef("order_id"))),
            has_shipment=Exists(Shipment.objects.filter(order=OuterRef("order_id"))),
        ).filter(Q(has_invoice=False) | Q(has_shipment=False)).order_by("updated_at").values_list("id", flat=True)[:batch_size]
    )
    for payment_id in rows:
        try:
            ZibalService.complete_paid_payment(payment_id)
        except Exception:
            logger.exception("تکمیل سفارش پرداخت‌شده %s ناموفق بود", payment_id)
        finally:
            _touch(payment_id, (Payment.PaymentStatus.SUCCESS,))
    return len(rows)


def _report_manual_review(now):
    try:
        late_paid = list(
            Payment.objects.filter(
                status=Payment.PaymentStatus.SUCCESS,
                order__status__in=(
                    Order.OrderStatus.PENDING,
                    Order.OrderStatus.CANCELLED,
                ),
                gateway="zibal",
            ).values_list("id", "order__status")
        )
        aged_unsettled = list(
            Payment.objects.filter(
                status__in=UNSETTLED,
                gateway="zibal",
                created_at__lte=now - LOOKBACK,
            ).values_list("id", "transaction_id")
        )
        previously_verified = list(
            Payment.objects.filter(
                status__in=UNSETTLED,
                gateway="zibal",
                gateway_response_code="201",
            ).values_list("id", "transaction_id")
        )
        for payment_id, track_id in previously_verified:
            if _first_time(f"payment-review-201-{payment_id}"):
                logger.error(
                    "پرداخت %s قبلاً در زیبال تأیید شده اما وضعیت محلی آن نامشخص است؛ "
                    "شناسه تراکنش: %s؛ تطبیق مالی لازم است.",
                    payment_id,
                    track_id,
                )
        for payment_id, order_status in late_paid:
            if _first_time(f"payment-review-late-{payment_id}"):
                logger.error(
                    "پرداخت %s موفق است اما سفارش در وضعیت %s قرار دارد؛ بررسی دستی لازم است.",
                    payment_id,
                    order_status,
                )
        for payment_id, track_id in aged_unsettled:
            if _first_time(f"payment-review-aged-{payment_id}"):
                logger.error(
                    "پرداخت %s بیش از ۲۴ ساعت نامشخص مانده است؛ شناسه تراکنش: %s؛ بررسی دستی لازم است.",
                    payment_id,
                    track_id or "ندارد",
                )
    except Exception:
        logger.exception("گزارش بررسی دستی ناموفق بود")



@shared_task(name="apps.payments.tasks.reverify_pending_payments")
def reverify_pending_payments(batch_size=10):
    token = _acquire_lock()
    if token is None:
        logger.info("Payment recheck skipped: another task is running.")
        return 0
    try:
        now = timezone.now()
        _report_manual_review(now)
        checked = _recheck_unsettled(now, batch_size)
        completed = _complete_paid_orders(now, batch_size)
        logger.info("Rechecked %s unsettled, completed %s paid", checked, completed)
        return checked + completed
    finally:
        try:
            _release_lock(token)
        except Exception:
            logger.exception("Failed to release payment recheck lock.")
