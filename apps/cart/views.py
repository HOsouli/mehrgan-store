from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import CartSerializer, AddToCartSerializer, CartItemSerializer, CartItemUpdateSerializer
from .services import CartService
from drf_spectacular.utils import extend_schema


class CartView(APIView):

    def get(self, request):
        cart = CartService.get_or_create_cart(user=request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    def delete(self, request):
        CartService.clear_cart(user=request.user)
        return Response({"message": "سبد خرید خالی شد"})


@extend_schema(request=AddToCartSerializer, responses=CartItemSerializer)
class AddCartView(APIView):

    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product"]
        quantity = serializer.validated_data["quantity"]
        item = CartService.add_item(user=request.user, product=product, quantity=quantity)
        return Response(CartItemSerializer(item).data)


class CartItemView(APIView):

    def patch(self, request, item_id):
        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]
        item = CartService.update_item(user=request.user, item_id=item_id, quantity=quantity)
        return Response(CartItemSerializer(item).data)

    def delete(self, request, item_id):
        CartService.remove_item(user=request.user, item_id=item_id)
        return Response({"message": "آیتم از سبد خرید حذف شد"})

