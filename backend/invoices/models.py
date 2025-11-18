from django.core.validators import MinValueValidator
from django.db import models

from core.constants import NAME_UNIT_MAX_LENGTH, NAME_MAX_LENGTH, SYMBOL_MAX_LENGTH
from core.utils import invoice_file_path


class InvoiceVersion(models.Model):
    """Model representing a version of an invoice."""

    invoice = models.ForeignKey(
        "Invoice",
        on_delete=models.CASCADE,
        related_name="versions",
        help_text="The invoice to which this version belongs.",
    )
    version = models.PositiveIntegerField(help_text="Version number of the invoice.")
    created_at = models.DateTimeField(
        auto_now_add=True, help_text="Timestamp when this version was created."
    )
    file = models.FileField(
        "file",
        upload_to=invoice_file_path,
        blank=True,
        null=True,
        help_text="Uploaded invoice file (excel).",
    )

    class Meta:
        verbose_name = "invoice version"
        verbose_name_plural = "invoice versions"
        unique_together = ("invoice", "version")
        ordering = ["-version"]

    def __str__(self) -> str:
        return f"Invoice #{self.invoice.number} - Version {self.version}"


class Invoice(models.Model):
    """Model representing an invoice."""

    number = models.IntegerField(
        "number",
        unique=True,
        validators=[MinValueValidator(1)],
        help_text="Unique invoice number as shown on the document.",
    )
    date = models.DateField("date", help_text="Date of the invoice.")
    active_version = models.ForeignKey(
        InvoiceVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="active version",
        related_name="active_for_invoice",
        help_text="The currently active version of the invoice.",
    )

    class Meta:
        verbose_name = "invoice"
        verbose_name_plural = "invoices"
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"Invoice #{self.number} from {self.date}"


class Unit(models.Model):
    """Model representing a measurement unit."""

    name = models.CharField(
        "name", max_length=NAME_UNIT_MAX_LENGTH, help_text="Name of the unit (e.g., 'kilogram')."
    )
    symbol = models.CharField(
        "symbol", max_length=SYMBOL_MAX_LENGTH, help_text="Symbol of the unit (e.g., 'kg')."
    )
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

    def __str__(self) -> str:
        return f"{self.name} ({self.symbol})"


class InvoiceItem(models.Model):
    """Model representing an item in an invoice."""

    name = models.CharField(
        "name", max_length=NAME_MAX_LENGTH, help_text="Item name as shown in the invoice."
    )
    quantity = models.DecimalField(
        "quantity",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
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
    version = models.ForeignKey(
        InvoiceVersion,
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

    def __str__(self) -> str:
        return f"{self.name} - {self.quantity} {self.unit.symbol if self.unit else ''}"
