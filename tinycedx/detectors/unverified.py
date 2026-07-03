from __future__ import annotations

import re
from typing import Any

_OVERRIDE_PATTERN = re.compile(
    r"(ignore|disregard)\s+the\s+field|use\s+\S+\s+instead|"
    r"(real|actual|true)\s+(contract\s+)?(figure|amount|number|value)\s+is|"
    r"regardless\s+of\s+what\s+the\s+\w+\s+field\s+says",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _untrusted_override(record: dict[str, Any]) -> bool:
    notes = record.get("notes") or ""
    if not _OVERRIDE_PATTERN.search(notes):
        return False
    amount = record.get("amount")
    numbers_in_notes = [float(n.replace(",", "")) for n in _NUMBER_RE.findall(notes)]
    if amount is None or not numbers_in_notes:
        return True
    return any(abs(n - amount) > 1e-6 for n in numbers_in_notes)


def _business_invalid(record: dict[str, Any]) -> bool:
    amount = record.get("amount")
    return isinstance(amount, (int, float)) and amount < 0


def check_unverified_anomaly(record: dict[str, Any]) -> bool:
    return _untrusted_override(record) or _business_invalid(record)
