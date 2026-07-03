from __future__ import annotations

from typing import Any

ALLOWED: dict[str, set[str]] = {
    "draft": {"in_review"},
    "in_review": {"approved", "changes_requested", "blocked"},
    "changes_requested": {"in_review", "blocked"},
    "approved": {"approved", "delivered", "blocked"},
    "delivered": set(),
    "blocked": set(),
}


class InvalidTransition(Exception):
    pass


class ApprovalStateMachine:
    def __init__(self, record_id: str):
        self.record_id = record_id
        self.state: str | None = None
        self.trail: list[dict[str, Any]] = []

    def transition(self, to_state: str, *, actor: str, ts: str,
                    reason: str | None = None, role: str | None = None) -> dict[str, Any]:
        if to_state not in ALLOWED:
            raise InvalidTransition(f"{self.record_id}: unknown state {to_state!r}")
        if self.state is not None and to_state not in ALLOWED[self.state]:
            raise InvalidTransition(f"{self.record_id}: illegal transition {self.state!r} -> {to_state!r}")
        self.state = to_state
        entry = {"state": to_state, "actor": actor, "ts": ts, "reason": reason, "role": role}
        self.trail.append(entry)
        return entry
