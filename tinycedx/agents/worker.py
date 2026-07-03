from __future__ import annotations

import json
from typing import Any

from tinycedx.agents.base import Agent
from tinycedx.agents.contracts import WORKER_INPUT, WORKER_OUTPUT, ContractError, validate
from tinycedx.llm.client import call as llm_call

WORKER_AGENT = Agent(
    name="worker", role="worker", models=["gpt-4o-mini", "gpt-4o"], can_call=[],
    prompt_version="worker-v1",
)

SYSTEM_PROMPT = (
    "You are the Assembly Worker for a law-firm work-request pipeline. Given a "
    "normalized matter record, draft delivered_fields using ONLY facts present in "
    "the record. Passthrough fields (matter_id, responsible_attorney, deadline, "
    "matter_type, matter_value) must exactly match the source -- never invent a "
    "field or figure not present in the record. If the record is too ambiguous to "
    "draft confidently, set abstain=true and explain why in abstain_reason instead "
    "of guessing.\n\n"
    "Reply with one JSON object and nothing else, in exactly this shape:\n"
    '{"record_id": <record_id from the input>, '
    '"delivered_fields": {"matter_id": ..., "responsible_attorney": ..., "deadline": ..., '
    '"matter_type": ..., "matter_value": ..., "summary": "<one sentence>"} or null when abstaining, '
    '"confidence": <number 0-1>, "abstain": <true|false>, "abstain_reason": <string or null>}\n'
    "matter_id, responsible_attorney, deadline, matter_type and matter_value copy the input's "
    "record_id, owner, deadline, category and amount unchanged. Add no other keys. Any number "
    "in the summary must appear in the input."
)


def run(*, record: dict[str, Any], model_tier: str, model_name: str, attempt: int,
        repair_hint: str | None = None) -> dict[str, Any]:
    payload = {
        "record_id": record["id"], "owner": record["owner"], "deadline": record["deadline"],
        "category": record["category"], "amount": record["amount"], "notes": record["notes"],
        "model_tier": model_tier, "model_name": model_name, "attempt": attempt,
        "repair_hint": repair_hint,
    }
    validate(payload, WORKER_INPUT, label="WorkerInput")

    result = llm_call(
        agent="worker", record_id=record["id"], attempt=attempt, model_tier=model_tier,
        model_name=model_name, prompt_version=WORKER_AGENT.prompt_version,
        system_prompt=SYSTEM_PROMPT, user_prompt=json.dumps(payload, sort_keys=True),
        request_payload=payload,
    )
    response = result["response"]

    malformed = False
    try:
        validate(response, WORKER_OUTPUT, label="WorkerOutput")
    except ContractError:
        malformed = True

    return {
        "record_id": record["id"],
        "response": response,
        "malformed": malformed,
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "cost_usd": result["cost_usd"],
        "latency_ms": result["latency_ms"],
        "transcript_hash": result["transcript_hash"],
        "model": result["model"],
        "prompt_version": result["prompt_version"],
    }
