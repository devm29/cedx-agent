from __future__ import annotations

from typing import Any


def build_exception_queue(exception_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": r["id"],
            "reason_code": r.get("reason_code"),
            "reason_class": r.get("reason_class"),
            "detail": r.get("detail"),
            "source_format": r.get("source_format"),
            "owner": r.get("owner"),
        }
        for r in sorted(exception_records, key=lambda r: r["id"])
    ]
