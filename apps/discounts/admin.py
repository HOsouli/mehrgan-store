from django.contrib import admin
from .models import Discount, CouponUsage
from django import forms
from django_jalali.forms import jDateTimeField


class DiscountAdminForm(forms.ModelForm):
    starts_at = jDateTimeField()
    ends_at = jDateTimeField()

    class Meta:
        model = Discount
        fields = "__all__"


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    form = DiscountAdminForm
    list_display = ("code", "discount_type", "value", "target_type", "minimum_order_amount", "starts_at", "ends_at", "is_active")
    search_fields = ("code",)
    list_filter = ("discount_type", "target_type", "is_active")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
    filter_horizontal = ("products", "categories", "brands")


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ("discount", "user", "order", "created_at")
    search_fields = ("discount__code", "user__phone_number", "order__order_number")
    list_filter = ("created_at",)
    ordering = ("-created_at",)
    readonly_fields = ("id", "user", "discount", "order", "created_at")

