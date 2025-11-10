from django.db import models


class Invoice(models.Model):
    number = models.IntegerField("number", unique=True)
    date = models.DateTimeField("date")
    file = models.FileField("file")

    class Meta:
        verbose_name = "invoice"
        verbose_name_plural = "invoices"
    
    def __str__(self):
        return f"Invoice #{self.number} from {self.date.date()}"


class Unit(models.Model):
    name = models.CharField("name", max_length=20)
    symbol = models.CharField("symbol", max_length=10)
    aliases = models.JSONField("aliases")

    class Meta:
        verbose_name = "unit"
        verbose_name_plural = "units"
    
    def __str__(self):
        return f"{self.name} ({self.symbol})"


class InvoiceItem(models.Model):
    name = models.CharField("name", max_length=50)
    quantity = models.DecimalField("quantity", max_digits=10, decimal_places=2)
    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="unit",
        related_name="used_in_items",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="invoice",
        related_name="items",
    )

    class Meta:
        verbose_name = "invoice item"
        verbose_name_plural = "invoice items"
    
    def __str__(self):
        return f"{self.name} - {self.quantity} {self.unit.symbol if self.unit else ''}"
