from uuid import UUID
from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import CartSerializer, AddToCartSerializer, CartItemSerializer, CartItemUpdateSerializer
from .services import CartService
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import ValidationError


def get_cart_owner(request):
    if request.user.is_authenticated:
        return request.user, None
    guest_token = request.headers.get("X-Guest-Cart-Token")
    if not guest_token:
        return None, None
    try:
        guest_token = UUID(guest_token)
    except ValueError:
        raise ValidationError({
            "guest_token": "شناسه مهمان نامعتبر است."
        })
    return None, guest_token

class CartView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        user, guest_token = get_cart_owner(request)
        cart = CartService.get_or_create_cart(user=user, guest_token=guest_token)
        serializer = CartSerializer(cart)
        data = serializer.data
        if not user and cart.guest_token:
            data["guest_token"] = str(cart.guest_token)
        return Response(data)

    def delete(self, request):
        user, guest_token = get_cart_owner(request)
        CartService.clear_cart(user=user, guest_token=guest_token)
        return Response({"message": "سبد خرید خالی شد"})


@extend_schema(request=AddToCartSerializer, responses=CartItemSerializer)
class AddCartView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product"]
        quantity = serializer.validated_data["quantity"]
        user, guest_token = get_cart_owner(request)
        item = CartService.add_item(user=user, guest_token=guest_token, product=product, quantity=quantity)
        data = CartItemSerializer(item).data
        if not user and item.cart.guest_token:
            data["guest_token"] = str(item.cart.guest_token)
        return Response(data)


class CartItemView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=CartItemUpdateSerializer, responses=CartItemSerializer)
    def patch(self, request, item_id):
        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]
        user, guest_token = get_cart_owner(request)
        item = CartService.update_item(user=user, guest_token=guest_token, item_id=item_id, quantity=quantity)
        return Response(CartItemSerializer(item).data)

    def delete(self, request, item_id):
        user, guest_token = get_cart_owner(request)
        CartService.remove_item(user=user, guest_token=guest_token, item_id=item_id)
        return Response({"message": "آیتم از سبد خرید حذف شد"})

