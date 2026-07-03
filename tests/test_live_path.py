"""The REPLAY_LLM=false path, exercised with a fake HTTP layer -- no network, no keys."""
from __future__ import annotations

import json

import pytest

from tests.conftest import good_draft
from tinycedx import config
from tinycedx.agents import worker
from tinycedx.eval import judge
from tinycedx.llm import client, live


@pytest.fixture
def live_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "REPLAY_LLM", False)
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "TRANSCRIPTS_DIR", tmp_path)
    monkeypatch.setattr(config, "LLM_MODEL", None)
    monkeypatch.setattr(config, "LLM_MODEL_STRONG", None)
    calls = []

    def fake_call_llm(*, model, api_key, base_url, system_prompt, user_prompt):
        calls.append({"model": model, "system": system_prompt, "user": user_prompt})
        record = json.loads(user_prompt)
        if "record_id" in record:
            response = good_draft({"id": record["record_id"], "owner": record["owner"], "deadline": record["deadline"],
                                   "category": record["category"], "amount": record["amount"]})
        else:
            response = {"score": 0.8, "rationale": "fine"}
        return {"response": response, "tokens_in": 10, "tokens_out": 5, "latency_ms": 1.0, "model": model}

    monkeypatch.setattr(live, "call_llm", fake_call_llm)
    return calls


def test_live_mode_requires_a_key(monkeypatch):
    monkeypatch.setattr(config, "REPLAY_LLM", False)
    monkeypatch.setattr(config, "LLM_API_KEY", None)
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        client.call(agent="worker", record_id="R", attempt=1, model_tier="cheap", model_name="gpt-4o-mini", prompt_version="v")


def test_default_models_follow_the_router_tier(live_mode):
    client.call(agent="worker", record_id="R", attempt=1, model_tier="cheap", model_name="gpt-4o-mini", prompt_version="v",
                user_prompt="{}")
    client.call(agent="worker", record_id="R", attempt=2, model_tier="strong", model_name="gpt-4o", prompt_version="v",
                user_prompt="{}")
    assert [c["model"] for c in live_mode] == ["gpt-4o-mini", "gpt-4o"]


def test_llm_model_env_is_honoured(live_mode, monkeypatch):
    monkeypatch.setattr(config, "LLM_MODEL", "claude-3-5-haiku")
    out = client.call(agent="worker", record_id="R", attempt=1, model_tier="strong", model_name="gpt-4o", prompt_version="v",
                      user_prompt="{}")
    assert live_mode[0]["model"] == "claude-3-5-haiku"
    assert out["model"] == "claude-3-5-haiku"


def test_strong_tier_can_use_its_own_model(live_mode, monkeypatch):
    monkeypatch.setattr(config, "LLM_MODEL", "gemini-1.5-flash")
    monkeypatch.setattr(config, "LLM_MODEL_STRONG", "gemini-1.5-pro")
    for tier, attempt in (("cheap", 1), ("strong", 2)):
        client.call(agent="worker", record_id="R", attempt=attempt, model_tier=tier, model_name="x", prompt_version="v",
                    user_prompt="{}")
    assert [c["model"] for c in live_mode] == ["gemini-1.5-flash", "gemini-1.5-pro"]


def test_live_worker_call_is_recorded_as_a_replayable_transcript(live_mode, tmp_path, clean_record):
    result = worker.run(record=clean_record, model_tier="cheap", model_name="gpt-4o-mini", attempt=1)
    assert result["malformed"] is False
    index = json.loads((tmp_path / "index.json").read_text())
    stored = json.loads((tmp_path / index["T-001:worker:1"]).read_text())
    assert stored["agent"] == "worker" and stored["response"] == result["response"]


def test_worker_prompt_spells_out_the_output_contract(live_mode, clean_record):
    worker.run(record=clean_record, model_tier="cheap", model_name="gpt-4o-mini", attempt=1)
    prompt = live_mode[0]["system"]
    for key in ("record_id", "delivered_fields", "confidence", "abstain", "abstain_reason",
                "matter_id", "responsible_attorney", "matter_type", "matter_value", "summary"):
        assert key in prompt


def test_judge_prompt_asks_for_json_score(live_mode):
    out = judge.judge_case(case_id="gc-x", agent="worker", context={"kind": "k", "correct": True})
    assert out["score"] == 0.8
    assert "JSON" in live_mode[0]["system"] and '"score"' in live_mode[0]["system"]


def test_gemini_key_is_sent_as_a_header_not_in_the_url(monkeypatch):
    seen = {}

    def fake_post(url, headers, body, timeout=30.0):
        seen.update(url=url, headers=headers)
        return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}], "usageMetadata": {}}

    monkeypatch.setattr(live, "_post_json", fake_post)
    live.call_llm(model="gemini-1.5-flash", api_key="secret-key", base_url=None, system_prompt="s", user_prompt="u")
    assert "secret-key" not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "secret-key"
