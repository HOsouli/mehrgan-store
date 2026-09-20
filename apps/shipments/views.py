from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from apps.orders.models import Order
from .models import Shipment
from .serializers import ShipmentDetailSerializer


class OrderShipmentView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Order Shipment",
        description="Get the shipment status for a specific order (only visible to the order's owner).",
    )
    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, user=request.user)
        shipment = get_object_or_404(Shipment, order=order)
        serializer = ShipmentDetailSerializer(shipment)
        return Response(serializer.data)



