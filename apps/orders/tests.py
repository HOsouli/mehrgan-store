from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from apps.payments.models import Payment
from .models import Order
from .services import OrderService
from apps.catalog.models import Product, Category, Brand
from apps.discounts.models import Discount, CouponUsage


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

    def test_old_unresolved_payment_is_cancelled_with_order(self):
        order = self._expired_order()
        payment = Payment.objects.create(
            order=order,
            amount=1000,
            gateway="zarinpal",
            status=Payment.PaymentStatus.PENDING,
            transaction_id="A2",
        )
        old_time = timezone.now() - timedelta(minutes=31)
        Payment.objects.filter(pk=payment.pk).update(
            created_at=old_time,
            updated_at=old_time,
        )
        OrderService.cancel_expired_orders()
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)
        self.assertEqual(payment.status, Payment.PaymentStatus.CANCELLED)

    def test_order_with_successful_payment_is_not_cancelled(self):
        order = self._expired_order()
        Payment.objects.create(
            order=order,
            amount=1000,
            gateway="zarinpal",
            status=Payment.PaymentStatus.SUCCESS,
            transaction_id="A3",
            tracking_code="REF_A3",
            paid_at=timezone.now(),
        )
        OrderService.cancel_expired_orders()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.PENDING)

    def test_cancelling_order_restores_product_stock(self):
        category = Category.objects.create(name="تست")
        brand = Brand.objects.create(name="برند تست")
        product = Product.objects.create(
            name="محصول تست",
            price=1000,
            stock=5,
            category=category,
            brand=brand,
        )
        order = self._expired_order()
        product.stock -= 2
        product.save(update_fields=["stock"])
        from apps.orders.models import OrderItem
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=2,
            unit_price=1000,
            total_price=2000,
        )
        OrderService.cancel_expired_orders()
        product.refresh_from_db()
        self.assertEqual(product.stock, 5)

    def test_cancelling_order_removes_coupon_usage(self):
        now = timezone.now()
        order = self._expired_order()
        discount = Discount.objects.create(
            title="تخفیف تست",
            code="TEST10",
            discount_type=Discount.DiscountType.PERCENTAGE,
            value=10,
            target_type=Discount.TargetType.ORDER,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
            is_active=True,
        )
        CouponUsage.objects.create(
            user=self.user,
            discount=discount,
            order=order,
        )
        OrderService.cancel_expired_orders()
        self.assertFalse(CouponUsage.objects.filter(order=order).exists())
