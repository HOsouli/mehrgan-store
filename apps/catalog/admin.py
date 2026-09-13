from django.contrib import admin
from .models import Category, Brand, Car, Product, ProductImage

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)
    ordering = ("name",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "formatted_price", "stock", "created_at", "updated_at")
    search_fields = ("name", "slug", "brand__name", "category__name")
    list_filter = ("brand", "category")
    ordering = ("-created_at",)
    readonly_fields = ("slug",)
    filter_horizontal = ("cars",)
    inlines = (ProductImageInline,)

    @admin.display(description="قیمت")
    def formatted_price(self, obj):
        return f"{obj.price:,}"


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "created_at")
    search_fields = ("product__name",)
    ordering = ("-created_at",)

