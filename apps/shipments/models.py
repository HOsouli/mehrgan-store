from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import models
from apps.orders.models import Order


class Shipment(models.Model):

    class ShipmentMethod(models.TextChoices):
        POST = "post", "پست"
        COURIER = "courier", "پیک"
        OTHER = "other", "سایر"

    class ShipmentStatus(models.TextChoices):
        PENDING = "pending", "در انتظار ارسال"
        PROCESSING = "processing", "در حال آماده‌سازی"
        SHIPPED = "shipped", "ارسال شده"
        DELIVERED = "delivered", "تحویل داده شده"
        CANCELLED = "cancelled", "لغو شده"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="shipment", verbose_name="سفارش")
    method = models.CharField(max_length=20, choices=ShipmentMethod.choices, verbose_name="روش ارسال")
    carrier = models.CharField(max_length=100, verbose_name="شرکت/سرویس حمل")
    tracking_code = models.CharField(max_length=100, blank=True, verbose_name="کد رهگیری")
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="هزینه ارسال")
    status = models.CharField(max_length=20, choices=ShipmentStatus.choices, default=ShipmentStatus.PENDING, verbose_name="وضعیت ارسال")
    shipped_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان ارسال")
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تحویل")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    def clean(self):
        super().clean()
        if self.shipping_cost < 0:
            raise ValidationError({
                "shipping_cost": "هزینه ارسال نمی‌تواند کمتر از صفر باشد."
            })
        if self.status == self.ShipmentStatus.SHIPPED:
            if not self.tracking_code:
                raise ValidationError({
                    "tracking_code": "برای مرسوله ارسال‌شده، کد رهگیری الزامی است."
                })
            if not self.shipped_at:
                raise ValidationError({
                    "shipped_at": "برای مرسوله ارسال‌شده، زمان ارسال الزامی است."
                })
        if self.status == self.ShipmentStatus.DELIVERED:
            if not self.shipped_at:
                raise ValidationError({
                    "shipped_at": "برای مرسوله تحویل‌شده، زمان ارسال الزامی است."
                })
            if not self.delivered_at:
                raise ValidationError({
                    "delivered_at": "برای مرسوله تحویل‌شده، زمان تحویل الزامی است."
                })

    class Meta:
        verbose_name = "مرسوله"
        verbose_name_plural = "مرسوله‌ها"
        ordering = ("-created_at",)

    def __str__(self):
        return f"شمارش سفارش: {self.order.order_number} - {self.get_status_display()}"

