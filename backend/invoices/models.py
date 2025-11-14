from django.db import models

from core.utils import invoice_file_path


class Invoice(models.Model):
    """Model representing an invoice."""

    number = models.IntegerField(
        "number", unique=True, help_text="Unique invoice number as shown on the document."
    )
    date = models.DateField("date", help_text="Date of the invoice.")
    file = models.FileField(
        "file",
        upload_to=invoice_file_path,
        blank=True,
        null=True,
        help_text="Original invoice file (Excel) saved for parsing and verification.",
    )

    class Meta:
        verbose_name = "invoice"
        verbose_name_plural = "invoices"
        ordering = ["-date"]

    def __str__(self):
        return f"Invoice #{self.number} from {self.date}"


class Unit(models.Model):
    """Model representing a measurement unit."""

    name = models.CharField("name", max_length=20, help_text="Name of the unit (e.g., 'kilogram').")
    symbol = models.CharField("symbol", max_length=10, help_text="Symbol of the unit (e.g., 'kg').")
    aliases = models.JSONField(
        "aliases",
        default=list,
        blank=True,
        help_text="List of alternative names for the unit, used to recognize it in invoices.",
    )

    class Meta:
        verbose_name = "unit"
        verbose_name_plural = "units"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class InvoiceItem(models.Model):
    """Model representing an item in an invoice."""

    name = models.CharField("name", max_length=100, help_text="Item name as shown in the invoice.")
    quantity = models.DecimalField(
        "quantity",
        max_digits=10,
        decimal_places=2,
        help_text="Quantity of the item in the specified unit, with up to two decimal places.",
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="unit",
        related_name="used_in_items",
        help_text="Measurement unit of the item. Can be empty if not recognized.",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="invoice",
        related_name="items",
        help_text="The invoice to which this item belongs.",
    )

    class Meta:
        verbose_name = "invoice item"
        verbose_name_plural = "invoice items"
        ordering = ["-invoice__date", "name"]

    def __str__(self):
        return f"{self.name} - {self.quantity} {self.unit.symbol if self.unit else ''}"
