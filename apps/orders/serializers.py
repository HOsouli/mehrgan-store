from rest_framework import serializers
from .models import postal_code_validator, Order, OrderAddress, OrderItem
from apps.accounts.models import mobile_validate


class OrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    items = OrderItemInputSerializer(many=True)
    recipient_name = serializers.CharField(max_length=100)
    province = serializers.CharField(max_length=100)
    city = serializers.CharField(max_length=100)
    address = serializers.CharField()
    postal_code = serializers.CharField(validators=[postal_code_validator])
    recipient_phone = serializers.CharField(validators=[mobile_validate])
    discount_code = serializers.CharField(required=False, allow_blank=True, max_length=10)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("سبد خرید خالی است.")
        return value


class OrderListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "order_number", "status", "subtotal", "discount_amount", "shipping_amount", "total_amount", "expires_at", "created_at"]


class OrderItemDetailSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = OrderItem
        fields = ["product_name", "quantity", "unit_price", "discount_amount", "total_price"]


class OrderAddressDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderAddress
        fields = ["recipient_name", "province", "city", "address", "postal_code", "recipient_phone"]


class OrderDetailSerializer(serializers.ModelSerializer):
    address = OrderAddressDetailSerializer(read_only=True)
    items = OrderItemDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "status", "subtotal", "discount_amount",
            "shipping_amount", "total_amount", "expires_at", "created_at",
            "address", "items",
        ]

