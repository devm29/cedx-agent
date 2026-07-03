from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from tinycedx import config
from tinycedx.agents.base import make_span
from tinycedx.agents.operator import OPERATOR_AGENT
from tinycedx.agents.orchestrator import ORCHESTRATOR_AGENT, process_record
from tinycedx.agents.router import ROUTER_AGENT
from tinycedx.agents.verifier import VERIFIER_AGENT
from tinycedx.agents.worker import WORKER_AGENT
from tinycedx.budget.summary import summarize_cost
from tinycedx.delivery.audit import AuditLog, build_audit
from tinycedx.delivery.exceptions_queue import build_exception_queue
from tinycedx.delivery.package import build_package
from tinycedx.detectors.registry import classify_batch
from tinycedx.hashutil import sha
from tinycedx.intake.store import collect_raw_records, persist
from tinycedx.normalize.normalize import normalize_all
from tinycedx.normalize.versions import resolve_versions
from tinycedx.pipeline.atomic import atomic_write_text
from tinycedx.review.amendment import amendment_applies, compute_amendment
from tinycedx.review.operator_actions import DeliveryRefused, approve, deliver, now_iso
from tinycedx.review.state_machine import ApprovalStateMachine

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
AGENT_ROSTER = [ORCHESTRATOR_AGENT, ROUTER_AGENT, WORKER_AGENT, VERIFIER_AGENT, OPERATOR_AGENT]


def log(msg: str) -> None:
    print(msg, flush=True)


def _base_record_entry(r: dict, *, status: str, reason_code: str | None, reason_class: str | None,
                        detail: str | None = None, transcript_hash: str | None = None,
                        delivered_fields: dict | None = None, agent_trace: list | None = None,
                        approval_trail: list | None = None) -> dict:
    return {
        "id": r["id"],
        "version": r.get("version"),
        "owner": r.get("owner"),
        "source_format": r["source_format"],
        "source_version_hash": r.get("source_version_hash"),
        "status": status,
        "reason_code": reason_code,
        "reason_class": reason_class,
        "detail": detail,
        "transcript_hash": transcript_hash,
        "delivered_fields": delivered_fields,
        "delivered_fields_hash": sha(delivered_fields) if delivered_fields is not None else None,
        "agent_trace": agent_trace or [],
        "approval_trail": approval_trail or [],
    }


def run() -> int:
    log(f"[tinycedx] pipeline_version={config.PIPELINE_VERSION} seed_dir={config.SEED_DIR} "
        f"replay_llm={config.REPLAY_LLM} case_id={config.CASE_ID}")

    amendment = compute_amendment(config.CASE_ID)
    log(f"AMENDMENT: role={amendment['role']} threshold={amendment['threshold']}")

    pipeline_now = date.fromisoformat(config.PIPELINE_NOW)
    audit_log = AuditLog()

    log("[stage 1/5] Intake: parsing feed.json + inbox/ ...")
    raw = collect_raw_records(config.SEED_DIR)
    persist(raw, config.OUT_DIR / "state")
    audit_log.append(actor="pipeline", action="intake_complete")
    log(f"  parsed {len(raw)} raw record(s) from {config.SEED_DIR}")

    log("[stage 2/5] Orchestration: normalizing + classifying ...")
    normalized = normalize_all(raw, SCHEMA_DIR)
    kept, superseded = resolve_versions(normalized)
    verdicts = classify_batch(kept, pipeline_now)
    audit_log.append(actor="pipeline", action="normalize_complete")

    final_records: list[dict] = []
    delivered_for_package: list[dict] = []

    for r in superseded:
        audit_log.append(actor="pipeline", action="SUPERSEDED_VERSION", record_id=r["id"])
        final_records.append(_base_record_entry(
            r, status="superseded", reason_code="SUPERSEDED_VERSION", reason_class="B",
            detail=f"superseded by version {r['superseded_by']['version']} ({r['superseded_by']['source_file']})",
        ))
        log(f"  {r['id']}: SUPERSEDED (kept version {r['superseded_by']['version']})")

    for r in kept:
        v = verdicts[r["id"]]
        drift = r.get("schema_drift_events") or []
        if drift:
            audit_log.append(actor="pipeline", action="SCHEMA_DRIFT", record_id=r["id"])
        if r.get("superseded_version_event"):
            audit_log.append(actor="pipeline", action="SUPERSEDED_VERSION_WINNER", record_id=r["id"])

        if v["reason_code"] is not None:
            audit_log.append(actor="orchestrator", action=f"EXCEPTION:{v['reason_code']}", record_id=r["id"])
            final_records.append(_base_record_entry(
                r, status="exception", reason_code=v["reason_code"], reason_class=v["reason_class"],
                detail=v["detail"], agent_trace=[make_span(agent="orchestrator", status="routed")],
            ))
            log(f"  {r['id']}: EXCEPTION {v['reason_code']}")
            continue

        result = process_record(record=r, low_confidence_flag=v["low_confidence_flag"],
                                 amendment_threshold=amendment["threshold"])

        if result["status"] == "exception":
            actor = "verifier" if result["reason_code"] in {"AGENT_HALLUCINATION", "AGENT_MALFORMED"} else "orchestrator"
            audit_log.append(actor=actor, action=f"EXCEPTION:{result['reason_code']}", record_id=r["id"])
            final_records.append(_base_record_entry(
                r, status="exception", reason_code=result["reason_code"], reason_class="A",
                detail=result["detail"], agent_trace=result["agent_trace"],
            ))
            log(f"  {r['id']}: EXCEPTION {result['reason_code']}")
            continue

        delivered_fields = result["delivered_fields"]
        machine = ApprovalStateMachine(r["id"])
        machine.transition("draft", actor="pipeline", ts=now_iso())
        machine.transition("in_review", actor="pipeline", ts=now_iso())
        approve(machine, actor="operator:auto-policy", reason="clean record; verifier pass")
        audit_log.append(actor="operator:auto-policy", action="approved", record_id=r["id"])

        if amendment_applies(r["amount"], amendment["threshold"]):
            approve(machine, actor=f"operator:{amendment['role']}", role=amendment["role"],
                    reason="amendment gate satisfied")
            audit_log.append(actor=f"operator:{amendment['role']}", action="approved_amendment", record_id=r["id"])

        try:
            deliver(machine, actor="delivery-service", amount=r["amount"], amendment=amendment)
        except DeliveryRefused as e:
            audit_log.append(actor="delivery-service", action="delivery_refused", record_id=r["id"])
            final_records.append(_base_record_entry(
                r, status="exception", reason_code="UNVERIFIED_ANOMALY", reason_class="A",
                detail=str(e), agent_trace=result["agent_trace"], approval_trail=machine.trail,
            ))
            log(f"  {r['id']}: DELIVERY REFUSED ({e})")
            continue

        audit_log.append(actor="delivery-service", action="delivered", record_id=r["id"])
        reason_code = "SCHEMA_DRIFT" if drift else None
        reason_class = "B" if drift else None
        entry = _base_record_entry(
            r, status="delivered", reason_code=reason_code, reason_class=reason_class,
            detail=f"schema drift: {drift}" if drift else None,
            transcript_hash=result["transcript_hash"], delivered_fields=delivered_fields,
            agent_trace=result["agent_trace"], approval_trail=machine.trail,
        )
        final_records.append(entry)
        delivered_for_package.append(entry)
        log(f"  {r['id']}: DELIVERED")

    log("[stage 5/5] Delivery: building branded package + audit + exception queue ...")
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(UTC).isoformat()
    package, package_hash = build_package(case_id=config.CASE_ID, generated_at=generated_at,
                                           delivered_records=delivered_for_package)
    atomic_write_text(config.OUT_DIR / "branded_package.json", json.dumps(package, indent=2, sort_keys=True))

    exceptions = [r for r in final_records if r["status"] == "exception"]
    exc_queue = build_exception_queue(exceptions)
    atomic_write_text(config.OUT_DIR / "exception_queue.json", json.dumps(exc_queue, indent=2, sort_keys=True))

    cost = summarize_cost(final_records)
    audit = build_audit(
        case_id=config.CASE_ID, pipeline_version=config.PIPELINE_VERSION,
        seed_dir=str(config.SEED_DIR), pipeline_now=config.PIPELINE_NOW,
        amendment=amendment, agents=[a.roster_entry() for a in AGENT_ROSTER],
        cost=cost, output_package_hash=package_hash, records=final_records,
        events=audit_log.events(),
    )
    atomic_write_text(config.OUT_DIR / "audit.json", json.dumps(audit, indent=2, sort_keys=True))

    log(f"\ndone: {len(final_records)} records "
        f"({len(delivered_for_package)} delivered, {len(exceptions)} exceptions, "
        f"{len(superseded)} superseded)")
    log(f"cost: total=${cost['total_usd']:.6f} avg/record=${cost['avg_usd_per_record']:.6f} "
        f"p95_latency={cost['p95_latency_ms']:.1f}ms projected@10k/day=${cost['projected_usd_per_10k']:.2f}")
    log(f"wrote {config.OUT_DIR / 'branded_package.json'}")
    log(f"wrote {config.OUT_DIR / 'audit.json'}")
    log(f"wrote {config.OUT_DIR / 'exception_queue.json'}")
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
