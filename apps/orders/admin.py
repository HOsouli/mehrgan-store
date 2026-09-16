from django.contrib import admin

from .models import Order, OrderItem, OrderAddress


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "quantity", "unit_price", "discount_amount", "total_price",)


class OrderAddressInline(admin.StackedInline):
    model = OrderAddress
    extra = 0
    max_num = 1
    readonly_fields = ("province", "city", "address", "postal_code", "recipient_phone", "created_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "status",
        "subtotal",
        "discount_amount",
        "shipping_amount",
        "total_amount",
        "expires_at",
        "created_at"
    )
    search_fields = ("order_number", "user__phone_number")
    list_filter = ("status", "created_at", "expires_at")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "order_number",
        "user",
        "subtotal",
        "discount_amount",
        "shipping_amount",
        "total_amount",
        "discount",
        "expires_at",
        "created_at",
        "updated_at",
    )

    inlines = (OrderItemInline, OrderAddressInline)

