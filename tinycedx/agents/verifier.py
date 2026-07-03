from __future__ import annotations

import re
from typing import Any

from tinycedx.agents.base import Agent
from tinycedx.agents.contracts import VERIFIER_INPUT, VERIFIER_OUTPUT, validate

VERIFIER_AGENT = Agent(
    name="verifier", role="verifier", models=["rule-based-verifier-v1"], can_call=[],
    prompt_version="verifier-crosscheck-v1",
)

PASSTHROUGH_MAP = {
    "matter_id": "id", "responsible_attorney": "owner", "deadline": "deadline",
    "matter_type": "category", "matter_value": "amount",
}
ALLOWED_KEYS = set(PASSTHROUGH_MAP) | {"summary"}
_DIGIT_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _source_digit_tokens(source: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for v in (source.get("id"), source.get("deadline")):
        if v:
            tokens.update(_DIGIT_RE.findall(str(v)))
    amount = source.get("amount")
    if isinstance(amount, (int, float)):
        tokens.add(str(int(amount)) if float(amount).is_integer() else str(amount))
        tokens.add(f"{amount:,.0f}")
    return tokens


def verify(*, source: dict[str, Any], worker_output: dict[str, Any]) -> dict[str, Any]:
    validate({"record_id": source["id"], "source": source, "worker_output": worker_output},
             VERIFIER_INPUT, label="VerifierInput")

    if worker_output.get("abstain"):
        result = {
            "record_id": source["id"], "verdict": "needs_human", "mismatches": [],
            "overruled": False, "notes": worker_output.get("abstain_reason"),
        }
        validate(result, VERIFIER_OUTPUT, label="VerifierOutput")
        return result

    mismatches: list[str] = []
    delivered = worker_output.get("delivered_fields")

    if delivered is None:
        mismatches.append("delivered_fields is null but abstain=false")
    else:
        extra_keys = sorted(set(delivered) - ALLOWED_KEYS)
        if extra_keys:
            mismatches.append(f"invented field(s) not supported by source or contract: {extra_keys}")

        for out_key, src_key in PASSTHROUGH_MAP.items():
            if out_key not in delivered:
                mismatches.append(f"missing passthrough field {out_key}")
                continue
            out_val, src_val = delivered[out_key], source.get(src_key)
            if isinstance(out_val, (int, float)) and isinstance(src_val, (int, float)):
                if abs(float(out_val) - float(src_val)) > 1e-6:
                    mismatches.append(f"{out_key}={out_val} does not match source {src_key}={src_val}")
            elif str(out_val).strip() != str(src_val).strip():
                mismatches.append(f"{out_key}={out_val!r} does not match source {src_key}={src_val!r}")

        summary = str(delivered.get("summary") or "")
        grounded = _source_digit_tokens(source)
        for tok in _DIGIT_RE.findall(summary):
            if tok not in grounded and tok.replace(",", "") not in grounded:
                mismatches.append(f"summary references a number not grounded in source: {tok!r}")

    verdict = "fail" if mismatches else "pass"
    result = {
        "record_id": source["id"], "verdict": verdict, "mismatches": mismatches,
        "overruled": bool(mismatches), "notes": None,
    }
    validate(result, VERIFIER_OUTPUT, label="VerifierOutput")
    return result
