
from django.shortcuts import redirect
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from apps.orders.models import Order
from .serializers import PaymentRequestSerializer
from .services import ZarinpalService
from rest_framework.exceptions import ValidationError
import logging
from uuid import UUID
from .models import Payment

logger = logging.getLogger(__name__)


class PaymentRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Request Payment",
        description="Start a Zarinpal payment for an existing order and return the redirect URL.",
        request=PaymentRequestSerializer,
    )
    def post(self, request):
        serializer = PaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_id = serializer.validated_data["order_id"]
        try:
            order = Order.objects.select_related("address").get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response({"detail": "سفارش یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        payment, pay_url = ZarinpalService.request_payment(order)
        return Response({"payment_id": payment.id, "pay_url": pay_url,})


class PaymentCallbackView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Payment Callback",
        description="Zarinpal redirects the user's browser here after payment. Verifies the transaction and redirects to the frontend result page.",
    )
    def get(self, request):
        payment_id = request.query_params.get("payment_id")
        authority = request.query_params.get("Authority")
        gateway_status = request.query_params.get("Status")
        result_url = f"{settings.FRONTEND_URL}/payment-result"
        failed_url = f"{result_url}?status=failed"
        try:
            payment_uuid = UUID(payment_id)
        except (TypeError, ValueError):
            return redirect(failed_url)
        if gateway_status != "OK" or not authority:
            return redirect(f"{failed_url}&payment_id={payment_uuid}")
        try:
            payment = ZarinpalService.verify_payment(payment_id=payment_uuid, authority=authority)
        except ValidationError as exc:
            logger.warning("تأیید پرداخت %s ناموفق بود: %s", payment_uuid, exc.detail)
            return redirect(f"{failed_url}&payment_id={payment_uuid}")
        if payment.status != Payment.PaymentStatus.SUCCESS:
            return redirect(f"{failed_url}&payment_id={payment_uuid}")
        return redirect(
            f"{result_url}?status=success&order_number={payment.order.order_number}&tracking_code={payment.tracking_code}"
        )
