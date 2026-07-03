from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = REPO_ROOT / "seed"
SCHEMA_DIR = REPO_ROOT / "tinycedx" / "schema"


@pytest.fixture
def clean_record() -> dict:
    return {
        "id": "T-001", "owner": "a.test", "deadline": "2026-09-01", "category": "REVIEW",
        "amount": 5000.0, "notes": "routine matter", "version": 1,
    }


def good_draft(record: dict, **overrides) -> dict:
    fields = {
        "matter_id": record["id"], "responsible_attorney": record["owner"],
        "deadline": record["deadline"], "matter_type": record["category"],
        "matter_value": record["amount"], "summary": f"Routine matter for {record['owner']}.",
    }
    fields.update(overrides)
    return {"record_id": record["id"], "delivered_fields": fields, "confidence": 0.9,
            "abstain": False, "abstain_reason": None}
