from __future__ import annotations

from datetime import date
from typing import Any


def check_stale(record: dict[str, Any], pipeline_now: date) -> bool:
    deadline_str = record.get("deadline")
    if not deadline_str:
        return False
    try:
        y, m, d = (int(x) for x in str(deadline_str).split("-"))
        deadline = date(y, m, d)
    except (ValueError, TypeError):
        return False
    return deadline < pipeline_now
