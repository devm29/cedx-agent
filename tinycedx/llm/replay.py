from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tinycedx.hashutil import sha_hex


class TranscriptNotFound(Exception):
    pass


def _index_key(record_id: str, agent: str, attempt: int) -> str:
    return f"{record_id}:{agent}:{attempt}"


def load_index(transcripts_dir: Path) -> dict[str, str]:
    idx_path = transcripts_dir / "index.json"
    if not idx_path.exists():
        return {}
    return json.loads(idx_path.read_text(encoding="utf-8"))


def replay_call(transcripts_dir: Path, *, record_id: str, agent: str, attempt: int) -> dict[str, Any]:
    index = load_index(transcripts_dir)
    key = _index_key(record_id, agent, attempt)
    filename = index.get(key)
    if not filename:
        raise TranscriptNotFound(f"no committed transcript for {key}")
    path = transcripts_dir / filename
    if not path.exists():
        raise TranscriptNotFound(f"transcript file missing: {path}")
    transcript = json.loads(path.read_text(encoding="utf-8"))

    expected_hex = sha_hex(transcript["response"])
    if transcript.get("response_hash") != f"sha256:{expected_hex}":
        raise TranscriptNotFound(f"transcript {filename} response_hash does not match its response")

    return transcript
