import logging

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from .sms import SMSIrService, SMSIrPermanentError, SMSIrTransientError

logger = logging.getLogger(__name__)


def deliver_otp_sms(phone_number: str, code: str) -> bool:
    """Synchronous sending (without Celery) — for fallback when the broker is unavailable."""
    return SMSIrService.send_otp(phone_number, code)


@shared_task(
    bind=True,
    name="apps.accounts.tasks.send_otp_sms",
    max_retries=2,
    default_retry_delay=20,
    acks_late=True,
    ignore_result=True,
)
def send_otp_sms(self, phone_number: str, code: str) -> bool:
    """
    Asynchronous OTP code sending.
    - Permanent error (invalid key/template): do not retry.
    - Temporary error (network/429/5xx): retry with exponential backoff.
    """
    try:
        deliver_otp_sms(phone_number, code)
        return True
    except SMSIrPermanentError as exc:
        logger.error("OTP SMS permanently failed for %s: %s", phone_number, exc)
        return False
    except SMSIrTransientError as exc:
        # 20، 40، 80 Second
        countdown = 20 * (2 ** self.request.retries)
        try:
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            logger.error(
                "Gave up sending OTP SMS to %s after %s retries.",
                phone_number,
                self.request.retries,
            )
            return False

