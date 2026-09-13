from .models import Cart, CartItem
from django.db import transaction
from rest_framework.exceptions import ValidationError, NotFound


class CartService:

    @staticmethod
    def get_or_create_cart(user):
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    @staticmethod
    @transaction.atomic
    def add_item(user, product, quantity):
        cart = CartService.get_or_create_cart(user=user)
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
    def update_item(user, item_id, quantity):
        cart = CartService.get_or_create_cart(user=user)
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
    def remove_item(user, item_id):
        cart = CartService.get_or_create_cart(user=user)
        item = CartItem.objects.select_for_update().filter(cart=cart, id=item_id).first()
        if item is None:
            raise NotFound("آیتم مورد نظر در سبد خرید پیدا نشد.")
        item.delete()

    @staticmethod
    @transaction.atomic
    def clear_cart(user):
        cart = CartService.get_or_create_cart(user=user)
        cart.items.all().delete()
