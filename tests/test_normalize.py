from __future__ import annotations

import pytest

from tests.conftest import SCHEMA_DIR
from tinycedx.normalize.normalize import _load_alias_map, normalize_record, to_number
from tinycedx.normalize.versions import resolve_versions


def _raw(fields: dict, order: int = 0) -> dict:
    return {"id": fields.get("Id") or fields.get("id"), "source_format": "eml", "source_file": "t.eml",
            "source_version_hash": None, "intake_order": order, "raw_fields": fields}


@pytest.mark.parametrize("value,expected", [
    (5000, 5000.0), ("5,050", 5050.0), ("$12,500.50 retainer", 12500.5),
    (None, None), ("TBD", None), ("n/a", None), ("no figure", None),
])
def test_to_number(value, expected):
    assert to_number(value) == expected


def test_known_alias_is_mapped_and_logged_as_drift():
    rec = normalize_record(_raw({"Id": "X-1", "Owner": "a", "Deadline": "2026-09-01", "Category": "review",
                                 "Retainer": "4,000", "Notes": "n"}), _load_alias_map(SCHEMA_DIR))
    assert rec["amount"] == 4000.0
    assert rec["category"] == "REVIEW"
    assert [(e["from_field"], e["to_field"]) for e in rec["schema_drift_events"]] == [("Retainer", "amount")]


def test_unseen_rename_is_inferred_structurally():
    rec = normalize_record(_raw({"Id": "X-2", "Owner": "a", "Deadline": "2026-09-01", "Category": "REVIEW",
                                 "TotalFeeXYZ": "7300", "Notes": "n"}), _load_alias_map(SCHEMA_DIR))
    assert rec["amount"] == 7300.0
    assert rec["schema_drift_events"][-1]["from_field"] == "TotalFeeXYZ"


def test_ambiguous_leftovers_are_not_guessed():
    rec = normalize_record(_raw({"Id": "X-3", "Owner": "a", "Deadline": "2026-09-01", "Category": "REVIEW",
                                 "FeeA": "1", "FeeB": "2", "Notes": "n"}), _load_alias_map(SCHEMA_DIR))
    assert rec["amount"] is None
    assert rec["schema_drift_events"] == []


def test_type_incompatible_leftover_is_not_mapped():
    rec = normalize_record(_raw({"Id": "X-4", "Owner": "a", "Category": "REVIEW", "Amount": "10",
                                 "Due_On": "soon", "Notes": "n"}), _load_alias_map(SCHEMA_DIR))
    assert rec["deadline"] is None


def test_higher_version_wins_regardless_of_order():
    recs = [{"id": "R", "version": 2, "intake_order": 0, "source_file": "b"},
            {"id": "R", "version": 1, "intake_order": 1, "source_file": "a"},
            {"id": "S", "version": 1, "intake_order": 2, "source_file": "c"}]
    kept, superseded = resolve_versions(recs)
    assert [(r["id"], r["version"]) for r in kept] == [("R", 2), ("S", 1)]
    assert [(r["id"], r["version"]) for r in superseded] == [("R", 1)]
    assert superseded[0]["superseded_by"] == {"version": 2, "source_file": "b"}
