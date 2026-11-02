from rest_framework import serializers
from .models import Shipment


class ShipmentDetailSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)

    class Meta:
        model = Shipment
        fields = ["id", "order_number", "method", "method_display", "carrier", "tracking_code",
            "shipping_cost", "status", "status_display", "shipped_at", "delivered_at",
        ]
