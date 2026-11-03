
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
        pending_url = f"{result_url}?status=pending&payment_id={payment_uuid}"
        try:
            payment = ZarinpalService.verify_payment(payment_id=payment_uuid, authority=authority)
        except ValidationError as exc:
            logger.warning("تأیید پرداخت %s ناموفق بود: %s", payment_uuid, exc.detail)
            payment = (Payment.objects.select_related("order").filter(pk=payment_uuid, transaction_id=authority).first())
            if payment is None or payment.status == Payment.PaymentStatus.FAILED:
                return redirect(f"{failed_url}&payment_id={payment_uuid}")
            if payment.status in (Payment.PaymentStatus.PENDING, Payment.PaymentStatus.CANCELLED):
                return redirect(pending_url)
        if payment.status == Payment.PaymentStatus.PENDING:
            return redirect(pending_url)
        if payment.status != Payment.PaymentStatus.SUCCESS:
            return redirect(f"{failed_url}&payment_id={payment_uuid}")
        if payment.order.status not in (
            Order.OrderStatus.PROCESSING,
            Order.OrderStatus.SHIPPED,
            Order.OrderStatus.DELIVERED,
        ):
            return redirect(f"{result_url}?status=review&payment_id={payment_uuid}")
        return redirect(
            f"{result_url}?status=success"
            f"&order_id={payment.order_id}"
            f"&order_number={payment.order.order_number}"
            f"&tracking_code={payment.tracking_code}"
        )


class PaymentStatusView(APIView):
    permission_classes = [IsAuthenticated]
    @extend_schema(
        summary="Payment Status",
        description="Retrieve the status and details of an owned payment.",
    )
    def get(self, request, payment_id):
        payment = (Payment.objects.select_related("order").filter(pk=payment_id, order__user=request.user).first())
        if payment is None:
            return Response({"detail": "پرداخت یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        if payment.status == Payment.PaymentStatus.SUCCESS:
            result = (
                "success"
                if payment.order.status in (
                    Order.OrderStatus.PROCESSING,
                    Order.OrderStatus.SHIPPED,
                    Order.OrderStatus.DELIVERED,
                )
                else "review"
            )
        elif payment.status in (Payment.PaymentStatus.PENDING, Payment.PaymentStatus.CANCELLED):
            result = "pending"
        else:
            result = "failed"
        return Response({
            "payment_id": str(payment.id),
            "status": result,
            "payment_status": payment.status,
            "order_id": str(payment.order_id),
            "order_number": payment.order.order_number,
            "order_status": payment.order.status,
            "amount": payment.amount,
            "tracking_code": payment.tracking_code,
            "paid_at": payment.paid_at,
        })
