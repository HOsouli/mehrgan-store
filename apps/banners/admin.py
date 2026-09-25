from django.contrib import admin
from django.utils.html import format_html

from .models import Banner


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("preview", "title", "position", "sort_order", "is_active", "starts_at", "ends_at")
    list_filter = ("position", "is_active")
    search_fields = ("title", "link")
    list_editable = ("sort_order", "is_active")
    ordering = ("position", "sort_order", "-id")

    @admin.display(description="تصویر")
    def preview(self, obj):
        if not obj.image:
            return "-"

        return format_html(
            '<img src="{}" style="height:42px;width:84px;object-fit:cover;border-radius:4px;" />',
            obj.image.url,
        )
