from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tinycedx.agents.contracts import OPERATOR_ACTION, validate
from tinycedx.review.amendment import amendment_applies
from tinycedx.review.state_machine import ApprovalStateMachine


class DeliveryRefused(Exception):
    pass


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _do(machine: ApprovalStateMachine, *, action: str, to_state: str, actor: str,
        role: str | None = None, reason: str | None = None, edits: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"record_id": machine.record_id, "action": action, "actor": actor,
               "role": role, "note": reason, "edits": edits}
    validate(payload, OPERATOR_ACTION, label="OperatorAction")
    return machine.transition(to_state, actor=actor, ts=now_iso(), reason=reason, role=role)


def approve(machine: ApprovalStateMachine, *, actor: str, role: str | None = None,
            reason: str | None = None) -> dict[str, Any]:
    return _do(machine, action="approve", to_state="approved", actor=actor, role=role, reason=reason)


def reject(machine: ApprovalStateMachine, *, actor: str, reason: str | None = None) -> dict[str, Any]:
    return _do(machine, action="reject", to_state="blocked", actor=actor, reason=reason)


def request_changes(machine: ApprovalStateMachine, *, actor: str, reason: str | None = None) -> dict[str, Any]:
    return _do(machine, action="request_changes", to_state="changes_requested", actor=actor, reason=reason)


def edit_resolve(machine: ApprovalStateMachine, *, actor: str, edits: dict[str, Any],
                  reason: str | None = None) -> dict[str, Any]:
    return _do(machine, action="edit_resolve", to_state="in_review", actor=actor, reason=reason, edits=edits)


def deliver(machine: ApprovalStateMachine, *, actor: str, amount: float | None,
            amendment: dict[str, Any]) -> dict[str, Any]:
    if machine.state != "approved":
        raise DeliveryRefused(
            f"{machine.record_id}: cannot deliver from state {machine.state!r} (must be 'approved')"
        )
    if amendment_applies(amount, amendment["threshold"]):
        role_approvals = [e for e in machine.trail if e["state"] == "approved" and e.get("role") == amendment["role"]]
        if not role_approvals:
            raise DeliveryRefused(
                f"{machine.record_id}: amount {amount} >= amendment threshold {amendment['threshold']} "
                f"requires a recorded approval by role={amendment['role']!r}, none found"
            )
    return machine.transition("delivered", actor=actor, ts=now_iso())
