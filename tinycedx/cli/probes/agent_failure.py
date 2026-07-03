from __future__ import annotations

import sys

from tinycedx.agents.orchestrator import process_record
from tinycedx.eval.scenarios import hallucinating_worker as _hallucinating_worker
from tinycedx.eval.scenarios import make_flapping_worker as _flapping_worker
from tinycedx.eval.scenarios import malformed_worker as _malformed_worker


def _never_delivered(result: dict) -> bool:
    return result["status"] == "exception" and not any(
        s["agent"] == "verifier" and s["status"] == "ok" for s in result["agent_trace"]
    )


def main() -> int:
    base = {"id": "PROBE", "owner": "z.probe", "deadline": "2026-09-01", "category": "REVIEW",
            "amount": 5000.0, "notes": "synthetic probe record"}
    failures: list[str] = []

    r1 = {**base, "id": "PROBE-HALLUCINATION"}
    res1 = process_record(record=r1, low_confidence_flag=False, worker_fn=_hallucinating_worker)
    print(f"  {r1['id']}: status={res1['status']} reason_code={res1['reason_code']}")
    if not (res1["reason_code"] == "AGENT_HALLUCINATION" and _never_delivered(res1)):
        failures.append(f"hallucinated worker output was not caught as AGENT_HALLUCINATION (got {res1['reason_code']})")

    r2 = {**base, "id": "PROBE-MALFORMED"}
    res2 = process_record(record=r2, low_confidence_flag=False, worker_fn=_malformed_worker)
    print(f"  {r2['id']}: status={res2['status']} reason_code={res2['reason_code']}")
    if not (res2["reason_code"] == "AGENT_MALFORMED" and _never_delivered(res2)):
        failures.append(f"malformed worker output was not caught as AGENT_MALFORMED (got {res2['reason_code']})")

    r3 = {**base, "id": "PROBE-LOOP"}
    res3 = process_record(record=r3, low_confidence_flag=False, max_steps=4, worker_fn=_flapping_worker())
    print(f"  {r3['id']}: status={res3['status']} reason_code={res3['reason_code']} "
          f"spans={len(res3['agent_trace'])}")
    killed = any(s["status"] == "killed" for s in res3["agent_trace"])
    if not (res3["reason_code"] == "AGENT_LOOP" and killed and _never_delivered(res3)):
        failures.append(f"a worker that never converges was not caught as AGENT_LOOP (got {res3['reason_code']})")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1

    print("PASS: hallucinated, malformed, and non-converging worker output are all caught by the "
          "Verifier/Orchestrator and never delivered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
