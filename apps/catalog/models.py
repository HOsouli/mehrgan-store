from django.db import models
from uuid import uuid4
from django.utils.text import slugify
import os
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFit


def product_image_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1]
    return f"products/{uuid4()}{extension}"


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    name = models.CharField(max_length=100, verbose_name="نام دسته‌بندی")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    class Meta:
        verbose_name="دسته‌بندی"
        verbose_name_plural="دسته‌بندی‌ها"

    def __str__(self):
        return self.name


class Brand(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    name = models.CharField(max_length=100, unique=True, verbose_name="نام برند")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    class Meta:
        verbose_name="برند"
        verbose_name_plural="برندها"

    def __str__(self):
        return self.name


class Car(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    name = models.CharField(max_length=100, unique=True, verbose_name="نام خودرو")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    class Meta:
        verbose_name="خودرو"
        verbose_name_plural="خودروها"

    def __str__(self):
        return self.name


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    name = models.CharField(max_length=100, unique=True, verbose_name="نام محصول")
    slug = models.SlugField(max_length=200, unique=True, blank=True, verbose_name="شناسه متنی")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    price = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="قیمت(ریال)")
    stock = models.PositiveIntegerField(default=0, verbose_name="موجودی")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", verbose_name="دسته‌بندی")
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products", verbose_name="برند")
    cars = models.ManyToManyField(Car, related_name="products", blank=True, verbose_name="خودروهای سازگار")
    model = models.CharField(max_length=100, blank=True, verbose_name="مدل")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name, allow_unicode=True)
            slug = base_slug
            n = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    class Meta:
        verbose_name="محصول"
        verbose_name_plural="محصولات"

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images", verbose_name="محصول")
    image = models.ImageField(upload_to=product_image_upload_path, verbose_name="تصویر")
    image_thumbnail = ImageSpecField(source="image", processors=[ResizeToFit(800, 800)], format="JPEG", options={"quality": 85})
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "تصویر محصول"
        verbose_name_plural = "تصاویر محصولات"

    def __str__(self):
        return f"تصویر {self.product.name}"

