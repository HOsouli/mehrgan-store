from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "amount",
        "status",
        "order_status",
        "review_required",
        "gateway",
        "transaction_id",
        "tracking_code",
        "paid_at",
        "created_at",
    )
    search_fields = (
        "order__order_number",
        "transaction_id",
        "tracking_code",
    )
    list_filter = (
        "status",
        "order__status",
        "gateway",
        "created_at",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "order",
        "amount",
        "status",
        "gateway",
        "transaction_id",
        "tracking_code",
        "paid_at",
        "created_at",
        "updated_at",
        "gateway_response_code",
        "gateway_response_message",
    )

    @admin.display(description="وضعیت سفارش")
    def order_status(self, obj):
        return obj.order.get_status_display()

    @admin.display(description="نیازمند بررسی", boolean=True)
    def review_required(self, obj):
        return (obj.status == Payment.PaymentStatus.SUCCESS and obj.order.status == "cancelled")
