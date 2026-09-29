from uuid import uuid4
from .models import Cart, CartItem
from apps.catalog.models import Product
from django.db import transaction
from rest_framework.exceptions import ValidationError, NotFound


class CartService:

    @staticmethod
    def get_or_create_cart(user=None, guest_token=None):
        if user:
            cart, _ = Cart.objects.get_or_create(user=user)
            return cart
        if guest_token:
            cart, _ = Cart.objects.get_or_create(guest_token=guest_token)
            return cart
        return Cart.objects.create(guest_token=uuid4())

    @staticmethod
    @transaction.atomic
    def merge_guest_cart(user, guest_token):
        guest_cart = Cart.objects.filter(guest_token=guest_token).first()
        if guest_cart is None:
            return CartService.get_or_create_cart(user=user)
        user_cart = CartService.get_or_create_cart(user=user)
        for guest_item in guest_cart.items.select_related("product"):
            product = Product.objects.select_for_update().get(pk=guest_item.product_id)
            user_item = CartItem.objects.select_for_update().filter(cart=user_cart, product=product).first()
            new_quantity = (guest_item.quantity if user_item is None else user_item.quantity + guest_item.quantity)
            if new_quantity > product.stock:
                raise ValidationError({"quantity": f"موجودی محصول «{product.name}» برای انتقال سبد کافی نیست."})
            if user_item:
                user_item.quantity = new_quantity
                user_item.save(update_fields=["quantity", "updated_at"])
            else:
                CartItem.objects.create(cart=user_cart, product=product, quantity=guest_item.quantity)
        guest_cart.delete()
        return user_cart

    @staticmethod
    @transaction.atomic
    def add_item(user=None, guest_token=None, product=None, quantity=1):
        cart = CartService.get_or_create_cart(user=user, guest_token=guest_token)
        item = CartItem.objects.select_for_update().filter(cart=cart, product=product).first()
        new_quantity = quantity if item is None else item.quantity + quantity
        if new_quantity > product.stock:
            raise ValidationError({"quantity": "تعداد درخواستی بیشتر از موجودی محصول است."})
        if item:
            item.quantity = new_quantity
            item.save(update_fields=["quantity", "updated_at"])
        else:
            item = CartItem.objects.create(cart=cart, product=product, quantity=quantity)
        return item

    @staticmethod
    @transaction.atomic
    def update_item(user=None, guest_token=None, item_id=None, quantity=1):
        cart = CartService.get_or_create_cart(user=user, guest_token=guest_token)
        item = CartItem.objects.select_for_update().filter(cart=cart, id=item_id).first()
        if item is None:
            raise NotFound("آیتم مورد نظر در سبد خرید پیدا نشد.")
        if quantity > item.product.stock:
            raise ValidationError({"quantity": "تعداد درخواستی بیشتر از موجودی محصول است."})
        item.quantity = quantity
        item.save(update_fields=["quantity", "updated_at"])
        return item

    @staticmethod
    @transaction.atomic
    def remove_item(user=None, guest_token=None, item_id=None):
        cart = CartService.get_or_create_cart(user=user, guest_token=guest_token)
        item = CartItem.objects.select_for_update().filter(cart=cart, id=item_id).first()
        if item is None:
            raise NotFound("آیتم مورد نظر در سبد خرید پیدا نشد.")
        item.delete()

    @staticmethod
    @transaction.atomic
    def clear_cart(user=None, guest_token=None):
        cart = CartService.get_or_create_cart(user=user, guest_token=guest_token)
        cart.items.all().delete()
