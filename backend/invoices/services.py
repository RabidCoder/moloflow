from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from invoices.models import ReportMonth


@transaction.atomic
def close_and_start_next_period(current_period):
    """Close the current reporting period and create the next one as OPEN."""
    current_period.close()

    # Move to January and the next year after December.
    if current_period.month == 12:
        next_month = 1
        next_year = current_period.year + 1
    else:
        next_month = current_period.month + 1
        next_year = current_period.year

    # The next reporting period starts the day after the previous one ends.
    next_start_date = current_period.end_date + timedelta(days=1)

    next_period = ReportMonth.objects.create(
        year=next_year,
        month=next_month,
        status=ReportMonth.StatusOption.OPEN,
        start_date=next_start_date,
    )


def close_period(period):
    """Close a reporting period according to its current status."""
    if period.status == ReportMonth.StatusOption.OPEN:
        close_and_start_next_period(period)
    elif period.status == ReportMonth.StatusOption.EDITING:
        period.close()
    else:
        raise ValidationError("A closed reporting period cannot be closed again.")
