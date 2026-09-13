from rest_framework import serializers
from apps.catalog.models import Product
from .models import Cart, CartItem


class AddToCartSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField(min_value=1)


class CartItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_price = serializers.DecimalField(source="product.price", max_digits=12, decimal_places=0, read_only=True)

    # Use when the field is calculated dynamically and doesn't exist in the model.
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "quantity", "product_name", "product_price", "line_total"]
        read_only_fields = ["id", "product_name", "product_price", "line_total"]

    def get_line_total(self, obj):
        return obj.product.price * obj.quantity


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "items", "item_count", "subtotal", "created_at", "updated_at"]
        read_only_fields = ["id", "items", "item_count", "subtotal", "created_at", "updated_at"]

    def get_item_count(self, obj):
        return sum(item.quantity for item in obj.items.all())

    def get_subtotal(self, obj):
        return sum(item.product.price * item.quantity for item in obj.items.all())



# `source` is used to access an attribute or field through a model relationship. that i used in lines 16 and 17.

