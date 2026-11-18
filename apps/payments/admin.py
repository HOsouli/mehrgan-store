
from datetime import timedelta
from django.contrib import admin
from django.utils import timezone
from apps.orders.models import Order
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "order", "amount", "status", "order_status", "review_status", "gateway",
        "transaction_id", "tracking_code", "paid_at", "created_at"
    )
    list_select_related = ("order",)
    search_fields = ("order__order_number", "transaction_id", "tracking_code")
    list_filter = ("status", "request_state", "order__status", "gateway", "created_at")
    ordering = ("-created_at",)
    readonly_fields = (
        "id", "order", "amount", "status", "request_state", "gateway", "transaction_id", "tracking_code",
        "paid_at", "created_at", "updated_at", "gateway_response_code", "gateway_response_message",
    )

    @admin.display(description="وضعیت سفارش")
    def order_status(self, obj):
        return obj.order.get_status_display()

    @admin.display(description="وضعیت بررسی")
    def review_status(self, obj):
        payment_status = obj.status
        order_status = obj.order.status
        response_code = obj.gateway_response_code or ""
        request_state = obj.request_state

        # Financial discrepancies have the highest priority.
        if response_code == "REVERSED":
            return "مغایرت مالی: تراکنش برگشت‌خورده"

        if response_code == "201":
            return "نیازمند بررسی مالی: تأیید قبلی درگاه"

        # Zibal Inquiry statuses requiring financial review.
        if response_code in ("s15", "s16", "s18"):
            return "نیازمند بررسی مالی: استرداد یا برگشت تراکنش"

        if response_code in ("s-1", "s-2", "s2"):
            return "نتیجه استعلام نامشخص؛ نیازمند پیگیری"

        if response_code.startswith("s"):
            try:
                inquiry_status = int(response_code[1:])
            except ValueError:
                return "نیازمند بررسی مالی"

            if 3 <= inquiry_status <= 12:
                if payment_status == Payment.PaymentStatus.FAILED:
                    return "پرداخت ناموفق"
                return "مغایرت مالی؛ نیازمند بررسی"

            return "نیازمند بررسی مالی"

        if payment_status == Payment.PaymentStatus.SUCCESS:
            if order_status == Order.OrderStatus.CANCELLED:
                return "مغایرت: پرداخت موفق برای سفارش لغوشده"

            if order_status == Order.OrderStatus.PENDING:
                return "پرداخت موفق؛ سفارش نیازمند بررسی"

            return "پرداخت موفق"

        if request_state == Payment.RequestState.SUBMITTING:
            return "در حال ارسال درخواست به درگاه"

        if request_state == Payment.RequestState.UNKNOWN:
            return "نتیجه درخواست درگاه نامشخص"

        if response_code in ("net", "invalid_response", "inq"):
            return "نتیجه پرداخت نامشخص؛ نیازمند پیگیری"

        if payment_status == Payment.PaymentStatus.FAILED:
            return "پرداخت ناموفق"

        if payment_status == Payment.PaymentStatus.CANCELLED:
            return "پرداخت لغوشده"

        if payment_status == Payment.PaymentStatus.PENDING:
            if obj.created_at <= timezone.now() - timedelta(hours=24):
                return "پرداخت معوق؛ نیازمند پیگیری"

            return "در انتظار پرداخت"

        return "نیازمند بررسی مالی"
