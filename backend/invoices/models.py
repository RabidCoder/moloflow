from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, MaxLengthValidator
from django.db import models, transaction
from django.utils import timezone

from core import constants
from core.mixins import FullCleanSaveMixin
from core.utils import invoice_file_path
from core.validators import validate_invoice_file


class ReportMonth(FullCleanSaveMixin, models.Model):
    """Model representing a reporting month."""

    year = models.IntegerField(
        validators=[MinValueValidator(constants.MIN_YEAR)], help_text="Year of the report month."
    )
    month = models.IntegerField(
        validators=[MinValueValidator(constants.MIN_MONTH), MaxValueValidator(constants.MAX_MONTH)],
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
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["year", "month"],
                name="uniq_report_month_year_month",
            ),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Store old values for year and month to prevent modifications on closed report months
        self._old_year = self.year
        self._old_month = self.month

    def clean(self):
        super().clean()
        # Prevent duplicate report months
        if (
            ReportMonth.objects.exclude(pk=self.pk)
            .filter(year=self.year, month=self.month)
            .exists()
        ):
            raise ValidationError("Report month for this year and month already exists.")

    def save(self, *args, **kwargs):
        # Check for modifications to locked fields
        if (
            not self._state.adding
            and self.is_closed
            and (self.year != self._old_year or self.month != self._old_month)
        ):
            raise ValidationError("Cannot modify year/month of a closed report month.")
        super().save(*args, **kwargs)

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
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "version"],
                name="uniq_invoice_version_per_invoice",
            ),
        ]

    def clean(self):
        super().clean()
        # Ensure the file is provided
        if not self.file:
            raise ValidationError({"file": "File must be set for the invoice version."})
        # Ensure version number is at least 1
        if self.version < 1:
            raise ValidationError({"version": "Version number must be at least 1."})

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

    @classmethod
    def create_next(cls, invoice, file):
        """Create the next version of the given invoice with the provided file."""
        with transaction.atomic():
            last = (
                cls.objects.select_for_update()
                .filter(invoice=invoice)
                .aggregate(models.Max("version"))
            )["version__max"] or 0

            return cls.objects.create(invoice=invoice, version=last + 1, file=file)

    @property
    def is_active(self) -> bool:
        """Return True if this version is the active version of the invoice."""
        return self.invoice.active_version_id == self.id

    def __str__(self) -> str:
        return f"Invoice #{self.invoice.number} - Version {self.version}"


class Invoice(FullCleanSaveMixin, models.Model):
    """Model representing an invoice."""

    number = models.IntegerField(
        "number",
        validators=[MinValueValidator(constants.MIN_INVOICE_NUMBER)],
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
    company = models.ForeignKey(
        "equipment.Company",
        on_delete=models.PROTECT,
        verbose_name="company",
        related_name="invoices",
        help_text="The company to which this invoice belongs.",
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
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["number", "report_month"],
                name="uniq_invoice_number_per_report_month",
            ),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Store old values for year and month to prevent changing report month if versions exist
        self._old_report_month = self.report_month

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
        if (
            not self._state.adding
            and self.report_month != self._old_report_month
            and self.versions.exists()
        ):
            raise ValidationError("Cannot modify report month if versions exist.")
        super().save(*args, **kwargs)

    def add_version(self, file):
        """
        Create a new version of this invoice with the given file.
        """
        return InvoiceVersion.create_next(self, file)

    def __str__(self) -> str:
        return f"Invoice #{self.number} from {self.date} (v{self.active_version.version if self.active_version else 'N/A'})"


class Unit(models.Model):
    """Model representing a measurement unit."""

    name = models.CharField(
        "name",
        max_length=constants.MAX_NAME_LENGTH,
        help_text="Name of the unit (e.g., 'kilogram').",
    )
    symbol = models.CharField(
        "symbol",
        max_length=constants.MAX_SYMBOL_LENGTH,
        help_text="Symbol of the unit (e.g., 'kg').",
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
        constraints = [
            models.UniqueConstraint(
                fields=["name", "symbol"],
                name="uniq_unit_name_symbol",
            ),
        ]

    def clean(self):
        super().clean()
        # Validation logic
        if not self.symbol or not self.symbol.strip():
            raise ValidationError({"symbol": "Unit symbol cannot be empty or just whitespace."})
        # Validate aliases
        if not all(isinstance(alias, str) and alias.strip() for alias in self.aliases):
            raise ValidationError({"aliases": "All aliases must be non-empty strings."})

    def __str__(self) -> str:
        return f"{self.name} ({self.symbol})"


class InvoiceItem(FullCleanSaveMixin, models.Model):
    """Model representing an item in an invoice."""

    spare_part = models.ForeignKey(
        "equipment.SparePart",
        on_delete=models.PROTECT,
        verbose_name="spare part",
        related_name="invoice_items",
        help_text="The spare part associated with this invoice item.",
    )
    quantity = models.DecimalField(
        "quantity",
        max_digits=constants.MAX_DIGITS,
        decimal_places=constants.DECIMAL_PLACES,
        validators=[MinValueValidator(constants.MIN_QUANTITY)],
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
        verbose_name="invoice",
        related_name="items",
        help_text="The invoice to which this item belongs.",
    )

    class Meta:
        verbose_name = "invoice item"
        verbose_name_plural = "invoice items"
        ordering = ["-version__invoice__date", "spare_part__name"]

    @property
    def is_unit_unknown(self) -> bool:
        """Return True if the unit is unknown (i.e., unit is None)."""
        return self.unit is None

    def __str__(self) -> str:
        return f"{self.spare_part.name} - {self.quantity} {self.unit.symbol if self.unit else ''}"


class InvoiceParsingError(models.Model):
    """Model representing an error encountered while parsing an invoice."""

    message = models.TextField(
        "message",
        validators=[MaxLengthValidator(constants.MAX_ERROR_MESSAGE_LENGTH)],
        help_text="Error message describing the parsing issue.",
    )
    row = models.PositiveIntegerField(
        "row",
        null=True,
        help_text="Row number where error occurred, or NULL if the error is not row-specific.",
    )
    created_at = models.DateTimeField(
        "created at", auto_now_add=True, help_text="Timestamp when the error was recorded."
    )
    version = models.ForeignKey(
        InvoiceVersion,
        on_delete=models.PROTECT,
        verbose_name="invoice version",
        related_name="parsing_errors",
        help_text="The invoice version associated with this parsing error.",
    )

    class Meta:
        verbose_name = "invoice parsing error"
        verbose_name_plural = "invoice parsing errors"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["version"]), models.Index(fields=["created_at"])]

    def __str__(self) -> str:
        return f"Error in Invoice #{self.version.invoice.number} v{self.version.version}: {self.message[:50]}"


class WriteOffFact(models.Model):
    """Model representing a write-off fact for a spare part."""

    # main fields
    spare_part = models.ForeignKey(
        "equipment.SparePart",
        on_delete=models.PROTECT,
        related_name="write_off_facts",
        verbose_name="spare part",
        help_text="The spare part that was written off.",
    )
    quantity = models.DecimalField(
        "quantity",
        max_digits=constants.MAX_DIGITS,
        decimal_places=constants.DECIMAL_PLACES,
        help_text="Quantity of spare parts written off.",
    )
    fact_date = models.DateField("fact date", help_text="Date when the write-off occurred.")
    # snapshot fields
    equipment_name = models.CharField(
        "equipment name",
        max_length=constants.MAX_NAME_LENGTH,
        help_text="Name of the equipment at the time of write-off.",
    )
    equipment_inventory_number = models.CharField(
        "inventory number",
        max_length=constants.MAX_NAME_LENGTH,
        help_text="Inventory number of the equipment at the time of write-off.",
    )
    equipment_sequence_number = models.PositiveSmallIntegerField(
        "sequence number", help_text="Sequence number of the equipment at the time of write-off."
    )
    equipment_company_name = models.CharField(
        "company name",
        max_length=constants.MAX_NAME_LENGTH,
        help_text="Company owning the equipment at the time of write-off.",
    )
    # metadata fields
    invoice_item = models.ForeignKey(
        InvoiceItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="write_off_facts",
        verbose_name="invoice item",
        help_text="Optional invoice item that was the source of this write-off.",
    )
    report_month = models.ForeignKey(
        ReportMonth,
        on_delete=models.PROTECT,
        related_name="write_off_facts",
        verbose_name="report month",
        help_text="The report month to which this fact belongs.",
    )
    created_at = models.DateTimeField(
        "created at", auto_now_add=True, help_text="Timestamp when the write-off fact was created."
    )
    # Source
    source = models.CharField(
        "source",
        max_length=constants.MAX_SYMBOL_LENGTH,
        choices=constants.SOURCE_CHOICES,
        help_text="Source of the write-off: invoice or manual entry.",
    )
    status = models.CharField(
        "status",
        max_length=constants.MAX_SYMBOL_LENGTH,
        choices=constants.STATUS_CHOICES,
        default="active",
        help_text="Status of the write-off fact for corrections.",
    )

    class Meta:
        verbose_name = "write-off fact"
        verbose_name_plural = "write-off facts"
        ordering = ["-fact_date"]

    def __str__(self) -> str:
        return f"{self.spare_part.name} - {self.quantity} pcs on {self.fact_date} ({self.status})"

    def cancel(self):
        """Cancel this write-off fact."""
        if self.status == "canceled":
            return
        self.status = "canceled"
        self.save(update_fields=["status"])

    def clone_as_manual(self, *, quantity, fact_date, equipment_snapshot):
        """Clone this write-off fact as a manual entry with updated fields."""
        return WriteOffFact.objects.create(
            spare_part=self.spare_part,
            quantity=quantity,
            fact_date=fact_date,
            equipment_name=equipment_snapshot.name,
            equipment_inventory_number=equipment_snapshot.inventory_number,
            equipment_sequence_number=equipment_snapshot.sequence_number,
            equipment_company_name=equipment_snapshot.company_name,
            invoice_item=None,
            report_month=self.report_month,
            source="manual",
            status="active",
        )
