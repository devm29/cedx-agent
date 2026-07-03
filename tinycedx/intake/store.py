import hashlib
import json
from pathlib import Path
from typing import Any

from tinycedx.intake.parse_eml import parse_eml
from tinycedx.intake.parse_feed import parse_feed
from tinycedx.intake.parse_pdf import parse_pdf


def _sha256_of_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def collect_raw_records(seed_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    feed_path = seed_dir / "feed.json"
    for rec in parse_feed(feed_path):
        rec["source_version_hash"] = _sha256_of_file(feed_path) if feed_path.exists() else None
        records.append(rec)

    inbox_dir = seed_dir / "inbox"
    if inbox_dir.exists():
        for path in sorted(inbox_dir.iterdir()):
            if path.suffix.lower() == ".eml":
                rec = parse_eml(path)
            elif path.suffix.lower() == ".pdf":
                rec = parse_pdf(path)
            else:
                continue
            if rec is None:
                continue
            rec["source_version_hash"] = _sha256_of_file(path)
            records.append(rec)

    for i, rec in enumerate(records):
        rec["intake_order"] = i

    return records


def persist(records: list[dict[str, Any]], state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "intake.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    return out_path


def load_intake(state_dir: Path) -> list[dict[str, Any]]:
    path = state_dir / "intake.jsonl"
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
