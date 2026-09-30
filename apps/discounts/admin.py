from django.contrib import admin, messages
from django.utils import timezone
from .models import Discount, CouponUsage


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "discount_type", "display_value", "target_type", "starts_at", "ends_at", "is_active", "state_label")
    search_fields = ("code", "title")
    list_filter = ("discount_type", "target_type", "is_active")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
    filter_horizontal = ("products", "categories", "brands", "eligible_users")
    actions = ("activate", "deactivate")
    fieldsets = (
        ("مشخصات", {"fields": ("id", "title", "code", "is_active", "priority")}),
        ("مقدار", {"fields": ("discount_type", "value", "minimum_order_amount")}),
        ("محدوده", {"fields": ("target_type", "products", "categories", "brands", "eligible_users")}),
        ("محدودیت استفاده", {"fields": ("total_usage_limit", "per_user_limit")}),
        ("بازه زمانی", {"fields": ("starts_at", "ends_at")}),
        ("سیستمی", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="وضعیت")
    def state_label(self, obj):
        return {
            "inactive": "غیرفعال",
            "scheduled": "زمان‌بندی‌شده",
            "running": "در حال اجرا",
            "expired": "منقضی",
        }[obj.state]

    @admin.display(description="مقدار")
    def display_value(self, obj):
        if obj.discount_type == Discount.DiscountType.PERCENTAGE:
            return f"{obj.value:,}٪"
        return f"{obj.value:,} ریال"

    @admin.action(description="فعال کردن تخفیف‌های انتخاب‌شده")
    def activate(self, request, queryset):
        count = queryset.update(is_active=True, updated_at=timezone.now())
        self.message_user(request, f"{count} تخفیف فعال شد.")

    @admin.action(description="غیرفعال کردن تخفیف‌های انتخاب‌شده")
    def deactivate(self, request, queryset):
        count = queryset.update(is_active=False, updated_at=timezone.now())
        self.message_user(request, f"{count} تخفیف غیرفعال شد.")

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        relation = {"product": obj.products, "category": obj.categories, "brand": obj.brands}.get(obj.target_type)
        if relation is not None and not relation.exists():
            messages.warning(request, "برای این محدوده هیچ مورد انتخاب نشده و تخفیف روی هیچ کالایی اعمال نمی‌شود.")


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ("discount", "user", "order", "created_at")
    search_fields = ("discount__code", "user__phone_number", "order__order_number")
    list_filter = ("created_at",)
    ordering = ("-created_at",)
    readonly_fields = ("id", "user", "discount", "order", "created_at")
