from django.contrib import admin
from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("product", "quantity", "created_at", "updated_at")


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    search_fields = ("user__phone_number",)
    ordering = ("-updated_at",)
    readonly_fields = ("id", "user", "created_at", "updated_at")
    inlines = (CartItemInline,)
