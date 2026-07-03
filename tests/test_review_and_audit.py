from __future__ import annotations

import pytest

from tinycedx.delivery.audit import AuditLog, verify_chain
from tinycedx.review.amendment import amendment_applies, compute_amendment
from tinycedx.review.operator_actions import DeliveryRefused, approve, deliver, reject
from tinycedx.review.state_machine import ApprovalStateMachine, InvalidTransition

AMENDMENT = {"role": "finance_controller", "threshold": 42000}


def _in_review(rid: str = "R") -> ApprovalStateMachine:
    m = ApprovalStateMachine(rid)
    m.transition("draft", actor="t", ts="t0")
    m.transition("in_review", actor="t", ts="t1")
    return m


def test_amendment_for_project_case_id():
    assert compute_amendment("CEDX-82C0A1") == AMENDMENT
    assert amendment_applies(42000, 42000) and not amendment_applies(41999.99, 42000)
    assert not amendment_applies(None, 42000)


def test_illegal_transition_is_refused():
    m = ApprovalStateMachine("R")
    m.transition("draft", actor="t", ts="t0")
    with pytest.raises(InvalidTransition):
        m.transition("approved", actor="t", ts="t1")


def test_blocked_is_terminal():
    m = _in_review()
    reject(m, actor="op")
    with pytest.raises(InvalidTransition):
        approve(m, actor="op")


def test_deliver_refuses_unapproved():
    with pytest.raises(DeliveryRefused):
        deliver(_in_review(), actor="d", amount=100, amendment=AMENDMENT)


def test_deliver_requires_amendment_role_at_threshold():
    m = _in_review()
    approve(m, actor="op")
    with pytest.raises(DeliveryRefused, match="finance_controller"):
        deliver(m, actor="d", amount=42000, amendment=AMENDMENT)
    approve(m, actor="op:fc", role="finance_controller")
    assert deliver(m, actor="d", amount=42000, amendment=AMENDMENT)["state"] == "delivered"


def test_deliver_below_threshold_needs_one_approval():
    m = _in_review()
    approve(m, actor="op")
    assert deliver(m, actor="d", amount=100, amendment=AMENDMENT)["state"] == "delivered"


def test_audit_chain_detects_edit_and_deletion():
    log = AuditLog()
    for i in range(3):
        log.append(actor="p", action=f"e{i}", ts=f"t{i}")
    events = log.events()
    assert verify_chain(events) == (True, None)

    edited = log.events()
    edited[1]["action"] = "rewritten"
    assert verify_chain(edited)[0] is False
    assert verify_chain(events[:1] + events[2:])[0] is False


def test_audit_log_hands_out_copies():
    log = AuditLog()
    log.append(actor="p", action="a")
    log.events()[0]["action"] = "changed"
    assert log.events()[0]["action"] == "a"
    assert not any(hasattr(log, m) for m in ("update", "delete", "remove", "pop", "clear"))
