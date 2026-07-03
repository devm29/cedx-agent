from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from tinycedx.agents.orchestrator import process_record
from tinycedx.detectors.registry import classify_batch
from tinycedx.eval import scenarios
from tinycedx.eval.judge import judge_case
from tinycedx.normalize.normalize import _load_alias_map, normalize_record
from tinycedx.normalize.versions import resolve_versions
from tinycedx.review.amendment import compute_amendment
from tinycedx.review.operator_actions import DeliveryRefused, deliver, now_iso
from tinycedx.review.state_machine import ApprovalStateMachine

GOLDEN_PATH = Path(__file__).parent / "golden_cases.json"
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
PIPELINE_NOW = date(2026, 6, 26)

SCENARIO_WORKERS = {
    "clean": scenarios.clean_worker,
    "abstain": scenarios.abstain_worker,
    "hallucination": scenarios.hallucinating_worker,
    "malformed": scenarios.malformed_worker,
    "flapping": None,
    "priced_downgrade": scenarios.priced_worker,
}


def _run_detector_case(case: dict[str, Any]) -> tuple[str | None, str | None]:
    rec = dict(case["record"])
    filler = [{"id": f"FILLER-{i}", "amount": a} for i, a in enumerate(case["batch"])]
    verdicts = classify_batch([rec] + filler, PIPELINE_NOW)
    v = verdicts[rec["id"]]
    return v["reason_code"], case["expected_reason_code"]


def _run_normalize_case(case: dict[str, Any]) -> tuple[str | None, str | None]:
    alias_map = _load_alias_map(SCHEMA_DIR)
    raw = {"id": case["raw_fields"].get("Id"), "source_format": "eml", "source_file": "golden.eml",
           "source_version_hash": None, "intake_order": 0, "raw_fields": case["raw_fields"]}
    normalized = normalize_record(raw, alias_map)
    drift = normalized["schema_drift_events"]
    actual = "SCHEMA_DRIFT" if drift and drift[0]["to_field"] == case.get("expected_field_mapped") else (
        "SCHEMA_DRIFT" if drift else None
    )
    return actual, case["expected_reason_code"]


def _run_versions_case(case: dict[str, Any]) -> tuple[str | None, str | None]:
    group = [dict(g) for g in case["group"]]
    for g in group:
        g.setdefault("source_format", "feed")
        g.setdefault("source_file", "golden.json")
    kept, superseded = resolve_versions(group)
    actual = "SUPERSEDED_VERSION" if superseded else None
    kept_version_ok = kept[0]["version"] == case["expected_kept_version"] if kept else False
    return (actual if kept_version_ok else None), case["expected_reason_code"]


def _run_orchestrator_scenario_case(case: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    """Returns (actual_status_or_code, expected_status_or_code, actual_tier, expected_tier)."""
    rec = dict(case["record"])
    scenario = case["scenario"]

    if scenario == "flapping":
        worker_fn = scenarios.make_flapping_worker()
        result = process_record(record=rec, low_confidence_flag=False, max_steps=4, worker_fn=worker_fn)
        return result["reason_code"], case.get("expected_reason_code"), None, None

    if scenario == "priced_downgrade":
        amendment = compute_amendment("CEDX-XXXX")
        strong_est = 0.0015
        result = process_record(record=rec, low_confidence_flag=True, amendment_threshold=10 ** 9,
                                 max_cost_usd=strong_est * 0.6, worker_fn=scenarios.priced_worker)
        return result.get("model_tier"), None, result.get("model_tier"), case.get("expected_model_tier")

    worker_fn = SCENARIO_WORKERS[scenario]
    result = process_record(record=rec, low_confidence_flag=(scenario == "abstain"), worker_fn=worker_fn)
    if "expected_status" in case:
        return result["status"], case["expected_status"], None, None
    return result["reason_code"], case.get("expected_reason_code"), None, None


def _run_review_scenario_case(case: dict[str, Any]) -> tuple[bool, bool]:
    amendment = compute_amendment("CEDX-XXXX")
    m = ApprovalStateMachine("GC-014")
    m.transition("draft", actor="pipeline", ts=now_iso())
    m.transition("in_review", actor="pipeline", ts=now_iso())
    refused = False
    try:
        deliver(m, actor="delivery-service", amount=case["amount"], amendment=amendment)
    except DeliveryRefused:
        refused = True
    return refused, case["expected_refused"]


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    kind = case["kind"]
    if kind == "detector":
        actual, expected = _run_detector_case(case)
        correct = actual == expected
    elif kind == "normalize":
        actual, expected = _run_normalize_case(case)
        correct = actual == expected
    elif kind == "versions":
        actual, expected = _run_versions_case(case)
        correct = actual == expected
    elif kind == "orchestrator_scenario":
        actual, expected, actual_tier, expected_tier = _run_orchestrator_scenario_case(case)
        correct = (actual == expected) if expected is not None else (actual_tier == expected_tier)
    elif kind == "review_scenario":
        actual, expected = _run_review_scenario_case(case)
        correct = actual == expected
    else:
        raise ValueError(f"unknown golden case kind: {kind!r}")

    return {"case_id": case["case_id"], "agent": case["agent"], "kind": kind,
            "actual": actual, "expected": expected, "correct": correct}


def main() -> int:
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    print(f"running {len(cases)} golden case(s) ...\n")

    results = []
    for case in cases:
        r = run_case(case)
        j = judge_case(case_id=case["case_id"], agent=case["agent"], context={
            "kind": case["kind"], "actual": str(r["actual"]), "expected": str(r["expected"]),
            "correct": r["correct"],
        })
        r["judge_score"] = j["score"]
        r["judge_rationale"] = j["rationale"]
        results.append(r)
        mark = "PASS" if r["correct"] else "FAIL"
        print(f"  [{mark}] {case['case_id']:<38} agent={r['agent']:<12} "
              f"actual={str(r['actual']):<18} expected={str(r['expected']):<18} "
              f"judge={r['judge_score']:.2f}")

    per_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        per_agent[r["agent"]].append(r)

    print("\nper-agent scores:")
    print(f"  {'agent':<14} {'cases':>6} {'accuracy':>10} {'avg_judge_score':>16}")
    overall_correct = 0
    for agent in sorted(per_agent):
        rs = per_agent[agent]
        acc = sum(1 for r in rs if r["correct"]) / len(rs)
        avg_judge = sum(r["judge_score"] for r in rs) / len(rs)
        overall_correct += sum(1 for r in rs if r["correct"])
        print(f"  {agent:<14} {len(rs):>6} {acc:>9.0%} {avg_judge:>16.2f}")

    total = len(results)
    print(f"\noverall: {overall_correct}/{total} golden cases correct "
          f"({overall_correct/total:.0%})")

    failed = [r for r in results if not r["correct"]]
    if failed:
        print(f"\nFAIL: {len(failed)} golden case(s) did not match expected behavior: "
              f"{[r['case_id'] for r in failed]}")
        return 1

    print("PASS: all golden cases matched expected behavior")
    return 0


if __name__ == "__main__":
    sys.exit(main())
