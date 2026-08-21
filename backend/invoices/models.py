from django import core
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, MaxLengthValidator
from django.db import models, transaction
from django.utils import timezone

from core import constants
from core.mixins import FullCleanSaveMixin
from core.utils import invoice_file_path
from core.validators import validate_invoice_file


def current_year():
    """Return the current calendar year."""
    return timezone.now().year


class ReportMonth(FullCleanSaveMixin, models.Model):
    """Model representing a reporting month."""

    class StatusOption(models.TextChoices):
        """
        Statuses representing the lifecycle of a reporting month.

        OPEN:
            Active reporting period. New invoices are automatically assigned
            to this period. Manual corrections and closing are allowed.

        CLOSED:
            Completed reporting period. New data cannot be added automatically.
            The period can be reopened for corrections or restored as the active
            reporting period.

        EDITING:
            Previously closed reporting period opened for corrections.
            New invoices are not assigned to this period. Manual changes are
            allowed before closing again.
        """

        OPEN = "open", "Открыт"
        CLOSED = "closed", "Закрыт"
        EDITING = "editing", "На редакции"

    year = models.IntegerField(
        "год",
        default=current_year(),
        validators=[MinValueValidator(constants.MIN_YEAR)],
        help_text="Год отчётного периода.",
    )
    month = models.IntegerField(
        "месяц",
        validators=[MinValueValidator(constants.MIN_MONTH), MaxValueValidator(constants.MAX_MONTH)],
        help_text="Месяц отчётного периода.",
    )
    status = models.CharField(
        "статус",
        max_length=constants.MAX_STATUS_LENGTH,
        choices=StatusOption,
        default=StatusOption.OPEN,
        help_text="Текущий статус отчётного периода.",
    )
    closed_at = models.DateTimeField(
        "дата закрытия",
        null=True,
        blank=True,
        help_text="Дата и время первого закрытия отчётного периода.",
    )
    start_date = models.DateField("дата начала", help_text="Первый день отчётного периода.")
    end_date = models.DateField(
        "дата окончания", null=True, blank=True, help_text="Последний день отчётного периода."
    )
    last_modified = models.DateTimeField(
        "изменено", auto_now=True, help_text="Дата и время последнего изменения."
    )

    class Meta:
        verbose_name = "отчётный период"
        verbose_name_plural = "отчётные периоды"
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["year", "month"],
                name="uniq_report_month_year_month",
            ),
            models.UniqueConstraint(
                fields=["status"],
                condition=models.Q(status="open"),
                name="uniq_open_report_month",
            ),
        ]

    def clean(self):
        super().clean()

        # An open reporting period cannot have closing information.
        # Closing dates are assigned only after the period is closed.
        if self.status == self.StatusOption.OPEN:
            if self.end_date or self.closed_at:
                raise ValidationError(
                    "An open reporting period cannot have an end date or closing timestamp."
                )

        # Closed and editing periods represent periods that were already closed.
        # They must preserve the closing date and closing timestamp.
        else:
            if not self.end_date or not self.closed_at:
                raise ValidationError(
                    "Closed or editing reporting periods must have an end date and closing timestamp."
                )

            # The end date must match the calendar date when the period was closed.
            if self.end_date != self.closed_at.date():
                raise ValidationError("The end date must match the closing date.")

            # The reporting period cannot end before it starts.
            if self.end_date and self.end_date < self.start_date:
                raise ValidationError("The end date cannot be earlier than the start date.")

    def close(self):
        """Close the reporting period, recording closing information only on first closure."""
        if self.status == self.StatusOption.CLOSED:
            return
        elif self.status == self.StatusOption.OPEN:
            self.closed_at = timezone.now()
            self.end_date = self.closed_at.date()
        self.status = self.StatusOption.CLOSED
        self.save()

    def start_editing(self):
        """Move a closed reporting period to the editing state."""
        if self.status == self.StatusOption.EDITING:
            return
        elif self.status == self.StatusOption.OPEN:
            raise ValidationError("An open reporting period cannot be moved to editing.")
        self.status = self.StatusOption.EDITING
        self.save()

    def __str__(self) -> str:
        return f"{self.month:02d}/{self.year} ({self.get_status_display()})"


class InvoiceVersion(models.Model):
    """Model representing a version of an invoice."""

    version = models.PositiveIntegerField("версия", help_text="Порядковый номер версии накладной.")
    created_at = models.DateTimeField(
        "создано", auto_now_add=True, help_text="Дата и время создания версии."
    )
    file = models.FileField(
        "файл",
        upload_to=invoice_file_path,
        validators=[validate_invoice_file],
        help_text="Файл накладной в формате Excel.",
    )
    invoice = models.ForeignKey(
        "Invoice",
        on_delete=models.PROTECT,
        verbose_name="накладная",
        related_name="versions",
        help_text="Накладная, к которой относится эта версия.",
    )
    warehouse_keeper = models.CharField(
        "кладовщик",
        max_length=constants.MAX_NAME_LENGTH,
        null=True,
        blank=True,
        help_text="ФИО кладовщика, указанное в накладной.",
    )

    class Meta:
        verbose_name = "версия накладной"
        verbose_name_plural = "версии накладных"
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

    def set_as_active(self):
        """Set this version as the active version of its invoice."""
        self.invoice.active_version = self
        self.invoice.save(update_fields=["active_version"])

    @classmethod
    def create_next_version(cls, invoice, file):
        """Create the next version of the given invoice with the provided file."""
        with transaction.atomic():
            # Determine the next sequential version number.
            last = (
                cls.objects.select_for_update()
                .filter(invoice=invoice)
                .aggregate(models.Max("version"))
            )["version__max"] or 0

            new_version = cls.objects.create(
                invoice=invoice,
                version=last + 1,
                file=file,
            )

            new_version.set_as_active()

            return new_version

    @property
    def is_active(self) -> bool:
        """Return True if this version is the active version of the invoice."""
        return self.invoice.active_version_id == self.pk

    def __str__(self) -> str:
        return f"Invoice #{self.invoice.number} - Version {self.version}"


class Invoice(FullCleanSaveMixin, models.Model):
    """Model representing an invoice."""

    number = models.IntegerField(
        "номер",
        validators=[MinValueValidator(constants.MIN_INVOICE_NUMBER)],
        help_text="Номер накладной, указанный в документе.",
    )
    date = models.DateField("дата", help_text="Дата накладной, указанная в документе.")
    active_version = models.ForeignKey(
        InvoiceVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="активная версия",
        related_name="active_for_invoice",
        help_text="Текущая активная версия накладной.",
    )
    company = models.ForeignKey(
        "equipment.Company",
        on_delete=models.PROTECT,
        verbose_name="компания",
        related_name="invoices",
        help_text="Компания, к которой относится накладная.",
    )
    report_month = models.ForeignKey(
        ReportMonth,
        on_delete=models.PROTECT,
        verbose_name="отчётный период",
        related_name="invoices",
        help_text="Отчётный период, к которому относится накладная.",
    )

    class Meta:
        verbose_name = "накладная"
        verbose_name_plural = "накладные"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["number", "date", "company"],
                name="uniq_invoice_number_date_per_company",
            ),
        ]

    def clean(self):
        super().clean()

        # Prevent modifications if the report month is closed
        if self.report_month.status == self.report_month.StatusOption.CLOSED:
            raise ValidationError(
                {"report_month": "Cannot modify invoice in a closed report month."}
            )

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
        verbose_name="запчасть",
        related_name="invoice_items",
        help_text="Запчасть, указанная в строке накладной.",
    )
    nomenclature_number = models.CharField(
        "номенклатурный номер",
        max_length=constants.MAX_CODE_LENGTH,
        null=True,
        blank=True,
        help_text="Номенклатурный номер запчасти, указанный в документе.",
    )
    requested_quantity = models.DecimalField(
        "затребованное количество",
        max_digits=constants.MAX_DIGITS,
        decimal_places=constants.DECIMAL_PLACES,
        validators=[MinValueValidator(constants.MIN_QUANTITY)],
        help_text="Количество запчасти, указанное в колонке «Затребовано».",
    )
    released_quantity = models.DecimalField(
        "отпущенное количество",
        max_digits=constants.MAX_DIGITS,
        decimal_places=constants.DECIMAL_PLACES,
        validators=[MinValueValidator(constants.MIN_QUANTITY)],
        help_text="Фактически отпущенное количество запчасти.",
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="единица измерения",
        related_name="used_in_items",
        help_text="Единица измерения запчасти.",
    )
    unit_code = models.CharField(
        "код единицы измерения",
        max_length=constants.MAX_CODE_LENGTH,
        null=True,
        blank=True,
        help_text="Код единицы измерения, указанный в документе.",
    )
    unit_price = models.DecimalField(
        "цена за единицу",
        max_digits=constants.MAX_DIGITS,
        decimal_places=constants.DECIMAL_PLACES,
        validators=[MinValueValidator(constants.MIN_PRICE)],
        help_text="Цена одной единицы запчасти, указанная в документе.",
    )
    total_price = models.DecimalField(
        "сумма",
        max_digits=constants.MAX_DIGITS,
        decimal_places=constants.DECIMAL_PLACES,
        validators=[MinValueValidator(constants.MIN_PRICE)],
        help_text="Общая сумма по строке накладной.",
    )
    version = models.ForeignKey(
        InvoiceVersion,
        on_delete=models.PROTECT,
        verbose_name="версия накладной",
        related_name="items",
        help_text="Версия накладной, из которой была получена эта строка.",
    )

    class Meta:
        verbose_name = "строка накладной"
        verbose_name_plural = "строки накладной"
        ordering = ["-version__invoice__date", "spare_part__name"]

    def __str__(self) -> str:
        return f"{self.spare_part.name} - {self.released_quantity} {self.unit.symbol if self.unit else ''}"


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
