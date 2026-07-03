from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Agent:
    name: str
    role: str
    models: list[str]
    can_call: list[str]
    prompt_version: str

    def roster_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "models": self.models,
            "prompt_version": self.prompt_version,
            "can_call": self.can_call,
        }


def make_span(
    *,
    agent: str,
    status: str,
    model: str | None = None,
    prompt_version: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
    latency_ms: float | None = None,
    retries: int | None = None,
    transcript_hash: str | None = None,
    verdict: str | None = None,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "model": model,
        "prompt_version": prompt_version,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
        "retries": retries,
        "transcript_hash": transcript_hash,
        "status": status,
        "verdict": verdict,
    }
