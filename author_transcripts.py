from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from tinycedx.detectors.registry import classify_batch
from tinycedx.hashutil import sha, sha_hex
from tinycedx.intake.store import collect_raw_records
from tinycedx.normalize.normalize import normalize_all
from tinycedx.normalize.versions import resolve_versions

REPO_ROOT = Path(__file__).resolve().parent
TRANSCRIPTS_DIR = REPO_ROOT / "transcripts"
WORKER_PROMPT_VERSION = "worker-v1"

CATEGORY_LABEL = {
    "ONBOARDING": "new-matter onboarding",
    "RENEWAL": "engagement letter renewal",
    "REVIEW": "matter review",
    "REPORT": "billing status report",
    "INTAKE": "new matter intake",
}


def delivered_fields_for(rec: dict) -> dict:
    label = CATEGORY_LABEL.get(rec["category"], (rec["category"] or "matter").lower())
    summary = (
        f"Routine {label} for {rec['owner']}; matter value ${rec['amount']:,.0f}, "
        f"target date {rec['deadline']}."
    )
    return {
        "matter_id": rec["id"],
        "responsible_attorney": rec["owner"],
        "deadline": rec["deadline"],
        "matter_type": rec["category"],
        "matter_value": rec["amount"],
        "summary": summary,
    }


def write_transcript(*, agent: str, record_id: str, attempt: int, model: str,
                      prompt_version: str, request: dict, response: dict,
                      tokens_in: int, tokens_out: int, cost_usd: float, latency_ms: float,
                      index: dict) -> None:
    response_hash_hex = sha_hex(response)
    delivered_fields = response.get("delivered_fields")
    transcript = {
        "agent": agent,
        "record_id": record_id,
        "attempt": attempt,
        "model": model,
        "prompt_version": prompt_version,
        "request": request,
        "response": response,
        "response_hash": f"sha256:{response_hash_hex}",
        "delivered_fields_hash": sha(delivered_fields) if delivered_fields is not None else None,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
    }
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPTS_DIR / f"{response_hash_hex}.json"
    path.write_text(json.dumps(transcript, indent=2, sort_keys=True), encoding="utf-8")
    index[f"{record_id}:{agent}:{attempt}"] = path.name
    print(f"wrote {path.name}  <- {record_id}:{agent}:{attempt}")


def cost(tier: str, tokens_in: int, tokens_out: int) -> float:
    pricing = {"cheap": {"in": 0.00015, "out": 0.00060}, "strong": {"in": 0.00250, "out": 0.01000}}[tier]
    return round((tokens_in / 1000) * pricing["in"] + (tokens_out / 1000) * pricing["out"], 8)


def main() -> None:
    raw = collect_raw_records(REPO_ROOT / "seed")
    normalized = normalize_all(raw, REPO_ROOT / "tinycedx" / "schema")
    kept, _superseded = resolve_versions(normalized)
    verdicts = classify_batch(kept, date(2026, 6, 26))
    by_id = {r["id"]: r for r in kept}

    index: dict[str, str] = {}

    reaches_assembly = [r for r in kept if verdicts[r["id"]]["reason_code"] is None]
    low_conf_ids = {r["id"] for r in reaches_assembly if verdicts[r["id"]]["low_confidence_flag"]}

    for rec in reaches_assembly:
        if rec["id"] in low_conf_ids or rec["id"] == "REC-018":
            continue
        tokens_in, tokens_out = 180, 90
        write_transcript(
            agent="worker", record_id=rec["id"], attempt=1, model="gpt-4o-mini",
            prompt_version=WORKER_PROMPT_VERSION,
            request={"instruction": "Draft the branded matter package from the normalized record.",
                      "record": {k: rec[k] for k in ("id", "owner", "deadline", "category", "amount", "notes")}},
            response={
                "record_id": rec["id"],
                "delivered_fields": delivered_fields_for(rec),
                "confidence": 0.93,
                "abstain": False,
                "abstain_reason": None,
            },
            tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost("cheap", tokens_in, tokens_out),
            latency_ms=420.0, index=index,
        )

    abstain_reasons = {
        "REC-015": "category says INTAKE but the notes describe both a renewal and a report with "
                    "inconsistent figures -- cannot determine the correct matter_type/matter_value.",
        "REC-021": "category is unspecified ('?') and the amount is referenced from a side letter that "
                    "was not attached -- no reliable basis to state matter_type or matter_value.",
    }
    for rid, reason in abstain_reasons.items():
        rec = by_id[rid]
        tokens_in, tokens_out = 210, 60
        write_transcript(
            agent="worker", record_id=rid, attempt=1, model="gpt-4o",
            prompt_version=WORKER_PROMPT_VERSION,
            request={"instruction": "Draft the branded matter package from the normalized record.",
                      "record": {k: rec[k] for k in ("id", "owner", "deadline", "category", "amount", "notes")}},
            response={
                "record_id": rid,
                "delivered_fields": None,
                "confidence": 0.32,
                "abstain": True,
                "abstain_reason": reason,
            },
            tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost("strong", tokens_in, tokens_out),
            latency_ms=610.0, index=index,
        )

    rec18 = by_id["REC-018"]
    write_transcript(
        agent="worker", record_id="REC-018", attempt=1, model="gpt-4o-mini",
        prompt_version=WORKER_PROMPT_VERSION,
        request={"instruction": "Draft the branded matter package from the normalized record.",
                  "record": {k: rec18[k] for k in ("id", "owner", "deadline", "category", "amount", "notes")}},
        response={
            "record_id": "REC-018",
            "delivered_fields": {
                "matter_id": "REC-018",
                "responsible_attorney": rec18["owner"],
                "deadline": rec18["deadline"],
                "matter_type": rec18["category"],
                "matter_value": 9999,
                "summary": f"Routine matter review for {rec18['owner']}; matter value $9,999.",
                "risk_rating": "high",
            },
            "confidence": 0.88,
            "abstain": False,
            "abstain_reason": None,
        },
        tokens_in=190, tokens_out=95, cost_usd=cost("cheap", 190, 95), latency_ms=455.0, index=index,
    )
    write_transcript(
        agent="worker", record_id="REC-018", attempt=2, model="gpt-4o",
        prompt_version=WORKER_PROMPT_VERSION,
        request={"instruction": "Retry: the previous draft's matter_value did not match the source record.",
                  "record": {k: rec18[k] for k in ("id", "owner", "deadline", "category", "amount", "notes")}},
        response={
            "record_id": "REC-018",
            "delivered_fields": {
                "matter_id": "REC-018",
                "responsible_attorney": rec18["owner"],
                "deadline": rec18["deadline"],
                "matter_type": rec18["category"],
                "matter_value": rec18["amount"],
                "summary": f"Routine matter review for {rec18['owner']}; matter value ${rec18['amount']:,.0f}.",
                "risk_rating": "high",
            },
            "confidence": 0.85,
            "abstain": False,
            "abstain_reason": None,
        },
        tokens_in=205, tokens_out=98, cost_usd=cost("strong", 205, 98), latency_ms=530.0, index=index,
    )

    idx_path = TRANSCRIPTS_DIR / "index.json"
    idx_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\n{len(index)} transcripts indexed -> {idx_path}")


if __name__ == "__main__":
    main()
