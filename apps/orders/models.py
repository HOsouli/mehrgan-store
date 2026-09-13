from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import models
from apps.accounts.models import CustomUser, mobile_validate
from apps.catalog.models import Product
from apps.discounts.models import Discount
from django.core.validators import MinValueValidator, RegexValidator
from django.db.models.expressions import RawSQL


postal_code_validator = RegexValidator(regex=r"^\d{10}$", message="کد پستی باید دقیقاً ده رقم باشد.")


class Order(models.Model):

    class OrderStatus(models.TextChoices):
        PENDING = "pending", "در انتظار"
        CONFIRMED = "confirmed", "تأیید شده"
        PROCESSING = "processing", "در حال پردازش"
        SHIPPED = "shipped", "ارسال شده"
        DELIVERED = "delivered", "تحویل داده شده"
        CANCELLED = "cancelled", "لغو شده"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="orders", verbose_name="کاربر")
    order_number = models.PositiveIntegerField(
        db_default=RawSQL("nextval('orders_order_number_seq')", []),
        unique=True,
        editable=False,
        verbose_name="شماره سفارش"
    )
    status = models.CharField( max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING, verbose_name="وضعیت سفارش")
    subtotal = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="مبلغ کالاها")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="مبلغ تخفیف")
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="هزینه ارسال")
    total_amount = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="مبلغ نهایی")
    discount = models.ForeignKey(Discount, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders", verbose_name="تخفیف")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    def clean(self):
        super().clean()
        if self.subtotal < 0:
            raise ValidationError({
                "subtotal": "مبلغ کالاها نمی‌تواندکمتر از صفر باشد."
            })
        if self.discount_amount < 0:
            raise ValidationError({
                "discount_amount": "مبلغ تخفیف نمی‌تواند کمتر از صفر باشد."
            })
        if self.shipping_amount < 0:
            raise ValidationError({
                "shipping_amount": "هزینه ارسال نمی‌تواند کمتر از صفر باشد."
            })
        if self.total_amount < 0:
            raise ValidationError({
                "total_amount": "مبلغ نهایی نمی‌تواند کمتر از صفر باشد."
            })

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ("-created_at",)

    def __str__(self):
        return str(self.order_number)


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items", verbose_name="سفارش")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items", verbose_name="محصول")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name="تعداد")
    unit_price = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="قیمت واحد در زمان سفارش")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="مبلغ تخفیف")
    total_price = models.DecimalField( max_digits=12, decimal_places=0, verbose_name="مبلغ نهایی آیتم")

    def clean(self):
        super().clean()
        if self.unit_price < 0:
            raise ValidationError({
                "unit_price": "قیمت واحد نمی‌تواند کمتر از صفر باشد."
            })
        if self.discount_amount < 0:
            raise ValidationError({
                "discount_amount": "مبلغ تخفیف نمی‌تواند کمتر از صفر باشد."
            })
        if self.total_price < 0:
            raise ValidationError({
                "total_price": "مبلغ نهایی نمی‌تواند کمتر از صفر باشد."
            })

    class Meta:
        verbose_name = "آیتم سفارش"
        verbose_name_plural = "آیتم‌های سفارش"

    def __str__(self):
        return f"{self.order.order_number} - {self.product.name}"


class OrderAddress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="address", verbose_name="سفارش")  # Each order has exactly one delivery address.
    recipient_name = models.CharField(max_length=100, verbose_name="نام گیرنده")
    province = models.CharField(max_length=100, verbose_name="استان")
    city = models.CharField(max_length=100, verbose_name="شهر")
    address = models.TextField(verbose_name="آدرس")
    postal_code = models.CharField(max_length=10, validators=[postal_code_validator], verbose_name="کد پستی")
    recipient_phone = models.CharField(max_length=11, validators=[mobile_validate], verbose_name="شماره تماس گیرنده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "آدرس سفارش"
        verbose_name_plural = "آدرس‌های سفارش"

    def __str__(self):
        return f"{self.order.order_number} - {self.city}"

