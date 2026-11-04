
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import CustomUser
from apps.orders.models import Order
from apps.invoices.models import Invoice
from .models import Shipment
from .services import sync_invoice_shipping, sync_order_status


class ShipmentServiceTests(TestCase):
    def setUp(self):
        user = CustomUser.objects.create_user(phone_number="09123456789")
        self.order = Order.objects.create(
            user=user,
            status=Order.OrderStatus.PROCESSING,
            subtotal=1000,
            total_amount=1000,
            expires_at=timezone.now(),
        )
        self.invoice = Invoice.objects.create(
            order=self.order,
            subtotal=1000,
            discount_amount=100,
            shipping_amount=0,
            total_amount=900,
            status=Invoice.InvoiceStatus.ISSUED,
            issued_at=timezone.now(),
        )

    def test_store_courier_cost_is_added_to_invoice(self):
        sync_invoice_shipping(
            self.order.pk, Decimal(50000),
            Shipment.ShipmentMethod.COURIER, "پیک فروشگاه"
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.shipping_amount, Decimal(50000))
        self.assertEqual(self.invoice.total_amount, Decimal(50900))

    def test_snapp_cost_is_not_added_to_invoice(self):
        sync_invoice_shipping(
            self.order.pk, Decimal(50000),
            Shipment.ShipmentMethod.COURIER, "اسنپ"
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.shipping_amount, Decimal(0))
        self.assertEqual(self.invoice.total_amount, Decimal(900))

    def test_post_cost_is_not_added_to_invoice(self):
        sync_invoice_shipping(
            self.order.pk, Decimal(50000),
            Shipment.ShipmentMethod.POST, "پست"
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.shipping_amount, Decimal(0))
        self.assertEqual(self.invoice.total_amount, Decimal(900))

    def test_changing_store_courier_to_snapp_removes_shipping_cost(self):
        sync_invoice_shipping(
            self.order.pk, Decimal(50000),
            Shipment.ShipmentMethod.COURIER, "پیک فروشگاه"
        )
        sync_invoice_shipping(
            self.order.pk, Decimal(50000),
            Shipment.ShipmentMethod.COURIER, "اسنپ"
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.shipping_amount, Decimal(0))
        self.assertEqual(self.invoice.total_amount, Decimal(900))

    def test_shipped_moves_processing_order(self):
        sync_order_status(self.order.pk, Shipment.ShipmentStatus.SHIPPED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.SHIPPED)

    def test_cancelled_order_is_not_reactivated(self):
        Order.objects.filter(pk=self.order.pk).update(status=Order.OrderStatus.CANCELLED)
        sync_order_status(self.order.pk, Shipment.ShipmentStatus.DELIVERED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CANCELLED)
