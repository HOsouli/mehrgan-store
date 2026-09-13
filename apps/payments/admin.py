from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "amount", "status", "gateway", "transaction_id", "tracking_code", "paid_at", "created_at")
    search_fields = ("order__order_number", "transaction_id", "tracking_code")
    list_filter = ("status", "gateway", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ("id", "order", "amount", "status", "gateway", "transaction_id", "tracking_code", "paid_at", "created_at", "updated_at")


