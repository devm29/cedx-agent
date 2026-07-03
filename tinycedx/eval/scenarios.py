from __future__ import annotations

from typing import Any

from tinycedx import config


def clean_worker(*, record: dict[str, Any], model_tier: str, model_name: str, attempt: int,
                  repair_hint: str | None = None) -> dict[str, Any]:
    return {
        "record_id": record["id"],
        "response": {
            "record_id": record["id"],
            "delivered_fields": {
                "matter_id": record["id"], "responsible_attorney": record["owner"],
                "deadline": record["deadline"], "matter_type": record["category"],
                "matter_value": record["amount"], "summary": f"Routine matter for {record['owner']}.",
            },
            "confidence": 0.93, "abstain": False, "abstain_reason": None,
        },
        "malformed": False, "tokens_in": 150, "tokens_out": 80, "cost_usd": 0.00005,
        "latency_ms": 300.0, "transcript_hash": "sha256:" + "0" * 64, "model": model_name,
        "prompt_version": "eval-fixture-v1",
    }


def abstain_worker(*, record: dict[str, Any], model_tier: str, model_name: str, attempt: int,
                    repair_hint: str | None = None) -> dict[str, Any]:
    return {
        "record_id": record["id"],
        "response": {
            "record_id": record["id"], "delivered_fields": None,
            "confidence": 0.3, "abstain": True,
            "abstain_reason": "insufficient grounded information to draft confidently",
        },
        "malformed": False, "tokens_in": 120, "tokens_out": 40, "cost_usd": 0.00004,
        "latency_ms": 280.0, "transcript_hash": "sha256:" + "1" * 64, "model": model_name,
        "prompt_version": "eval-fixture-v1",
    }


def hallucinating_worker(*, record: dict[str, Any], model_tier: str, model_name: str, attempt: int,
                          repair_hint: str | None = None) -> dict[str, Any]:
    return {
        "record_id": record["id"],
        "response": {
            "record_id": record["id"],
            "delivered_fields": {
                "matter_id": record["id"], "responsible_attorney": record["owner"],
                "deadline": record["deadline"], "matter_type": record["category"],
                "matter_value": (record["amount"] or 0) + 99999,
                "summary": "Routine matter.", "invented_field": "not supported by source",
            },
            "confidence": 0.9, "abstain": False, "abstain_reason": None,
        },
        "malformed": False, "tokens_in": 100, "tokens_out": 50, "cost_usd": 0.0001,
        "latency_ms": 100.0, "transcript_hash": "sha256:" + "a" * 64, "model": model_name,
        "prompt_version": "eval-fixture-v1",
    }


def malformed_worker(*, record: dict[str, Any], model_tier: str, model_name: str, attempt: int,
                      repair_hint: str | None = None) -> dict[str, Any]:
    return {
        "record_id": record["id"],
        "response": {"this_is": "not a valid WorkerOutput shape"},
        "malformed": True, "tokens_in": 40, "tokens_out": 10, "cost_usd": 0.00001,
        "latency_ms": 60.0, "transcript_hash": "sha256:" + "b" * 64, "model": model_name,
        "prompt_version": "eval-fixture-v1",
    }


def make_flapping_worker():
    """Alternates malformed/hallucinating every call -- never converges, so
    the Orchestrator's step ceiling should kill it with AGENT_LOOP."""
    calls = {"n": 0}

    def _fn(*, record, model_tier, model_name, attempt, repair_hint=None):
        calls["n"] += 1
        fn = malformed_worker if calls["n"] % 2 == 1 else hallucinating_worker
        return fn(record=record, model_tier=model_tier, model_name=model_name, attempt=attempt)

    return _fn


def priced_worker(*, record: dict[str, Any], model_tier: str, model_name: str, attempt: int,
                   repair_hint: str | None = None) -> dict[str, Any]:
    tokens_in, tokens_out = config.ESTIMATED_TOKENS_IN, config.ESTIMATED_TOKENS_OUT
    pricing = config.MODEL_PRICING_PER_1K[model_tier]
    cost = (tokens_in / 1000) * pricing["in"] + (tokens_out / 1000) * pricing["out"]
    return {
        "record_id": record["id"],
        "response": {
            "record_id": record["id"],
            "delivered_fields": {
                "matter_id": record["id"], "responsible_attorney": record["owner"],
                "deadline": record["deadline"], "matter_type": record["category"],
                "matter_value": record["amount"], "summary": f"Routine matter for {record['owner']}.",
            },
            "confidence": 0.9, "abstain": False, "abstain_reason": None,
        },
        "malformed": False, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost,
        "latency_ms": 150.0, "transcript_hash": "sha256:" + "c" * 64, "model": model_name,
        "prompt_version": "eval-fixture-v1",
    }
