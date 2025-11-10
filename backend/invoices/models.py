from django.db import models


class Invoice(models.Model):
    number = models.IntegerField("Number", unique=True)
    date = models.DateTimeField("Date")
    file = models.FileField("File")

    class Meta:
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"


class Unit(models.Model):
    name = models.CharField("Name", max_length=20)
    symbol = models.CharField("Symbol", max_length=10)
    aliases = models.JSONField("Aliases")

    class Meta:
        verbose_name = "Unit"
        verbose_name_plural = "Units"


class InvoiceItem(models.Model):
    name = models.CharField("Name", max_length=50)
    quantity = models.DecimalField("Quantity", max_digits=10, decimal_places=2)
    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Unit",
        related_name="used_in_items",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Invoice",
        related_name="items",
    )

    class Meta:
        verbose_name = "Invoice Item"
        verbose_name_plural = "Invoice Items"
