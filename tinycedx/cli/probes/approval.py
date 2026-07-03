from __future__ import annotations

import sys

from tinycedx import config
from tinycedx.delivery.audit import AuditLog
from tinycedx.review.amendment import compute_amendment
from tinycedx.review.operator_actions import DeliveryRefused, approve, deliver, now_iso
from tinycedx.review.state_machine import ApprovalStateMachine


def main() -> int:
    amendment = compute_amendment(config.CASE_ID)
    audit_log = AuditLog()
    failures: list[str] = []

    m1 = ApprovalStateMachine("PROBE-NEVER-APPROVED")
    m1.transition("draft", actor="pipeline", ts=now_iso())
    m1.transition("in_review", actor="pipeline", ts=now_iso())
    try:
        deliver(m1, actor="delivery-service", amount=1000, amendment=amendment)
        failures.append("a never-approved record was DELIVERED (should have been refused)")
    except DeliveryRefused as e:
        audit_log.append(actor="delivery-service", action="delivery_refused", record_id=m1.record_id)
        print(f"  refused (as expected): {e}")

    high_amount = amendment["threshold"] + 1000
    m2 = ApprovalStateMachine("PROBE-MISSING-AMENDMENT-APPROVAL")
    m2.transition("draft", actor="pipeline", ts=now_iso())
    m2.transition("in_review", actor="pipeline", ts=now_iso())
    approve(m2, actor="operator:auto-policy")
    try:
        deliver(m2, actor="delivery-service", amount=high_amount, amendment=amendment)
        failures.append("a high-value record missing its amendment-role approval was DELIVERED (should have been refused)")
    except DeliveryRefused as e:
        audit_log.append(actor="delivery-service", action="delivery_refused", record_id=m2.record_id)
        print(f"  refused (as expected): {e}")

    m3 = ApprovalStateMachine("PROBE-FULLY-APPROVED")
    m3.transition("draft", actor="pipeline", ts=now_iso())
    m3.transition("in_review", actor="pipeline", ts=now_iso())
    approve(m3, actor="operator:auto-policy")
    approve(m3, actor=f"operator:{amendment['role']}", role=amendment["role"])
    try:
        entry = deliver(m3, actor="delivery-service", amount=high_amount, amendment=amendment)
        audit_log.append(actor="delivery-service", action="delivered", record_id=m3.record_id)
        print(f"  delivered (as expected): {entry['state']}")
    except DeliveryRefused as e:
        failures.append(f"a fully-approved record (incl. amendment role) was refused unexpectedly: {e}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1

    print(f"PASS: non-approved delivery refused + logged (amendment role={amendment['role']} "
          f"threshold={amendment['threshold']}); fully-approved delivery succeeds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
