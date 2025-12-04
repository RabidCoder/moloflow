import os

from django.utils.text import slugify


def invoice_file_path(instance, filename):
    """Generate file path for uploaded invoice files."""
    base, ext = os.path.splitext(filename)
    date_str = instance.invoice.date.strftime("%Y-%m-%d")
    number_str = str(instance.invoice.number).zfill(6)
    version_str = f"v{instance.version}"
    safe_name = slugify(f"{date_str}-{number_str}-{version_str}")

    return f"invoices/{safe_name}{ext}"
