import json
from pathlib import Path
from typing import Any


def parse_feed(feed_path: Path) -> list[dict[str, Any]]:
    if not feed_path.exists():
        return []
    data = json.loads(feed_path.read_text(encoding="utf-8"))
    records = []
    for obj in data:
        records.append({
            "id": str(obj.get("id") or "").strip() or None,
            "source_format": "feed",
            "source_file": feed_path.name,
            "raw_fields": dict(obj),
        })
    return records
