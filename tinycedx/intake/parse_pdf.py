from pathlib import Path
from typing import Any

from pypdf import PdfReader

from tinycedx.intake.parse_eml import _parse_key_value_lines


def parse_pdf(pdf_path: Path) -> dict[str, Any] | None:
    if not pdf_path.exists():
        return None
    reader = PdfReader(str(pdf_path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    fields = _parse_key_value_lines(text)
    rec_id = (fields.get("Id") or "").strip() or None
    return {
        "id": rec_id,
        "source_format": "pdf",
        "source_file": pdf_path.name,
        "raw_fields": fields,
    }
