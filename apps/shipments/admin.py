from django.contrib import admin
from django.db import transaction
from .models import Shipment
from .services import sync_invoice_shipping


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("order", "method", "carrier", "tracking_code", "shipping_cost", "status", "shipped_at", "delivered_at", "created_at")
    search_fields = ("order__order_number", "tracking_code", "carrier")
    list_filter = ("method", "status", "carrier", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        sync_invoice_shipping(obj.order_id, obj.shipping_cost)

    @transaction.atomic
    def delete_model(self, request, obj):
        order_id = obj.order_id
        super().delete_model(request, obj)
        sync_invoice_shipping(order_id, 0)

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        order_ids = list(queryset.values_list("order_id", flat=True))
        super().delete_queryset(request, queryset)
        for order_id in order_ids:
            sync_invoice_shipping(order_id, 0)
