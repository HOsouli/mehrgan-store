# Secure 6-digit code using Secrets
# OTP validity: 2 minutes
# One request per number every 120 seconds
# Any existing active OTP for the same number is marked as `is_used=True` upon a new request
# The OTP code is never returned in the API response
# Stricter rate limiting can be implemented later using DRF Throttling.

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



class OTPService:
    OTP_EXPIRY_SECONDS = 120
    REQUEST_COOLDOWN_SECONDS = 120
    MAX_ATTEMPTS = 6
    BLOCK_DURATION_SECONDS = 300

    @staticmethod
    def request_otp(phone_number):
        now = timezone.now()
        last_otp = OTP.objects.filter(phone_number=phone_number).order_by("-created_at").first()

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
        if settings.DEBUG:
            print(f"OTP for {phone_number}: {code}")
        otp = OTP.objects.create(
            phone_number=phone_number,
            code=make_password(code),
            expires_at=now + timedelta(seconds=OTPService.OTP_EXPIRY_SECONDS)
        )
        return otp

    @staticmethod
    def verify_otp(phone_number, code):
        now = timezone.now()
        otp = OTP.objects.filter(phone_number=phone_number, is_used=False).order_by("-created_at").first()
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
            otp.save()
            raise ValidationError({
                "code": "کد تأیید واردشده صحیح نیست."
            })
        with transaction.atomic():
            otp.is_used = True
            otp.save(update_fields=("is_used",))
            user, _ = CustomUser.objects.get_or_create(phone_number=phone_number)
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
