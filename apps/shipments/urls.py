from django.urls import path
from .views import OrderShipmentView

app_name = "shipments"

urlpatterns = [
    path("<uuid:order_id>/", OrderShipmentView.as_view(), name="order-shipment"),
]

