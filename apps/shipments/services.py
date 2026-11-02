from django.db import transaction
from apps.invoices.models import Invoice


@transaction.atomic
def sync_invoice_shipping(order_id, shipping_cost):
    invoice = Invoice.objects.select_for_update().filter(order_id=order_id).first()
    if not invoice:
        return
    invoice.shipping_amount = shipping_cost
    invoice.total_amount = invoice.subtotal - invoice.discount_amount + shipping_cost
    invoice.save(update_fields=["shipping_amount", "total_amount", "updated_at"])
