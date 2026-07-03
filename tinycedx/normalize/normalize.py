import json
import re
from pathlib import Path
from typing import Any

CANONICAL_FIELDS = ("id", "owner", "deadline", "category", "amount", "notes", "version")
REQUIRED_FOR_DRIFT = ("id", "owner", "deadline", "category", "amount", "notes")

_NUMERIC_RE = re.compile(r"-?\d[\d,]*\.?\d*")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load_alias_map(schema_dir: Path) -> dict[str, list[str]]:
    path = schema_dir / "field_mapping.v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: [a.lower() for a in v] for k, v in data["aliases"].items()}


def to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() in {"null", "none", "n/a", "tbd"}:
        return None
    m = _NUMERIC_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _looks_like_date(value: Any) -> bool:
    return isinstance(value, str) and bool(_DATE_RE.match(value.strip()))


def _type_compatible(field: str, value: Any) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return False
    if field == "amount":
        return to_number(value) is not None
    if field == "deadline":
        return _looks_like_date(value)
    if field in {"id", "owner", "category", "notes", "version"}:
        return True
    return False


def normalize_record(raw: dict[str, Any], alias_map: dict[str, list[str]]) -> dict[str, Any]:
    raw_fields: dict[str, Any] = raw["raw_fields"]
    lower_keys = {k.lower(): k for k in raw_fields}

    canonical: dict[str, Any] = {f: None for f in CANONICAL_FIELDS}
    matched_raw_keys: set[str] = set()
    drift_events: list[dict[str, Any]] = []

    for field, aliases in alias_map.items():
        for alias in aliases:
            if alias in lower_keys:
                raw_key = lower_keys[alias]
                canonical[field] = raw_fields[raw_key]
                matched_raw_keys.add(raw_key)
                if alias != field:
                    drift_events.append({
                        "record_id": raw.get("id"), "from_field": raw_key, "to_field": field,
                    })
                break

    missing_fields = [f for f in REQUIRED_FOR_DRIFT if canonical.get(f) in (None, "")]
    unmatched_keys = [k for k in raw_fields if k not in matched_raw_keys]
    if len(missing_fields) == 1 and len(unmatched_keys) == 1:
        field = missing_fields[0]
        raw_key = unmatched_keys[0]
        value = raw_fields[raw_key]
        if _type_compatible(field, value):
            canonical[field] = value
            matched_raw_keys.add(raw_key)
            drift_events.append({
                "record_id": raw.get("id"),
                "from_field": raw_key,
                "to_field": field,
            })

    amount = to_number(canonical.get("amount"))
    version_raw = canonical.get("version")
    try:
        version = int(version_raw) if version_raw not in (None, "") else 1
    except (TypeError, ValueError):
        version = 1

    def _clean_str(v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    normalized = {
        "id": _clean_str(canonical.get("id")) or raw.get("id"),
        "owner": _clean_str(canonical.get("owner")),
        "deadline": _clean_str(canonical.get("deadline")),
        "category": (_clean_str(canonical.get("category")) or "").upper() or None,
        "amount": amount,
        "notes": _clean_str(canonical.get("notes")),
        "version": version,
        "source_format": raw["source_format"],
        "source_file": raw["source_file"],
        "source_version_hash": raw.get("source_version_hash"),
        "intake_order": raw["intake_order"],
        "schema_drift_events": drift_events,
        "raw_fields": raw_fields,
    }
    return normalized


def normalize_all(raw_records: list[dict[str, Any]], schema_dir: Path) -> list[dict[str, Any]]:
    alias_map = _load_alias_map(schema_dir)
    return [normalize_record(r, alias_map) for r in raw_records]
