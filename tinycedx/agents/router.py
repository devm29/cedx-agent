from __future__ import annotations

from typing import Any

from tinycedx.agents.base import Agent
from tinycedx.agents.contracts import ROUTER_INPUT, ROUTER_OUTPUT, validate
from tinycedx.config import MODEL_PRICING_PER_1K

ROUTER_AGENT = Agent(
    name="router", role="router", models=[], can_call=[], prompt_version="router-policy-v1",
)


def decide(*, record_id: str, low_confidence_flag: bool, prior_retry_count: int,
           amount: float | None, amendment_threshold: float | None) -> dict[str, Any]:
    payload = {
        "record_id": record_id, "low_confidence_flag": low_confidence_flag,
        "prior_retry_count": prior_retry_count, "amount": amount,
        "amendment_threshold": amendment_threshold,
    }
    validate(payload, ROUTER_INPUT, label="RouterInput")

    reasons = []
    strong = False
    if low_confidence_flag:
        strong = True
        reasons.append("low_confidence_prefilter")
    if prior_retry_count > 0:
        strong = True
        reasons.append("escalate_on_verifier_retry")
    if amount is not None and amendment_threshold is not None and amount >= amendment_threshold:
        strong = True
        reasons.append("amount_at_or_above_amendment_threshold")

    tier = "strong" if strong else "cheap"
    output = {
        "model_tier": tier,
        "model_name": MODEL_PRICING_PER_1K[tier]["model"],
        "reason": ",".join(reasons) or "clean_record_default_cheap",
    }
    validate(output, ROUTER_OUTPUT, label="RouterOutput")
    return output
