from __future__ import annotations

import json
from typing import Any

from tinycedx.llm.client import call as llm_call

JUDGE_PROMPT_VERSION = "judge-v1"

SYSTEM_PROMPT = (
    "You are an independent LLM judge scoring how well one agent in a law-firm "
    "work-request pipeline handled a single golden test case. Score 0.0-1.0 for "
    "clarity and correctness of the agent's behavior, and give a one-sentence rationale. "
    'Reply with one JSON object only: {"score": <number 0.0-1.0>, "rationale": "<one sentence>"}'
)


def judge_case(*, case_id: str, agent: str, context: dict[str, Any]) -> dict[str, Any]:
    result = llm_call(
        agent="judge", record_id=case_id, attempt=1, model_tier="cheap", model_name="gpt-4o-mini",
        prompt_version=JUDGE_PROMPT_VERSION, system_prompt=SYSTEM_PROMPT,
        user_prompt=json.dumps(context, sort_keys=True), request_payload=context,
    )
    response = result["response"]
    return {
        "case_id": case_id,
        "agent": agent,
        "score": float(response.get("score", 0.0)),
        "rationale": response.get("rationale", ""),
        "cost_usd": result["cost_usd"],
    }
