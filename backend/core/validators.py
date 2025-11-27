import magic
import xlrd
from io import BytesIO
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat
from openpyxl import load_workbook

from core.constants import ALLOWED_MIME_TYPES, MAX_FILE_SIZE


def validate_invoice_file(file):
    """Validate an uploaded invoice file."""
    # --- Check that file is provided ---
    if not file:
        raise ValidationError("No file was uploaded.")

    # --- Check size ---
    if file.size == 0:
        raise ValidationError("Uploaded file is empty.")

    if file.size > MAX_FILE_SIZE:
        raise ValidationError(
            f"File is too large ({filesizeformat(file.size)}). "
            f"Maximum allowed size is {filesizeformat(MAX_FILE_SIZE)}."
        )

    # --- Check MIME type (weak check) ---
    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)

    if mime not in ALLOWED_MIME_TYPES:
        raise ValidationError(f"Invalid file type: {mime}")

    # --- Determine extension ---
    filename = file.name.lower()

    if "." not in filename:
        raise ValidationError("File must have an extension.")

    ext = filename.rsplit(".", 1)[1]

    # --- Load file into memory (safe for small Excel files) ---
    data = file.read()
    file.seek(0)

    # --- Deep check: try to open file as real Excel ---
    try:
        if ext == "xlsx":
            load_workbook(BytesIO(data))
        elif ext == "xls":
            xlrd.open_workbook(file_contents=data)
        else:
            raise ValidationError("Unsupported file extension.")
    except Exception:
        raise ValidationError("The file is not a valid Excel document.")

    # If everything passed - OK
