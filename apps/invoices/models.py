from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.expressions import RawSQL
from apps.orders.models import Order
from django.core.validators import MinValueValidator
from apps.catalog.models import Product


class Invoice(models.Model):

    class InvoiceStatus(models.TextChoices):
        ISSUED = "issued", "صادر شده"
        CANCELLED = "cancelled", "لغو شده"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    order = models.OneToOneField(Order,on_delete=models.PROTECT,related_name="invoice",verbose_name="سفارش")
    invoice_number = models.PositiveIntegerField(
        db_default=RawSQL("nextval('invoices_invoice_number_seq')", []),
        unique=True,
        editable=False,
        verbose_name="شماره فاکتور"
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="مبلغ کالاها")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="مبلغ تخفیف")
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="هزینه ارسال")
    total_amount = models.DecimalField( max_digits=12, decimal_places=0, verbose_name="مبلغ نهایی")
    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, verbose_name="وضعیت فاکتور")
    issued_at = models.DateTimeField(verbose_name="زمان صدور")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاریخ ویرایش")

    def clean(self):
        super().clean()
        if self.subtotal < 0:
            raise ValidationError({
                "subtotal": "مبلغ کالاها نمی‌تواند کمتر از صفر باشد."
            })
        if self.discount_amount < 0:
            raise ValidationError({
                "discount_amount": "مبلغ تخفیف نمی‌تواند کمتر از صفر باشد."
            })
        if self.shipping_amount < 0:
            raise ValidationError({
                "shipping_amount": "هزینه ارسال نمی‌تواند کمتر از صفر باشد."
            })
        if self.total_amount < 0:
            raise ValidationError({
                "total_amount": "مبلغ نهایی نمی‌تواند کمتر از صفر باشد."
            })

    class Meta:
        verbose_name = "فاکتور"
        verbose_name_plural = "فاکتورها"
        ordering = ("-created_at",)

    def __str__(self):
        return str(self.invoice_number)



class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, verbose_name="شناسه")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items", verbose_name="فاکتور")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="محصول")
    product_name = models.CharField(max_length=100, verbose_name="نام محصول")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name="تعداد")
    unit_price = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="قیمت واحد")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="مبلغ تخفیف")
    total_price = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="مبلغ نهایی")

    def clean(self):
        super().clean()
        if self.unit_price < 0:
            raise ValidationError({
                "unit_price": "قیمت واحد نمی‌تواند کمتر از صفر باشد."
            })
        if self.discount_amount < 0:
            raise ValidationError({
                "discount_amount": "مبلغ تخفیف نمی‌تواند کمتر از صفر باشد."
            })
        if self.total_price < 0:
            raise ValidationError({
                "total_price": "مبلغ نهایی نمی‌تواند کمتر از صفر باشد."
            })

    class Meta:
        verbose_name = "آیتم فاکتور"
        verbose_name_plural = "آیتم‌های فاکتور"

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.product_name}"
