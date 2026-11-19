from django.shortcuts import redirect
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from apps.orders.models import Order
from .serializers import PaymentRequestSerializer, PaymentRequestResponseSerializer
from .services import ZibalService
from rest_framework.exceptions import ValidationError
import logging
from uuid import UUID
from .models import Payment
from urllib.parse import urlencode
from django.db import transaction, IntegrityError


logger = logging.getLogger(__name__)


class PaymentRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Request Payment",
        description="Start a Zibal payment for an existing order and return the redirect URL.",
        request=PaymentRequestSerializer,
        responses={200: PaymentRequestResponseSerializer},
    )
    def post(self, request):
        serializer = PaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_id = serializer.validated_data["order_id"]
        try:
            order = Order.objects.select_related("address").get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response({"detail": "سفارش یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        payment, pay_url = ZibalService.request_payment(order)
        if payment.status == Payment.PaymentStatus.SUCCESS:
            payment.refresh_from_db()
            payment.order.refresh_from_db()
            payment_status = (
                "success"
                if payment.order.status in (
                    Order.OrderStatus.PROCESSING,
                    Order.OrderStatus.SHIPPED,
                    Order.OrderStatus.DELIVERED,
                )
                else "review"
            )
        else:
            payment_status = "pending"
        return Response({
            "payment_id": payment.id,
            "status": payment_status,
            "pay_url": pay_url,
        })


class PaymentCallbackView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Payment Callback",
        description=(
    "Receives Zibal Standard GET callback, validates payment identifiers, "
    "verifies the transaction, and redirects to the frontend result page."
),
    )

    def get(self, request):
        payment_id = request.query_params.get("payment_id")
        track_id = request.query_params.get("trackId")
        callback_order_id = request.query_params.get("orderId")
        result_url = f"{settings.FRONTEND_URL}/payment-result"
        failed_url = f"{result_url}?status=failed"
        pending_url = f"{result_url}?status=pending"
        try:
            payment_uuid = UUID(payment_id)
        except (TypeError, ValueError):
            return redirect(failed_url)
        if callback_order_id != str(payment_uuid):
            logger.warning("Zibal callback orderId mismatch for payment %s", payment_uuid)
            return redirect(f"{result_url}?status=review&payment_id={payment_uuid}")
        if not track_id or not track_id.isdigit() or int(track_id) <= 0:
            return redirect(f"{pending_url}&payment_id={payment_uuid}")
        try:
            with transaction.atomic():
                payment = Payment.objects.select_for_update().get(pk=payment_uuid, gateway="zibal")
                if payment.transaction_id and payment.transaction_id != track_id:
                    logger.error("Zibal callback trackId mismatch for payment %s", payment_uuid)
                    return redirect(f"{result_url}?status=review&payment_id={payment_uuid}")
                if not payment.transaction_id:
                    payment.transaction_id = track_id
                    payment.save(update_fields=["transaction_id", "updated_at"])
        except Payment.DoesNotExist:
            return redirect(f"{result_url}?status=review&payment_id={payment_uuid}")
        except IntegrityError:
            logger.exception("Duplicate Zibal trackId received for payment %s", payment_uuid)
            return redirect(f"{result_url}?status=review&payment_id={payment_uuid}")
        try:
            ZibalService.verify_payment(payment_id=payment_uuid, track_id=track_id)
        except ValidationError as exc:
            logger.warning("بررسی پرداخت %s ناموفق بود: %s", payment_uuid, exc.detail)
        except Exception:
            logger.exception("خطای غیرمنتظره در بررسی پرداخت %s", payment_uuid)
        payment = Payment.objects.select_related("order").filter(pk=payment_uuid, transaction_id=track_id,).first()
        if payment is None or payment.status == Payment.PaymentStatus.FAILED:
            return redirect(f"{failed_url}&payment_id={payment_uuid}")
        if payment.status in (Payment.PaymentStatus.PENDING, Payment.PaymentStatus.CANCELLED):
            return redirect(f"{pending_url}&payment_id={payment_uuid}")
        if payment.status != Payment.PaymentStatus.SUCCESS:
            return redirect(f"{failed_url}&payment_id={payment_uuid}")
        if payment.order.status not in (Order.OrderStatus.PROCESSING, Order.OrderStatus.SHIPPED, Order.OrderStatus.DELIVERED):
            return redirect(f"{result_url}?status=review&payment_id={payment_uuid}")
        return redirect(
            f"{result_url}?{urlencode({
                'status': 'success',
                'order_id': payment.order_id,
                'order_number': payment.order.order_number,
                'tracking_code': payment.tracking_code or '',
            })}"
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
