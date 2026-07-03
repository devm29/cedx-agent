from __future__ import annotations

import json

import pytest

from tests.conftest import REPO_ROOT
from tinycedx.hashutil import sha_hex
from tinycedx.llm import live
from tinycedx.llm.replay import TranscriptNotFound, replay_call

TRANSCRIPTS = REPO_ROOT / "transcripts"


def test_replay_returns_hash_checked_transcript():
    t = replay_call(TRANSCRIPTS, record_id="REC-001", agent="worker", attempt=1)
    assert t["agent"] == "worker"
    assert t["response_hash"] == "sha256:" + sha_hex(t["response"])


def test_replay_missing_key():
    with pytest.raises(TranscriptNotFound, match="no committed transcript"):
        replay_call(TRANSCRIPTS, record_id="NOPE", agent="worker", attempt=1)


def test_replay_rejects_edited_transcript(tmp_path):
    t = replay_call(TRANSCRIPTS, record_id="REC-001", agent="worker", attempt=1)
    t["response"]["confidence"] = 0.1
    (tmp_path / "x.json").write_text(json.dumps(t))
    (tmp_path / "index.json").write_text(json.dumps({"REC-001:worker:1": "x.json"}))
    with pytest.raises(TranscriptNotFound, match="does not match"):
        replay_call(tmp_path, record_id="REC-001", agent="worker", attempt=1)


def test_every_indexed_transcript_matches_its_key():
    index = json.loads((TRANSCRIPTS / "index.json").read_text())
    for key, name in index.items():
        record_id, agent, attempt = key.rsplit(":", 2)
        t = json.loads((TRANSCRIPTS / name).read_text())
        assert (t["record_id"], t["agent"], t["attempt"]) == (record_id, agent, int(attempt))
        assert name == sha_hex(t["response"]) + ".json"


@pytest.mark.parametrize("text", [
    '{"a": 1}', '```json\n{"a": 1}\n```', 'Here you go: {"a": 1} hope that helps',
])
def test_extract_json_text(text):
    assert live._extract_json_text(text) == {"a": 1}


@pytest.fixture
def fake_post(monkeypatch):
    calls = []

    def _post(url, headers, body, timeout=30.0):
        calls.append({"url": url, "headers": headers, "body": body})
        if "anthropic" in url:
            return {"content": [{"text": '{"ok": true}'}], "usage": {"input_tokens": 3, "output_tokens": 2}}
        if "generativelanguage" in url:
            return {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
                    "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}}
        return {"choices": [{"message": {"content": '{"ok": true}'}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}

    monkeypatch.setattr(live, "_post_json", _post)
    return calls


@pytest.mark.parametrize("model,host", [
    ("gpt-4o-mini", "api.openai.com"), ("claude-3-5-haiku", "api.anthropic.com"),
    ("gemini-1.5-flash", "generativelanguage.googleapis.com"),
])
def test_live_call_routes_by_model_family(fake_post, model, host):
    out = live.call_llm(model=model, api_key="test-key", base_url=None, system_prompt="s", user_prompt="u")
    assert host in fake_post[0]["url"]
    assert out["response"] == {"ok": True}
    assert (out["tokens_in"], out["tokens_out"]) == (3, 2)


def test_live_call_keeps_unparsable_text(fake_post, monkeypatch):
    monkeypatch.setattr(live, "_post_json", lambda *a, **k: {"choices": [{"message": {"content": "no json"}}], "usage": {}})
    assert live.call_llm(model="gpt-4o-mini", api_key="k", base_url=None, system_prompt="", user_prompt="")["response"] == {
        "_raw_unparsable": "no json"}
