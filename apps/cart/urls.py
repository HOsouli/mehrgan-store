from django.urls import path
from .views import CartView, AddCartView, CartItemView


app_name = "cart"

urlpatterns = [
    path("", CartView.as_view(), name="cart"),
    path("items/", AddCartView.as_view(), name="add-item"),
    path("items/<uuid:item_id>/", CartItemView.as_view(), name="cart-item"),
]
