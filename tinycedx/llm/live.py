from __future__ import annotations

import json
import time
import urllib.request
from typing import Any


class LiveCallError(Exception):
    pass


def _post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_json_text(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def call_llm(*, model: str, api_key: str, base_url: str | None, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    t0 = time.monotonic()
    lower = model.lower()

    if lower.startswith("claude"):
        url = (base_url or "https://api.anthropic.com") + "/v1/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        body = {
            "model": model, "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        raw = _post_json(url, headers, body)
        text = "".join(b.get("text", "") for b in raw.get("content", []))
        usage = raw.get("usage", {})
        tokens_in, tokens_out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)

    elif lower.startswith("gemini"):
        url = (base_url or "https://generativelanguage.googleapis.com") + f"/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"content-type": "application/json"}
        body = {"contents": [{"parts": [{"text": system_prompt + "\n\n" + user_prompt}]}]}
        raw = _post_json(url, headers, body)
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        usage = raw.get("usageMetadata", {})
        tokens_in = usage.get("promptTokenCount", 0)
        tokens_out = usage.get("candidatesTokenCount", 0)

    else:
        url = (base_url or "https://api.openai.com/v1") + "/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        }
        raw = _post_json(url, headers, body)
        text = raw["choices"][0]["message"]["content"]
        usage = raw.get("usage", {})
        tokens_in, tokens_out = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)

    latency_ms = (time.monotonic() - t0) * 1000
    try:
        parsed = _extract_json_text(text)
    except json.JSONDecodeError:
        parsed = {"_raw_unparsable": text}

    return {
        "response": parsed,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "model": model,
    }
