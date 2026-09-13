from django.db import models
from uuid import uuid4
from apps.accounts.models import CustomUser
from apps.catalog.models import Product


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="cart", verbose_name="کاربر")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    class Meta:
        verbose_name = "سبد خرید"
        verbose_name_plural = "سبدهای خرید"

    def __str__(self):
        return f"سبد خرید: {self.user.phone_number}"


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
        return f"{self.cart.user.phone_number} - {self.product.name}"
