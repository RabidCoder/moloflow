import os

from django.utils.text import slugify


def invoice_file_path(instance, filename):
    """Generate file path for uploaded invoice files."""

    base, ext = os.path.splitext(filename)
    date_str = instance.date.strftime("%Y-%m-%d")
    number_str = str(instance.number).zfill(6)
    safe_name = slugify(f"invoice-{number_str}-{date_str}")
    
    return f"invoices/{safe_name}{ext}"

