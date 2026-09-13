from django.contrib import admin
from .models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    autocomplete_fields = ("product",)
    readonly_fields = ("product_name", "quantity", "unit_price", "discount_amount", "total_price")

list_display = ("invoice_number", "order", "status", "subtotal", "discount_amount", "shipping_amount", "total_amount", "issued_at")
list_filter = ("status", "issued_at")
search_fields = ("invoice_number", "order__order_number", "order__user__phone_number")
readonly_fields = (
    "invoice_number", "order", "subtotal", "discount_amount", "shipping_amount",
    "total_amount", "issued_at", "created_at", "updated_at"
    )
