# Secure 6-digit code using Secrets
# OTP validity: 2 minutes
# One request per number every 120 seconds
# Any existing active OTP for the same number is marked as `is_used=True` upon a new request
# The OTP code is never returned in the API response
# Stricter rate limiting can be implemented later using DRF Throttling.

import hashlib
from django.db import connection
import secrets
from datetime import timedelta
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import CustomUser, OTP
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.db import transaction
from django.contrib.auth.hashers import make_password, check_password
from django.conf import settings
from .tasks import send_otp_sms, deliver_otp_sms
import logging


logger = logging.getLogger(__name__)



class OTPService:
    OTP_EXPIRY_SECONDS = 120
    REQUEST_COOLDOWN_SECONDS = 120
    MAX_ATTEMPTS = 6
    BLOCK_DURATION_SECONDS = 300

    @staticmethod
    def _acquire_phone_lock(phone_number):
        lock_key = int.from_bytes(
            hashlib.sha256(phone_number.encode("utf-8")).digest()[:8], byteorder="big", signed=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s);", [lock_key])

    @staticmethod
    def request_otp(phone_number):
        now = timezone.now()
        with transaction.atomic():
            OTPService._acquire_phone_lock(phone_number)
            last_otp = (OTP.objects.filter(phone_number=phone_number).order_by("-created_at").first())

            # Check whether the phone number is temporarily blocked
            if last_otp and last_otp.blocked_until and last_otp.blocked_until > now:
                remaining_seconds = int((last_otp.blocked_until - now).total_seconds())
                raise ValidationError({
                    "phone_number": f"این شماره موقتا مسدود شده است لطفا {remaining_seconds} ثانیه دیگر تلاش کنید."
                })

            # Check request cooldown
            if last_otp:
                elapsed_seconds = (now - last_otp.created_at).total_seconds()
                if elapsed_seconds < OTPService.REQUEST_COOLDOWN_SECONDS:
                    remaining_seconds = int(OTPService.REQUEST_COOLDOWN_SECONDS - elapsed_seconds)
                    raise ValidationError({
                        "phone_number":f"لطفا تا {remaining_seconds} ثانیه دیگر برای درخواست مجدد صبر کنید."
                    })

            # Invalidate previous active OTPs
            OTP.objects.filter(phone_number=phone_number, is_used=False).update(is_used=True)
            code = f"{secrets.randbelow(1_000_000):06d}"
            otp = OTP.objects.create(
                phone_number=phone_number,
                code=make_password(code),
                expires_at=now + timedelta(seconds=OTPService.OTP_EXPIRY_SECONDS)
            )
            try:
                sent = OTPService._dispatch_otp_sms(phone_number, code)
            except Exception:
                logger.exception("خطای غیرمنتظره در ارسال OTP برای %s", phone_number)
                sent = False
            if not sent:
                otp.delete()   # ← تضمین میکند رکورد یتیم نماند و شماره در cooldown گیر نکند
                raise ValidationError({
                    "phone_number": "ارسال پیامک ناموفق بود. لطفاً دوباره تلاش کنید."
                })
            return otp

    @staticmethod
    def _dispatch_otp_sms(phone_number, code):
        if getattr(settings, "OTP_DEV_ECHO", False):
            logger.warning("OTP DEV ECHO — phone: %s, code: %s", phone_number, code)
            return True
        try:
            send_otp_sms.delay(phone_number, code)
            return True
        except Exception:
            logger.exception("Celery در دسترس نیست؛ ارسال همگام OTP برای %s", phone_number)
        try:
            return deliver_otp_sms(phone_number, code)
        except Exception:
            logger.exception("ارسال همگام OTP شکست خورد برای %s", phone_number)
            return False

    @staticmethod
    def verify_otp(phone_number, code):
        now = timezone.now()
        with transaction.atomic():
            OTPService._acquire_phone_lock(phone_number)
            otp = (OTP.objects .select_for_update().filter(phone_number=phone_number, is_used=False).order_by("-created_at").first())
            if not otp:
                raise ValidationError({
                    "code": "کد تائید معتبر نیست"
                })

            # Check whether the phone number is temporarily blocked
            if otp.blocked_until and otp.blocked_until > now:
                remaining_seconds = int((otp.blocked_until - now).total_seconds())
                raise ValidationError({
                    "code": f"این شماره موقتا مسدود شده است لطفا {remaining_seconds} ثانیه دیگر تلاش کنید."
                })

            # Check whether the OTP has expired
            if otp.expires_at <= now:
                raise ValidationError({
                    "otp": "کد تائید منقضی شده است"
                })

            # Check whether the entered code is correct
            if not check_password(code, otp.code):
                otp.attempts += 1
                if otp.attempts >= OTPService.MAX_ATTEMPTS:
                    otp.blocked_until = now + timedelta(seconds=OTPService.BLOCK_DURATION_SECONDS)
                    otp.is_used = True
                otp.save(update_fields=["attempts", "blocked_until", "is_used"])
                raise ValidationError({
                    "code": "کد تأیید واردشده صحیح نیست."
                })
            otp.is_used = True
            otp.save(update_fields=("is_used",))
            user, _ = CustomUser.objects.get_or_create(phone_number=phone_number)
            if not user.is_active:
                raise ValidationError({
                    "phone_number": "حساب کاربری شما غیرفعال است. لطفاً با پشتیبانی تماس بگیرید."
                })
            if not user.is_verified:
                user.is_verified = True
                user.save(update_fields=("is_verified",))

            refresh = RefreshToken.for_user(user)
            access = refresh.access_token
            return {
                "access": str(access),
                "refresh": str(refresh),
            }


class AuthService:

    @staticmethod
    def logout(refresh_token):
        try:
            refresh = RefreshToken(refresh_token)
            refresh.blacklist()
        except TokenError:
            raise ValidationError({
                "refresh": "توکن خروج معتبر نیست."
            })
