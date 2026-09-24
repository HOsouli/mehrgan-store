import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SMSIrError(Exception):
    """خطای پایه سرویس پیامک."""


class SMSIrPermanentError(SMSIrError):
    """کلید API/قالب/payload غلط — تلاش مجدد بی‌فایده است."""


class SMSIrTransientError(SMSIrError):
    """شبکه، 429 یا 5xx — ارزش تلاش مجدد دارد."""


class SMSIrService:
    BASE_URL = "https://api.sms.ir/v1/send/verify"
    TIMEOUT = 10

    @classmethod
    def send_otp(cls, phone_number: str, code: str) -> bool:
        api_key = getattr(settings, "SMSIR_API_KEY", "")
        template_id = getattr(settings, "SMSIR_TEMPLATE_ID", None)
        param_name = getattr(settings, "SMSIR_OTP_PARAM_NAME", "CODE")

        if not api_key or not template_id:
            raise SMSIrPermanentError(
                "SMSIR_API_KEY یا SMSIR_TEMPLATE_ID تنظیم نشده است."
            )

        # sms.ir شماره را بدون صفر ابتدایی می‌خواهد: 0912... -> 912...
        mobile = phone_number[1:] if phone_number.startswith("0") else phone_number

        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "mobile": mobile,
            "templateId": int(template_id),
            "parameters": [
                {
                    "name": param_name,
                    "value": str(code),
                }
            ],
        }

        try:
            resp = requests.post(
                cls.BASE_URL, json=payload, headers=headers, timeout=cls.TIMEOUT
            )
        except requests.Timeout as exc:
            raise SMSIrTransientError("Timeout در ارتباط با sms.ir") from exc
        except requests.RequestException as exc:
            raise SMSIrTransientError(f"خطای شبکه: {exc}") from exc

        if resp.status_code in (401, 403):
            raise SMSIrPermanentError(f"کلید API نامعتبر است (HTTP {resp.status_code})")
        if resp.status_code == 429 or resp.status_code >= 500:
            raise SMSIrTransientError(f"خطای موقت sms.ir (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise SMSIrPermanentError(
                f"درخواست رد شد (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise SMSIrTransientError("پاسخ غیر JSON از sms.ir") from exc

        if data.get("status") != 1:
            raise SMSIrPermanentError(f"sms.ir خطا برگرداند: {data.get('message')}")

        logger.info("OTP SMS sent to %s", phone_number)
        return True
