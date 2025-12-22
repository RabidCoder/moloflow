from django.db import models

from core import constants


class BaseModel(models.Model):
    """Abstract base model with common fields."""

    name = models.CharField(
        "name", max_length=constants.MAX_NAME_LENGTH, help_text="Name of the entity."
    )
    active = models.BooleanField(
        "active", default=True, help_text="Indicates if the entity is active."
    )

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Company(BaseModel):
    """Model representing a company that owns equipment."""

    class Meta:
        verbose_name = "company"
        verbose_name_plural = "companies"


class Equipment(BaseModel):
    """Model representing equipment owned by a company."""

    inventory_number = models.CharField(
        "inventory number",
        max_length=constants.MAX_SYMBOL_LENGTH,
        help_text="Inventory number of the equipment.",
    )
    sequence_number = models.PositiveSmallIntegerField(
        "sequence number", help_text="Sequence number of the equipment."
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="equipments",
        verbose_name="company",
        help_text="Company that owns the equipment.",
    )

    class Meta:
        verbose_name = "equipment"
        verbose_name_plural = "equipments"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "inventory_number"],
                name="unique_inventory_number_per_company",
            ),
            models.UniqueConstraint(
                fields=["company", "name", "sequence_number"],
                name="uniq_equipment_sequence_per_company_and_name",
            ),
        ]


class SparePart(BaseModel):
    """Model representing a spare part for equipment."""

    unit = models.ForeignKey(
        "invoices.Unit",
        on_delete=models.PROTECT,
        verbose_name="unit",
        related_name="spare_parts",
        help_text="Unit of measurement for the spare part.",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="spare_parts",
        verbose_name="company",
        help_text="Company that owns the spare part.",
    )

    class Meta:
        verbose_name = "spare part"
        verbose_name_plural = "spare parts"
