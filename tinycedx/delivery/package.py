from __future__ import annotations

from typing import Any

from tinycedx.hashutil import sha

BRAND = "Tiny CEDX — Law Firm Matter Operations"


def build_package(*, case_id: str, generated_at: str, delivered_records: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    package = {
        "case_id": case_id,
        "generated_at": generated_at,
        "brand": BRAND,
        "record_count": len(delivered_records),
        "records": [
            {"id": r["id"], "delivered_fields": r["delivered_fields"]}
            for r in sorted(delivered_records, key=lambda r: r["id"])
        ],
    }
    return package, sha(package)
