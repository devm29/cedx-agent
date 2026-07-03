from __future__ import annotations

import sys

from tinycedx import config
from tinycedx.agents.orchestrator import process_record
from tinycedx.eval.scenarios import priced_worker as _priced_worker


def main() -> int:
    base = {"owner": "z.probe", "deadline": "2026-09-01", "category": "REVIEW",
            "amount": 4000.0, "notes": "synthetic probe record"}
    failures: list[str] = []

    r_a = {**base, "id": "PROBE-BUDGET-DOWNGRADE"}
    strong_est = config.estimate_cost("strong")
    cheap_est = config.estimate_cost("cheap")
    ceiling_a = (strong_est + cheap_est) / 2
    res_a = process_record(record=r_a, low_confidence_flag=True, amendment_threshold=10**9,
                            max_cost_usd=ceiling_a, worker_fn=_priced_worker)
    print(f"  {r_a['id']}: status={res_a['status']} model_tier={res_a.get('model_tier')} "
          f"ceiling=${ceiling_a:.6f}")
    if not (res_a["status"] == "assembled" and res_a.get("model_tier") == "cheap"):
        failures.append("Router/Orchestrator did not downgrade to the cheap tier when strong couldn't fit the ceiling")

    r_b = {**base, "id": "PROBE-BUDGET-EXCEEDED"}
    ceiling_b = cheap_est / 10
    res_b = process_record(record=r_b, low_confidence_flag=False, amendment_threshold=10**9,
                            max_cost_usd=ceiling_b, worker_fn=_priced_worker)
    print(f"  {r_b['id']}: status={res_b['status']} reason_code={res_b['reason_code']} "
          f"ceiling=${ceiling_b:.6f}")
    if not (res_b["status"] == "exception" and res_b["reason_code"] == "BUDGET_EXCEEDED"):
        failures.append(f"a record exceeding even the cheap-tier ceiling did not raise BUDGET_EXCEEDED (got {res_b['reason_code']})")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1

    print("PASS: over-ceiling record is downgraded to the cheap tier when that fits, and raises "
          "BUDGET_EXCEEDED (routed, never delivered) when even the cheap tier can't fit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
