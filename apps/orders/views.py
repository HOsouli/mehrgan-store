from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from .models import Order
from .serializers import OrderCreateSerializer, OrderListSerializer, OrderDetailSerializer
from .services import OrderService


class OrderListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="List Orders", description="List all orders for the current user.")
    def get(self, request):
        orders = Order.objects.filter(user=request.user).order_by("-created_at")
        serializer = OrderListSerializer(orders, many=True)
        return Response(serializer.data)

    @extend_schema(
            summary="Create Order",
            description="Create a new order from cart items, address, and optional discount code.",
            request=OrderCreateSerializer,
        )
    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = OrderService.create_order(user=request.user, validated_data=serializer.validated_data)
        return Response(
            {
                "message": "سفارش با موفقیت ایجاد شد.",
                "order_id": order.id,
                "order_number": order.order_number,
                "total_amount": order.total_amount,
            },
            status=status.HTTP_201_CREATED,
        )


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
            summary="Order Detail",
            description="Retrieve a single order's full details (items, address).",
            responses=OrderDetailSerializer
        )
    def get(self, request, pk):
        order = get_object_or_404(
            Order.objects.select_related("address").prefetch_related("items__product"),
            pk=pk,
            user=request.user
        )
        serializer = OrderDetailSerializer(order)
        return Response(serializer.data)

