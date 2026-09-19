from django.urls import path
from .views import OrderListCreateView, OrderDetailView

app_name = "orders"

urlpatterns = [
    path("", OrderListCreateView.as_view(), name="list-create"),
    path("<uuid:pk>/", OrderDetailView.as_view(), name="detail"),
]


