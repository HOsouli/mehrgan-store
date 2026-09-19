from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.catalog.models import Product
from apps.discounts.models import Discount, CouponUsage
from .models import Order, OrderItem, OrderAddress


class OrderService:

    @staticmethod
    def _round_amount(amount):
        return Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _calc_amount(discount, base_amount):
        if discount.discount_type == Discount.DiscountType.PERCENTAGE:
            return OrderService._round_amount(base_amount * discount.value / Decimal("100"))
        return OrderService._round_amount(discount.value)

    @staticmethod
    def _apply_order_discount(line_items, discount_amount, subtotal):
        if not subtotal or not discount_amount:
            return

        raw_discounts = []
        allocated = Decimal("0")

        for line in line_items:
            raw_discount = discount_amount * line["item_total"] / subtotal
            base_discount = raw_discount.quantize(Decimal("1"), rounding=ROUND_DOWN)
            raw_discounts.append({"line": line, "raw": raw_discount, "discount": base_discount})
            allocated += base_discount

        remaining = int(discount_amount - allocated)
        raw_discounts.sort(key=lambda item: item["raw"] - item["discount"], reverse=True)

        for item in raw_discounts:
            if remaining <= 0:
                break
            if item["discount"] < item["line"]["item_total"]:
                item["discount"] += Decimal("1")
                remaining -= 1

        for item in raw_discounts:
            line = item["line"]
            line_discount = min(item["discount"], line["item_total"])
            line["discount_amount"] = line_discount
            line["total_price"] = line["item_total"] - line_discount

    @staticmethod
    @transaction.atomic
    def create_order(user, validated_data):
        items_data = validated_data["items"]
        product_ids = [item["product_id"] for item in items_data]
        products = Product.objects.select_related("category", "brand").select_for_update().filter(id__in=product_ids)
        products_map = {str(p.id): p for p in products}

        if len(products_map) != len(set(product_ids)):
            raise ValidationError("یک یا چند محصول یافت نشد.")

        subtotal = Decimal("0")
        line_items = []
        for item in items_data:
            product = products_map[str(item["product_id"])]
            quantity = item["quantity"]
            if product.stock < quantity:
                raise ValidationError(f"موجودی محصول «{product.name}» کافی نیست.")
            unit_price = product.price
            item_total = unit_price * quantity
            subtotal += item_total
            line_items.append({
                "product": product,
                "quantity": quantity,
                "unit_price": unit_price,
                "item_total": item_total,
                "discount_amount": Decimal("0"),
                "total_price": item_total,
            })

        discount_code = validated_data.get("discount_code", "").strip().upper()
        discount = None
        discount_amount = Decimal("0")

        if discount_code:
            try:
                discount = Discount.objects.select_for_update().get(code=discount_code)
            except Discount.DoesNotExist:
                raise ValidationError("کد تخفیف معتبر نیست.")

            now = timezone.now()
            if not discount.is_active:
                raise ValidationError("کد تخفیف فعال نیست.")
            if now < discount.starts_at or now > discount.ends_at:
                raise ValidationError("کد تخفیف در این بازه زمانی قابل استفاده نیست.")
            if discount.eligible_users.exists() and not discount.eligible_users.filter(pk=user.pk).exists():
                raise ValidationError("این کد تخفیف برای شما قابل استفاده نیست.")
            if discount.minimum_order_amount is not None and subtotal < discount.minimum_order_amount:
                raise ValidationError("مبلغ سفارش به حداقل مبلغ لازم برای استفاده از این تخفیف نرسیده است.")
            if discount.total_usage_limit is not None and discount.usages.count() >= discount.total_usage_limit:
                raise ValidationError("سقف استفاده از این کد تخفیف تکمیل شده است.")
            if discount.per_user_limit is not None and discount.usages.filter(user=user).count() >= discount.per_user_limit:
                raise ValidationError("سقف استفاده شما از این کد تخفیف تکمیل شده است.")

            if discount.target_type == Discount.TargetType.PRODUCT:
                eligible_ids = set(discount.products.values_list("id", flat=True))
                for line in line_items:
                    if line["product"].id in eligible_ids:
                        line_discount = min(OrderService._calc_amount(discount, line["item_total"]), line["item_total"])
                        line["discount_amount"] = line_discount
                        line["total_price"] = line["item_total"] - line_discount
                        discount_amount += line_discount

            elif discount.target_type == Discount.TargetType.CATEGORY:
                eligible_ids = set(discount.categories.values_list("id", flat=True))
                for line in line_items:
                    if line["product"].category_id in eligible_ids:
                        line_discount = min(OrderService._calc_amount(discount, line["item_total"]), line["item_total"])
                        line["discount_amount"] = line_discount
                        line["total_price"] = line["item_total"] - line_discount
                        discount_amount += line_discount

            elif discount.target_type == Discount.TargetType.BRAND:
                eligible_ids = set(discount.brands.values_list("id", flat=True))
                for line in line_items:
                    if line["product"].brand_id in eligible_ids:
                        line_discount = min(OrderService._calc_amount(discount, line["item_total"]), line["item_total"])
                        line["discount_amount"] = line_discount
                        line["total_price"] = line["item_total"] - line_discount
                        discount_amount += line_discount

            elif discount.target_type == Discount.TargetType.ORDER:
                order_discount = min(OrderService._calc_amount(discount, subtotal), subtotal)
                discount_amount = order_discount
                OrderService._apply_order_discount(line_items, order_discount, subtotal)

            discount_amount = min(discount_amount, subtotal)

        shipping_amount = Decimal("0")
        total_amount = subtotal - discount_amount + shipping_amount

        order = Order.objects.create(
            user=user,
            subtotal=subtotal,
            discount_amount=discount_amount,
            shipping_amount=shipping_amount,
            total_amount=total_amount,
            discount=discount,
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        for line in line_items:
            OrderItem.objects.create(
                order=order,
                product=line["product"],
                quantity=line["quantity"],
                unit_price=line["unit_price"],
                discount_amount=line["discount_amount"],
                total_price=line["total_price"],
            )
            line["product"].stock -= line["quantity"]
            line["product"].save(update_fields=["stock"])

        OrderAddress.objects.create(
            order=order,
            recipient_name=validated_data["recipient_name"],
            province=validated_data["province"],
            city=validated_data["city"],
            address=validated_data["address"],
            postal_code=validated_data["postal_code"],
            recipient_phone=validated_data["recipient_phone"],
        )

        if discount:
            CouponUsage.objects.create(user=user, discount=discount, order=order)

        return order
