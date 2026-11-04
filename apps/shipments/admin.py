from django.contrib import admin
from django.db import transaction
from .models import Shipment
from .services import sync_invoice_shipping, sync_order_status


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("order", "method", "carrier", "tracking_code", "shipping_cost", "status", "shipped_at", "delivered_at", "created_at")
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
