from django.contrib import admin
from django.contrib import admin
from .models import Banner


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "display_order", "is_active", "created_at", "updated_at")
    search_fields = ("title",)
    list_filter = ("is_active",)
    ordering = ("display_order", "-created_at")
    readonly_fields = ("id", "created_at", "updated_at")

