from __future__ import annotations

import copy
import json
import subprocess
import sys

from tinycedx import config
from tinycedx.delivery.audit import AuditLog, verify_chain


def main() -> int:
    failures: list[str] = []

    log = AuditLog()
    log.append(actor="pipeline", action="demo_event_1")
    log.append(actor="pipeline", action="demo_event_2", record_id="REC-001")
    forbidden_methods = [m for m in ("update", "delete", "remove", "edit", "mutate", "set", "pop", "clear")
                          if hasattr(log, m)]
    if forbidden_methods:
        failures.append(f"AuditLog exposes mutation method(s) that should not exist: {forbidden_methods}")
    else:
        print("  AuditLog exposes no update/delete/mutate API (code-level guarantee holds)")

    audit_path = config.OUT_DIR / "audit.json"
    if not audit_path.exists():
        print("  out/audit.json not found -- running `make demo` first")
        subprocess.run([sys.executable, "-m", "tinycedx.pipeline.run"], check=True)

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    events = audit["events"]
    if len(events) < 2:
        failures.append("audit.json has too few events to exercise a tamper test")
    else:
        ok_before, err_before = verify_chain(events)
        if not ok_before:
            failures.append(f"the untampered chain failed to verify on its own: {err_before}")
        else:
            print("  untampered chain verifies cleanly")

        tampered = copy.deepcopy(events)
        tampered[0]["actor"] = "attacker-edited-this-past-entry"
        ok_after, err_after = verify_chain(tampered)
        if ok_after:
            failures.append("a hand-edited past audit entry was NOT detected by the hash chain (should have been refused)")
        else:
            print(f"  tampered entry correctly detected and refused: {err_after}")

        deleted = events[1:]
        ok_del, err_del = verify_chain(deleted)
        if ok_del:
            failures.append("deleting a past audit entry was NOT detected by the hash chain (should have been refused)")
        else:
            print(f"  deleted entry correctly detected and refused: {err_del}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1

    print("PASS: no mutation API exists, and hand-edited/deleted past audit entries are detected and refused")
    return 0


if __name__ == "__main__":
    sys.exit(main())
