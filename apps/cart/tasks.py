import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from .models import Cart


logger = logging.getLogger(__name__)

GUEST_CART_TTL_DAYS = 60
BATCH_SIZE = 3000
MAX_BATCHES = 100


@shared_task(name="apps.cart.tasks.delete_expired_guest_carts")
def delete_expired_guest_carts() -> int:
    """Delete guest carts inactive for at least 60 days."""
    cutoff = timezone.now() - timedelta(days=GUEST_CART_TTL_DAYS)
    total_deleted = 0
    for _ in range(MAX_BATCHES):
        expired_ids = list(
            Cart.objects.filter(user__isnull=True, updated_at__lte=cutoff)
            .order_by("updated_at")
            .values_list("id", flat=True)[:BATCH_SIZE]
        )
        if not expired_ids:
            break
        _, per_model = Cart.objects.filter(id__in=expired_ids, user__isnull=True, updated_at__lte=cutoff).delete()
        deleted = per_model.get(Cart._meta.label, 0)
        if deleted == 0:
            break
        total_deleted += deleted
    logger.info("Deleted %s expired guest carts", total_deleted)
    return total_deleted

