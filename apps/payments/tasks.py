import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from apps.orders.services import OrderService
from .models import Payment
from .services import ZarinpalService

logger = logging.getLogger(__name__)


@shared_task(name="apps.payments.tasks.reverify_pending_payments")
def reverify_pending_payments(batch_size=50):
    """Re-verify payments whose verify result was lost because of a network error."""
    now = timezone.now()
    rows = list(
        Payment.objects.filter(
            status=Payment.PaymentStatus.PENDING,
            gateway_response_code="net",
            transaction_id__isnull=False,
            updated_at__lte=now - timedelta(minutes=5),
            created_at__gte=now - OrderService.PAYMENT_GRACE,
        )
        .exclude(transaction_id="")
        .order_by("created_at")
        .values_list("id", "transaction_id")[:batch_size]
    )
    checked = 0
    for payment_id, authority in rows:
        try:
            ZarinpalService.verify_payment(payment_id=payment_id, authority=authority)
            checked += 1
        except Exception:
            logger.exception("بازبینی پرداخت %s ناموفق بود", payment_id)
    logger.info("Re-verified %s pending payments", checked)
    return checked
