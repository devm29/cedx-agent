from __future__ import annotations

from typing import Any

from tinycedx.config import KNOWN_CATEGORIES

_HEDGE_MARKERS = [
    "unclear", "inconsistent", "tbd", "could be", "not attached",
    "conflicting", "ambiguous", "unsure", "unknown", "side letter",
    "pending confirmation", "to be determined",
]


def prefilter_low_confidence(record: dict[str, Any]) -> bool:
    category = (record.get("category") or "").strip().upper()
    notes = (record.get("notes") or "").lower()
    if category and category not in KNOWN_CATEGORIES:
        return True
    if any(marker in notes for marker in _HEDGE_MARKERS):
        return True
    return False
