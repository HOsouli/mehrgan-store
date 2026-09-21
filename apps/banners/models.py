from uuid import uuid4
from django.db import models


class Banner(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    image = models.ImageField(upload_to="banners/", verbose_name="تصویر")
    title = models.CharField(max_length=200, verbose_name="عنوان")
    link = models.URLField(blank=True, verbose_name="لینک")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True,verbose_name="تاریخ ویرایش")

    class Meta:
        verbose_name = "بنر"
        verbose_name_plural = "بنرها"
        ordering = ("display_order", "-created_at")

    def __str__(self):
        return self.title


