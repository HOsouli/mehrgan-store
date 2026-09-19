from django.urls import path
from .views import PaymentRequestView, PaymentCallbackView

app_name = "payments"

urlpatterns = [
    path("request/", PaymentRequestView.as_view(), name="request"),
    path("callback/", PaymentCallbackView.as_view(), name="callback"),
]
