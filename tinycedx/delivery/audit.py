from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from tinycedx.hashutil import sha

GENESIS_HASH = "sha256:" + "0" * 64


class AuditLog:
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._prev_hash = GENESIS_HASH

    def append(self, *, actor: str, action: str, record_id: str | None = None,
               ts: str | None = None) -> dict[str, Any]:
        seq = len(self._events)
        ts = ts or datetime.now(UTC).isoformat()
        body = {"seq": seq, "ts": ts, "actor": actor, "action": action, "record_id": record_id}
        h = sha({"prev_hash": self._prev_hash, "event": body})
        entry = {**body, "prev_hash": self._prev_hash, "hash": h}
        self._events.append(entry)
        self._prev_hash = h
        return json.loads(json.dumps(entry))

    def events(self) -> list[dict[str, Any]]:
        return json.loads(json.dumps(self._events))


def verify_chain(events: list[dict[str, Any]]) -> tuple[bool, str | None]:
    prev = GENESIS_HASH
    for e in events:
        body = {"seq": e.get("seq"), "ts": e.get("ts"), "actor": e.get("actor"),
                 "action": e.get("action"), "record_id": e.get("record_id")}
        expected = sha({"prev_hash": prev, "event": body})
        if e.get("prev_hash") != prev:
            return False, f"seq {e.get('seq')}: prev_hash does not match the chain"
        if e.get("hash") != expected:
            return False, f"seq {e.get('seq')}: hash does not match recomputed value (event content was altered)"
        prev = e["hash"]
    return True, None


def build_audit(*, case_id: str, pipeline_version: str, seed_dir: str, pipeline_now: str,
                 amendment: dict[str, Any], agents: list[dict[str, Any]], cost: dict[str, Any],
                 output_package_hash: str, records: list[dict[str, Any]],
                 events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "pipeline_version": pipeline_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "seed_dir": seed_dir,
        "pipeline_now": pipeline_now,
        "amendment": amendment,
        "agents": agents,
        "cost": cost,
        "output_package_hash": output_package_hash,
        "records": records,
        "events": events,
    }
