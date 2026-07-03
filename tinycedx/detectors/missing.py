from __future__ import annotations

from typing import Any

from tinycedx.config import REQUIRED_FIELDS


def check_missing(record: dict[str, Any]) -> list[str]:
    missing = ["id"] if record.get("id_missing") else []
    for field in REQUIRED_FIELDS:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing
