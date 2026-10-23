from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from apps.payments.models import Payment
from .models import Order
from .services import OrderService


class CancelExpiredOrdersTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(phone_number="09120000000")

    def _expired_order(self):
        return Order.objects.create(
            user=self.user,
            subtotal=1000,
            total_amount=1000,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

    def test_order_with_unresolved_payment_is_not_cancelled(self):
        order = self._expired_order()
        Payment.objects.create(
            order=order, amount=1000, gateway="zarinpal",
            status=Payment.PaymentStatus.PENDING, transaction_id="A1",
        )
        OrderService.cancel_expired_orders()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.PENDING)

    def test_order_without_payment_is_cancelled(self):
        order = self._expired_order()
        OrderService.cancel_expired_orders()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)
