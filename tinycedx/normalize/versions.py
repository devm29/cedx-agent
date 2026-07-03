from __future__ import annotations

from typing import Any


def resolve_versions(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_id.setdefault(rec["id"], []).append(rec)

    kept: list[dict[str, Any]] = []
    superseded: list[dict[str, Any]] = []

    for rid, group in by_id.items():
        if len(group) == 1:
            group[0]["superseded_version_event"] = None
            kept.append(group[0])
            continue

        ordered = sorted(group, key=lambda r: (r.get("version", 1), r["intake_order"]))
        winner = ordered[-1]
        losers = ordered[:-1]

        winner["superseded_version_event"] = {
            "record_id": rid,
            "kept_version": winner.get("version"),
            "kept_source_file": winner.get("source_file"),
            "superseded_versions": [
                {"version": loser.get("version"), "source_file": loser.get("source_file")}
                for loser in losers
            ],
        }
        kept.append(winner)

        for loser in losers:
            loser["status"] = "superseded"
            loser["superseded_by"] = {
                "version": winner.get("version"),
                "source_file": winner.get("source_file"),
            }
            superseded.append(loser)

    kept.sort(key=lambda r: r["intake_order"])
    return kept, superseded
