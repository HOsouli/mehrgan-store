from decimal import Decimal
from django import forms
from django.contrib import admin
from django.db import transaction
from .models import Shipment
from .services import sync_invoice_shipping, sync_order_status


class ShipmentAdminForm(forms.ModelForm):
    class Meta:
        model = Shipment
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shipping_cost"].required = False

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")
        carrier = (cleaned_data.get("carrier") or "").strip()
        shipping_cost = cleaned_data.get("shipping_cost")
        is_store_courier = (
            method == Shipment.ShipmentMethod.COURIER
            and carrier == "پیک فروشگاه"
        )
        if is_store_courier and shipping_cost is None:
            self.add_error("shipping_cost", "برای پیک فروشگاه، ثبت هزینه ارسال الزامی است.")
        elif not is_store_courier:
            cleaned_data["shipping_cost"] = Decimal(0)
        return cleaned_data


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    form = ShipmentAdminForm
    list_display = (
        "order", "method", "carrier", "tracking_code",
        "shipping_cost", "status", "shipped_at",
        "delivered_at", "created_at",
    )
    search_fields = ("order__order_number", "tracking_code", "carrier")
    list_filter = ("method", "status", "carrier", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ("id", "order", "created_at", "updated_at")

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        sync_invoice_shipping(obj.order_id, obj.shipping_cost, obj.method, obj.carrier)
        sync_order_status(obj.order_id, obj.status)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
