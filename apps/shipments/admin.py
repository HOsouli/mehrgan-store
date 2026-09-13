from django.contrib import admin
from .models import Shipment


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("order", "method", "carrier", "tracking_code", "shipping_cost", "status", "shipped_at", "delivered_at", "created_at")
    search_fields = ("order__order_number", "tracking_code", "carrier")
    list_filter = ("method", "status", "carrier", "created_at")
    ordering = ("-created_at",)
    readonly_fields = (
        "id", "order", "method", "carrier", "tracking_code", "shipping_cost", "status",
        "shipped_at", "delivered_at", "created_at", "updated_at",
    )
