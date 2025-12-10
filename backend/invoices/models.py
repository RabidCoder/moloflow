from datetime import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction

from core.constants import NAME_UNIT_MAX_LENGTH, NAME_MAX_LENGTH, SYMBOL_MAX_LENGTH
from core.validators import validate_invoice_file
from core.utils import invoice_file_path


class ReportMonth(models.Model):
    """Model representing a reporting month."""

    year = models.IntegerField(
        validators=[MinValueValidator(2000)], help_text="Year of the report month."
    )
    month = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Month of the report month.",
    )
    is_closed = models.BooleanField(
        default=False, help_text="Indicates whether the report month is closed."
    )
    closed_at = models.DateTimeField(
        null=True, blank=True, help_text="Timestamp when the report month was closed."
    )

    class Meta:
        verbose_name = "report month"
        verbose_name_plural = "report months"
        unique_together = ("year", "month")
        ordering = ["-year", "-month"]

    def clean(self):
        super().clean()

        today = timezone.now()
        current_year = today.year
        current_month = today.month
        # Prevent setting a report month in the past
        if (self.year < current_year) or (self.year == current_year and self.month < current_month):
            raise ValidationError("Report month cannot be in the past.")
        # Prevent duplicate report months
        if (
            ReportMonth.objects.exclude(pk=self.pk)
            .filter(year=self.year, month=self.month)
            .exists()
        ):
            raise ValidationError("Report month for this year and month already exists.")
        # Prevent modifications if the report month is closed
        if self.pk:
            old = ReportMonth.objects.get(pk=self.pk)
            if old.is_closed and (self.year != old.year or self.month != old.month):
                raise ValidationError("Cannot modify year/month of a closed report month.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def close(self):
        """Close the report month."""
        if self.is_closed == True:
            return
        self.is_closed = True
        self.closed_at = timezone.now()
        self.save(update_fields=["is_closed", "closed_at"])

    def reopen(self):
        """Reopen the report month."""
        if not self.is_closed:
            return
        self.is_closed = False
        self.closed_at = None
        self.save(update_fields=["is_closed", "closed_at"])

    def __str__(self) -> str:
        return f"{self.month:02d}/{self.year} {'(Closed)' if self.is_closed else ''}"


class InvoiceVersion(models.Model):
    """Model representing a version of an invoice."""

    version = models.PositiveIntegerField(help_text="Version number of the invoice.")
    created_at = models.DateTimeField(
        auto_now_add=True, help_text="Timestamp when this version was created."
    )
    file = models.FileField(
        "file",
        upload_to=invoice_file_path,
        validators=[validate_invoice_file],
        help_text="Uploaded invoice file (excel).",
    )
    invoice = models.ForeignKey(
        "Invoice",
        on_delete=models.PROTECT,
        related_name="versions",
        help_text="The invoice to which this version belongs.",
    )

    class Meta:
        verbose_name = "invoice version"
        verbose_name_plural = "invoice versions"
        unique_together = ("invoice", "version")
        ordering = ["-version"]

    def clean(self):
        super().clean()
        # Validation logic
        if not self.invoice:
            raise ValidationError({"invoice": "Invoice must be set for the invoice version."})
        # Ensure the file is provided
        if not self.file:
            raise ValidationError({"file": "File must be set for the invoice version."})
        # Ensure version number is at least 1
        if self.version < 1:
            raise ValidationError({"version": "Version number must be at least 1."})

    @property
    def is_active(self) -> bool:
        """Return True if this version is the active version of the invoice."""
        return self.invoice.active_version_id == self.id

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.pk:
                # New version creation → check sequential version
                last_version = (
                    InvoiceVersion.objects.select_for_update()
                    .filter(invoice=self.invoice)
                    .aggregate(models.Max("version"))["version__max"]
                ) or 0

                if self.version != last_version + 1:
                    raise ValidationError(
                        f"Version must be sequential. Expected {last_version + 1}."
                    )

            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.invoice.active_version_id == self.id:
            raise ValidationError("Cannot delete the active version of the invoice.")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"Invoice #{self.invoice.number} - Version {self.version}"


class Invoice(models.Model):
    """Model representing an invoice."""

    number = models.IntegerField(
        "number",
        validators=[MinValueValidator(1)],
        help_text="Invoice number as shown on the document.",
    )
    date = models.DateField("date", help_text="Date of the invoice.")
    active_version = models.ForeignKey(
        InvoiceVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="active version",
        related_name="active_for_invoice",
        help_text="The currently active version of the invoice.",
    )
    report_month = models.ForeignKey(
        ReportMonth,
        on_delete=models.PROTECT,
        verbose_name="report month",
        related_name="invoices",
        help_text="The report month to which this invoice belongs.",
    )

    class Meta:
        verbose_name = "invoice"
        verbose_name_plural = "invoices"
        unique_together = ("number", "report_month")
        ordering = ["-date"]

    def clean(self):
        super().clean()
        # Validation logic
        if not self.report_month:
            raise ValidationError({"report_month": "Report month must be set for the invoice."})
        # Prevent modifications if the report month is closed
        if self.report_month.is_closed:
            raise ValidationError(
                {"report_month": "Cannot modify invoice in a closed report month."}
            )
        # Ensure invoice date is within the report month
        if (self.date.month, self.date.year) != (self.report_month.month, self.report_month.year):
            raise ValidationError({"date": "Invoice date must be within the report month."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def add_version(self, file):
        """
        Create a new version of this invoice with the given file.
        Automatically increments the version number and sets it as active.
        """
        with transaction.atomic():
            last_version = self.versions.order_by("-version").first()
            next_num = (last_version.version + 1) if last_version else 1

            new_version = InvoiceVersion(invoice=self, version=next_num, file=file)

            new_version.full_clean()
            new_version.save()

            self.active_version = new_version
            self.save(update_fields=["active_version"])

            return new_version

    def __str__(self) -> str:
        return f"Invoice #{self.number} from {self.date} (v{self.active_version.version if self.active_version else 'N/A'})"


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

    def clean(self):
        pass

        super().clean()

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
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="unit",
        related_name="used_in_items",
        help_text="Measurement unit of the item. Can be empty if not recognized.",
    )
    version = models.ForeignKey(
        InvoiceVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="invoice",
        related_name="items",
        help_text="The invoice to which this item belongs.",
    )
    is_unit_unknown = models.BooleanField(default=False)  # ДОПИЛИ

    class Meta:
        verbose_name = "invoice item"
        verbose_name_plural = "invoice items"
        ordering = ["-invoice__date", "name"]

    def clean(self):
        pass

        super().clean()

    def __str__(self) -> str:
        return f"{self.name} - {self.quantity} {self.unit.symbol if self.unit else ''}"


# ДОПИЛИ
class InvoiceParsingError(models.Model):
    version = models.ForeignKey(InvoiceVersion, on_delete=models.PROTECT)
    message = models.TextField()
    row = models.IntegerField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        pass
