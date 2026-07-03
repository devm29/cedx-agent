from __future__ import annotations

from typing import Any


def find_record(audit: dict[str, Any], record_id: str, version: int | None = None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return (chosen record, other versions) for an id.

    One id can appear several times when a later version supersedes an earlier one. Without
    an explicit version the live (non-superseded) entry is the one worth tracing.
    """
    matches = [r for r in audit["records"] if r["id"] == record_id]
    if version is not None:
        chosen = next((r for r in matches if r.get("version") == version), None)
    else:
        live = [r for r in matches if r["status"] != "superseded"]
        chosen = (live or matches or [None])[0]
    return chosen, [r for r in matches if r is not chosen]


def describe_other_versions(others: list[dict[str, Any]]) -> str | None:
    if not others:
        return None
    listed = ", ".join(f"v{r.get('version')} ({r['status']})" for r in others)
    return f"  other version(s) of this id: {listed} -- pass --version to inspect one"
