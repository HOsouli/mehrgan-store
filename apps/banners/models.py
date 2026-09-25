from django.db import models
from django.db.models import Q
from django.utils import timezone


class BannerQuerySet(models.QuerySet):
    def currently_visible(self):
        now = timezone.now()

        return self.filter(is_active=True,).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now),
            Q(ends_at__isnull=True) | Q(ends_at__gt=now),
        )


class Banner(models.Model):
    class Position(models.TextChoices):
        HOME_SLIDER = "home_slider", "اسلایدر صفحه اصلی"

    title = models.CharField(max_length=150, verbose_name="عنوان")
    alt_text = models.CharField(max_length=150, blank=True, verbose_name="متن جایگزین تصویر")
    image = models.ImageField(upload_to="banners/%Y/%m/", verbose_name="تصویر دسکتاپ")
    mobile_image = models.ImageField(upload_to="banners/mobile/%Y/%m/", blank=True, verbose_name="تصویر موبایل")
    link = models.CharField(max_length=500, blank=True, verbose_name="لینک", help_text="آدرس کامل یا مسیر داخلی مثل /products/oil")
    open_in_new_tab = models.BooleanField(default=False, verbose_name="باز شدن در تب جدید")
    position = models.CharField(max_length=32, choices=Position.choices, default=Position.HOME_SLIDER, db_index=True, verbose_name="جایگاه")
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name="ترتیب")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    starts_at = models.DateTimeField(null=True, blank=True, verbose_name="شروع نمایش")
    ends_at = models.DateTimeField(null=True, blank=True, verbose_name="پایان نمایش")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="ویرایش")

    objects = BannerQuerySet.as_manager()

    class Meta:
        verbose_name = "بنر"
        verbose_name_plural = "بنرها"
        ordering = ["position", "sort_order", "-id"]
        indexes = [models.Index(fields=["position", "is_active", "sort_order"])]

    def __str__(self):
        return self.title
