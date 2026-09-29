from django.db import models
from uuid import uuid4
from apps.accounts.models import CustomUser
from apps.catalog.models import Product
from django.db.models import Q


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="cart", null=True, blank=True, verbose_name="کاربر")
    guest_token = models.UUIDField(unique=True, editable=False, null=True, blank=True, verbose_name="شناسه مهمان")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    class Meta:
        verbose_name = "سبد خرید"
        verbose_name_plural = "سبدهای خرید"
        constraints = [
        models.CheckConstraint(
            condition=(
                Q(user__isnull=False, guest_token__isnull=True)
                | Q(user__isnull=True, guest_token__isnull=False)
            ),
            name="cart_exactly_one_owner",
        ),
    ]

    def __str__(self):
        if self.user:
            return f"سبد خرید: {self.user.phone_number}"
        return f"سبد خرید مهمان: {self.guest_token}"


class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items", verbose_name="سبد خرید")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="cart_items", verbose_name="محصول")
    quantity = models.PositiveIntegerField(default=1, verbose_name="تعداد")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    class Meta:
        verbose_name = "آیتم سبد خرید"
        verbose_name_plural = "آیتم‌های سبد خرید"
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"],
                name="unique_product_per_cart"
            )
        ]

    def __str__(self):
        if self.cart.user:
            owner = self.cart.user.phone_number
        else:
            owner = f"guest:{self.cart.guest_token}"
        return f"{owner} - {self.product.name}"
