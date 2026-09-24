from django.core.management.base import BaseCommand
from apps.orders.services import OrderService


class Command(BaseCommand):
    help = "Automatic cancellation of expired orders"

    def handle(self, *args, **options):
        count = OrderService.cancel_expired_orders()
        self.stdout.write(self.style.SUCCESS(f"{count} سفارش منقضی لغو شد."))

