from django.urls import path
from .views import PaymentRequestView, PaymentCallbackView, PaymentStatusView

app_name = "payments"

urlpatterns = [
    path("request/", PaymentRequestView.as_view(), name="request"),
    path("callback/", PaymentCallbackView.as_view(), name="callback"),
    path("status/<uuid:payment_id>/", PaymentStatusView.as_view(), name="status"),
]
