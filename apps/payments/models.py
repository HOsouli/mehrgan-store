from django.db import models
from uuid import uuid4
from apps.orders.models import Order
from django.core.exceptions import ValidationError


class Payment(models.Model):

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "در انتظار پرداخت"
        SUCCESS = "success", "موفق"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغو شده"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments", verbose_name="سفارش")
    amount = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="مبلغ پرداخت")
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, verbose_name="وضعیت پرداخت")
    gateway = models.CharField(max_length=50, verbose_name="درگاه پرداخت")
    transaction_id = models.CharField(max_length=100, blank=True, verbose_name="شناسه تراکنش")
    tracking_code = models.CharField(max_length=100, blank=True, verbose_name="کد رهگیری")
    gateway_response_code = models.CharField(max_length=10, blank=True, verbose_name="کد پاسخ درگاه")
    gateway_response_message = models.CharField(max_length=255, blank=True, verbose_name="پیام پاسخ درگاه")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پرداخت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    def clean(self):
        super().clean()
        if self.amount <= 0:
            raise ValidationError({
                "amount": "مبلغ پرداخت باید بیشتر از صفر باشد."
            })
        if self.status == self.PaymentStatus.SUCCESS:
            if not self.transaction_id:
                raise ValidationError({
                    "transaction_id": "برای پرداخت موفق، شناسه تراکنش الزامی است."
                })
            if not self.tracking_code:
                raise ValidationError({
                    "tracking_code": "برای پرداخت موفق، کد رهگیری الزامی است."
                })
            if not self.paid_at:
                raise ValidationError({
                    "paid_at": "برای پرداخت موفق، زمان پرداخت الزامی است."
                })

    class Meta:
        verbose_name = "پرداخت"
        verbose_name_plural = "پرداخت‌ها"
        ordering = ("-created_at",)

    def __str__(self):
        return f"شماره سفارش: {self.order.order_number} - مبلغ: {self.amount}"

