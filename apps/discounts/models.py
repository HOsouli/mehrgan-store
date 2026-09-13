from django.db import models
from uuid import uuid4
from apps.catalog.models import Product, Category, Brand
from django.core.exceptions import ValidationError
from apps.accounts.models import CustomUser


class Discount(models.Model):

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "درصدی"
        FIXED = "fixed", "مبلغ ثابت"

    class TargetType(models.TextChoices):
        ORDER = "order", "کل سفارش"
        PRODUCT = "product", "محصولات"
        CATEGORY = "category", "دسته بندی"
        BRAND = "brand", "برند"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    code = models.CharField(max_length=10, unique=True, verbose_name="کد تخفیف")
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices, verbose_name="نوع تخفیف")
    value = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="مقدار تخفیف")
    target_type = models.CharField(max_length=20, choices=TargetType.choices, verbose_name="محدوده تخفیف")
    products = models.ManyToManyField(Product, blank=True, related_name="discounts", verbose_name="محصولات")
    categories = models.ManyToManyField(Category, blank=True, related_name="discounts", verbose_name="دسته‌بندی‌ها")
    brands = models.ManyToManyField(Brand, blank=True, related_name="discounts", verbose_name="برندها")
    minimum_order_amount = models.DecimalField(max_digits=12, decimal_places=0, blank=True, null=True, verbose_name="حداقل مبلغ کل سبد")
    total_usage_limit = models.PositiveIntegerField(blank=True, null=True, verbose_name="سقف استفاده کل")
    per_user_limit = models.PositiveIntegerField(blank=True, null=True, verbose_name="سقف استفاده هر کاربر")
    starts_at = models.DateTimeField(verbose_name="تاریخ و زمان شروع")
    ends_at = models.DateTimeField(verbose_name="تاریخ و زمان پایان")
    is_active = models.BooleanField(default=False, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    def clean(self):
        super().clean()

        if self.value <= 0:
            raise ValidationError({
                "value": "مقدار تخفیف باید بیشتر از صفر باشد."
            })
        if self.discount_type == self.DiscountType.PERCENTAGE and self.value > 100:
            raise ValidationError({
                "value": "درصد تخفیف نمی‌تواند بیشتر از 100 باشد."
            })
        if self.minimum_order_amount is not None and self.minimum_order_amount <= 0:
            raise ValidationError({
                "minimum_order_amount": "حداقل مبلغ سبد باید بیشتر از صفر باشد."
            })
        if self.total_usage_limit is not None and self.total_usage_limit <= 0:
            raise ValidationError({
                "total_usage_limit": "سقف استفاده کل باید بیشتر از صفر باشد."
            })
        if self.per_user_limit is not None and self.per_user_limit <= 0:
            raise ValidationError({
                "per_user_limit": "سقف استفاده هر کاربر باید بیشتر از صفر باشد."
            })
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({
                "ends_at": "زمان پایان باید بعد از زمان شروع باشد."
            })

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "تخفیف"
        verbose_name_plural = "تخفیف‌ها"
        ordering = ("-created_at",)

    def __str__(self):
        return self.code

# __________________________________________________________
class CouponUsage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    user = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="coupon_usages", verbose_name="کاربر")
    discount = models.ForeignKey(Discount, on_delete=models.PROTECT, related_name="usages", verbose_name="تخفیف")
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="coupon_usages", verbose_name="سفارش")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان استفاده")

    class Meta:
        verbose_name = "استفاده از کد تخفیف"
        verbose_name_plural = "استفاده‌های کد تخفیف"
        constraints = [models.UniqueConstraint(
                fields=["discount", "order"],
                name="unique_discount_per_order"
            )
        ]

    def __str__(self):
        return f"{self.user.phone_number} - {self.discount.code}"






#     Discount
# ├── code
# ├── discount_type
# ├── value
# ├── target_type
# ├── products
# ├── categories
# ├── brands
# ├── minimum_order_amount
# ├── total_usage_limit
# ├── per_user_limit
# ├── starts_at
# ├── ends_at
# ├── is_active
# ├── created_at
# └── updated_at

