from __future__ import annotations

from typing import Any

import jsonschema


class ContractError(Exception):
    pass


def validate(data: Any, schema: dict[str, Any], *, label: str) -> None:
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as e:
        raise ContractError(f"{label} failed contract validation: {e.message}") from e


ROUTER_INPUT = {
    "type": "object",
    "required": ["record_id", "low_confidence_flag", "prior_retry_count", "amount"],
    "properties": {
        "record_id": {"type": "string"},
        "low_confidence_flag": {"type": "boolean"},
        "prior_retry_count": {"type": "integer", "minimum": 0},
        "amount": {"type": ["number", "null"]},
        "amendment_threshold": {"type": ["number", "null"]},
    },
}
ROUTER_OUTPUT = {
    "type": "object",
    "required": ["model_tier", "model_name", "reason"],
    "properties": {
        "model_tier": {"type": "string", "enum": ["cheap", "strong"]},
        "model_name": {"type": "string"},
        "reason": {"type": "string"},
    },
}

WORKER_INPUT = {
    "type": "object",
    "required": ["record_id", "owner", "deadline", "category", "amount", "notes",
                 "model_tier", "model_name", "attempt"],
    "properties": {
        "record_id": {"type": "string"},
        "owner": {"type": ["string", "null"]},
        "deadline": {"type": ["string", "null"]},
        "category": {"type": ["string", "null"]},
        "amount": {"type": ["number", "null"]},
        "notes": {"type": ["string", "null"]},
        "model_tier": {"type": "string"},
        "model_name": {"type": "string"},
        "attempt": {"type": "integer", "minimum": 1},
        "repair_hint": {"type": ["string", "null"]},
    },
}
WORKER_OUTPUT = {
    "type": "object",
    "required": ["record_id", "delivered_fields", "confidence", "abstain"],
    "properties": {
        "record_id": {"type": "string"},
        "delivered_fields": {"type": ["object", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "abstain": {"type": "boolean"},
        "abstain_reason": {"type": ["string", "null"]},
    },
}

VERIFIER_INPUT = {
    "type": "object",
    "required": ["record_id", "source", "worker_output"],
    "properties": {
        "record_id": {"type": "string"},
        "source": {"type": "object"},
        "worker_output": {"type": "object"},
    },
}
VERIFIER_OUTPUT = {
    "type": "object",
    "required": ["record_id", "verdict", "mismatches", "overruled"],
    "properties": {
        "record_id": {"type": "string"},
        "verdict": {"type": "string", "enum": ["pass", "fail", "needs_human"]},
        "mismatches": {"type": "array", "items": {"type": "string"}},
        "overruled": {"type": "boolean"},
        "notes": {"type": ["string", "null"]},
    },
}

OPERATOR_ACTION = {
    "type": "object",
    "required": ["record_id", "action", "actor"],
    "properties": {
        "record_id": {"type": "string"},
        "action": {"type": "string", "enum": ["approve", "reject", "request_changes", "edit_resolve"]},
        "actor": {"type": "string"},
        "role": {"type": ["string", "null"]},
        "note": {"type": ["string", "null"]},
        "edits": {"type": ["object", "null"]},
    },
}
