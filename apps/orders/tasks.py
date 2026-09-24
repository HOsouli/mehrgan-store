import logging
from celery import shared_task
from .services import OrderService


logger = logging.getLogger(__name__)

@shared_task(name="apps.orders.tasks.cancel_expired_orders")
def cancel_expired_orders() -> int:
    """Automatic cancellation of expired orders — executed by Celery Beat every minute."""
    count = OrderService.cancel_expired_orders()
    logger.info("Cancelled %s expired orders", count)
    return count
