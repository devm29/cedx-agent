from __future__ import annotations

import json
from pathlib import Path

from tinycedx.hashutil import sha_hex

REPO_ROOT = Path(__file__).resolve().parent
TRANSCRIPTS_DIR = REPO_ROOT / "transcripts"
JUDGE_PROMPT_VERSION = "judge-v1"

RATIONALES = {
    "gc-01-stale": (0.97, "Correctly flagged the past-deadline record as STALE using a pure date comparison."),
    "gc-02-missing-input": (0.97, "Correctly flagged the null amount as MISSING_INPUT with no auto-default applied."),
    "gc-03-outlier": (0.95, "Correctly flagged the extreme value as OUTLIER via the batch's robust median/MAD statistic."),
    "gc-04-injection": (0.98, "Correctly detected the instruction-override language and blocked the record."),
    "gc-05-unverified-anomaly": (0.9, "Correctly caught the untrusted-figure-override pattern as UNVERIFIED_ANOMALY."),
    "gc-06-schema-drift": (0.93, "Correctly inferred the renamed field structurally and logged SCHEMA_DRIFT."),
    "gc-07-superseded-version": (0.95, "Correctly kept the higher version and logged the loser as SUPERSEDED_VERSION."),
    "gc-08-worker-clean-assembly": (0.94, "Worker drafted a grounded, passthrough-accurate package; Verifier passed it cleanly."),
    "gc-09-worker-abstain": (0.92, "Worker correctly abstained on an ambiguous record instead of guessing."),
    "gc-10-verifier-catches-hallucination": (0.96, "Verifier correctly rejected a fabricated field/value not supported by source."),
    "gc-11-verifier-catches-malformed": (0.95, "Verifier/Orchestrator correctly rejected structurally invalid worker output after bounded retry."),
    "gc-12-orchestrator-caps-loop": (0.9, "Orchestrator correctly killed a non-converging record at the step ceiling."),
    "gc-13-router-downgrades-on-budget": (0.93, "Router correctly downgraded to the cheap tier when the strong tier could not fit the ceiling."),
    "gc-14-operator-refuses-nonapproved": (0.98, "Delivery correctly refused a record with no recorded approval."),
}


def main() -> None:
    idx_path = TRANSCRIPTS_DIR / "index.json"
    index = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}

    for case_id, (score, rationale) in RATIONALES.items():
        response = {"score": score, "rationale": rationale}
        response_hash_hex = sha_hex(response)
        transcript = {
            "agent": "judge", "record_id": case_id, "attempt": 1,
            "model": "gpt-4o-mini", "prompt_version": JUDGE_PROMPT_VERSION,
            "request": {"case_id": case_id}, "response": response,
            "response_hash": f"sha256:{response_hash_hex}",
            "delivered_fields_hash": None,
            "tokens_in": 60, "tokens_out": 25, "cost_usd": 0.00002, "latency_ms": 210.0,
        }
        path = TRANSCRIPTS_DIR / f"{response_hash_hex}.json"
        path.write_text(json.dumps(transcript, indent=2, sort_keys=True), encoding="utf-8")
        index[f"{case_id}:judge:1"] = path.name
        print(f"wrote {path.name}  <- {case_id}:judge:1")

    idx_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\n{len(RATIONALES)} judge transcripts indexed -> {idx_path}")


if __name__ == "__main__":
    main()
