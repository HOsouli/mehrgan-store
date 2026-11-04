
from decimal import Decimal

from django.db import transaction
from apps.invoices.models import Invoice
from apps.orders.models import Order
from .models import Shipment


@transaction.atomic
def sync_invoice_shipping(order_id, shipping_cost, method, carrier):
    invoice = Invoice.objects.select_for_update().filter(order_id=order_id).first()
    if not invoice:
        return
    is_store_courier = method == Shipment.ShipmentMethod.COURIER and carrier.strip() == "پیک فروشگاه"
    shipping_amount = shipping_cost if is_store_courier else Decimal(0)
    invoice.shipping_amount = shipping_amount
    invoice.total_amount = (invoice.subtotal - invoice.discount_amount + shipping_amount)
    invoice.save(update_fields=["shipping_amount", "total_amount", "updated_at"])

@transaction.atomic
def sync_order_status(order_id, shipment_status):
    mapping = {
        Shipment.ShipmentStatus.SHIPPED: Order.OrderStatus.SHIPPED,
        Shipment.ShipmentStatus.DELIVERED: Order.OrderStatus.DELIVERED,
    }
    new_status = mapping.get(shipment_status)
    if not new_status:
        return
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status in (Order.OrderStatus.PROCESSING, Order.OrderStatus.SHIPPED):
        order.status = new_status
        order.save(update_fields=["status", "updated_at"])
