from __future__ import annotations

import json
from typing import Any

from tinycedx import config
from tinycedx.hashutil import sha, sha_hex
from tinycedx.llm import live as live_llm
from tinycedx.llm.replay import replay_call


def _cost(model_tier: str, tokens_in: int, tokens_out: int) -> float:
    pricing = config.MODEL_PRICING_PER_1K.get(model_tier, config.MODEL_PRICING_PER_1K["cheap"])
    return round((tokens_in / 1000) * pricing["in"] + (tokens_out / 1000) * pricing["out"], 8)


def _persist_transcript(*, agent: str, record_id: str, attempt: int, model: str, prompt_version: str,
                         request: dict[str, Any], response: dict[str, Any], tokens_in: int, tokens_out: int,
                         cost_usd: float, latency_ms: float) -> dict[str, Any]:
    response_hash_hex = sha_hex(response)
    delivered_fields = response.get("delivered_fields") if isinstance(response, dict) else None
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
    config.TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.TRANSCRIPTS_DIR / f"{response_hash_hex}.json"
    path.write_text(json.dumps(transcript, indent=2, sort_keys=True), encoding="utf-8")

    idx_path = config.TRANSCRIPTS_DIR / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    idx[f"{record_id}:{agent}:{attempt}"] = path.name
    idx_path.write_text(json.dumps(idx, indent=2, sort_keys=True), encoding="utf-8")
    return transcript


def call(*, agent: str, record_id: str, attempt: int, model_tier: str, model_name: str,
          prompt_version: str, system_prompt: str = "", user_prompt: str = "",
          request_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if config.REPLAY_LLM:
        transcript = replay_call(config.TRANSCRIPTS_DIR, record_id=record_id, agent=agent, attempt=attempt)
    else:
        if not config.LLM_API_KEY:
            raise RuntimeError("REPLAY_LLM=false requires LLM_API_KEY to be set")
        result = live_llm.call_llm(
            model=model_name, api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL,
            system_prompt=system_prompt, user_prompt=user_prompt,
        )
        cost_usd = _cost(model_tier, result["tokens_in"], result["tokens_out"])
        transcript = _persist_transcript(
            agent=agent, record_id=record_id, attempt=attempt, model=result["model"],
            prompt_version=prompt_version, request=request_payload or {"system": system_prompt, "user": user_prompt},
            response=result["response"], tokens_in=result["tokens_in"], tokens_out=result["tokens_out"],
            cost_usd=cost_usd, latency_ms=result["latency_ms"],
        )

    return {
        "response": transcript["response"],
        "tokens_in": transcript.get("tokens_in", 0),
        "tokens_out": transcript.get("tokens_out", 0),
        "cost_usd": transcript.get("cost_usd", 0.0),
        "latency_ms": transcript.get("latency_ms", 0.0),
        "transcript_hash": transcript["response_hash"],
        "model": transcript.get("model", model_name),
        "prompt_version": transcript.get("prompt_version", prompt_version),
    }
