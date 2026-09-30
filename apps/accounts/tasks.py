import logging
from celery import shared_task
from .sms import SMSIrService, SMSIrPermanentError, SMSIrTransientError

logger = logging.getLogger(__name__)


def deliver_otp_sms(phone_number: str, code: str) -> bool:
    """Synchronous sending (without Celery) — for fallback when the broker is unavailable."""
    return SMSIrService.send_otp(phone_number, code)


@shared_task(
    bind=True,
    name="apps.accounts.tasks.send_otp_sms",
    autoretry_for=(SMSIrTransientError,),
    retry_backoff=20,
    retry_backoff_max=80,
    retry_jitter=False,
    max_retries=2,
    acks_late=True,
    ignore_result=True,
)
def send_otp_sms(self, phone_number: str, code: str) -> bool:
    """
    Asynchronous OTP code sending.
    - Permanent error (invalid key/template): do not retry.
    - Temporary error (network/429/5xx): retry automatically.
    """
    try:
        return deliver_otp_sms(phone_number, code)
    except SMSIrPermanentError as exc:
        logger.error(
            "OTP SMS permanently failed for %s: %s",
            phone_number,
            exc,
        )
        return False
