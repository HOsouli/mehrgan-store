from django.db import models
from uuid import uuid4
from django.core.exceptions import ValidationError
import re
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.utils import timezone


def mobile_validate(value):
    pattern = r"09\d{9}"
    if not re.fullmatch(pattern, value):
        raise ValidationError("شماره موبایل معتبر نیست. مثال: 09123456789")
    return value


# Manage User and Superuser creation for Custom User
class CustomUserManager(BaseUserManager):

    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("شماره موبایل را وارد کنید")
        user = self.model(phone_number=phone_number, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(phone_number, password, **extra_fields)


# Main project user; AbstractBaseUser for custom authentication and PermissionsMixin for using Django Permissions and Groups
class CustomUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    phone_number = models.CharField(max_length=11, unique=True, validators=[mobile_validate], verbose_name="شماره موبایل")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    is_verified = models.BooleanField(default=False, verbose_name="تأیید شده")
    is_staff = models.BooleanField(default=False, verbose_name="دسترسی ادمین")
    date_joined = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ عضویت")

    objects = CustomUserManager()
    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"

    def __str__(self):
        return self.phone_number


# Maintain OTP to verify mobile number and control expiration and failed attempts
class OTP(models.Model):
    phone_number = models.CharField(max_length=11, validators=[mobile_validate], verbose_name="شماره موبایل")
    code = models.CharField(max_length=150, verbose_name="کد تایید")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    expires_at = models.DateTimeField(verbose_name="زمان انقضا")
    is_used = models.BooleanField(default=False, verbose_name="استفاده شده")
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name="تعداد تلاش")
    blocked_until = models.DateTimeField(blank=True, null=True, verbose_name="زمان پایان مسدودسازی")

    def is_valid(self):
        now = timezone.now()
        if self.blocked_until and self.blocked_until > now:
            return False
        return not self.is_used and now < self.expires_at

    class Meta:
        verbose_name = "کد تأیید (OTP)"
        verbose_name_plural = "کدهای تأیید (OTP)"

    def __str__(self):
        return f"{self.phone_number} - {self.created_at}"
