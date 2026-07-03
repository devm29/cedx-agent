"""Records that arrive without an id must be quarantined, not crash the run or merge into each other."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

from tests.conftest import REPO_ROOT, SCHEMA_DIR, SEED_DIR
from tinycedx.detectors.missing import check_missing
from tinycedx.normalize.normalize import _load_alias_map, normalize_record
from tinycedx.normalize.versions import resolve_versions

NO_ID_EML = """From: intake@partner.example
To: queue@example.com
Subject: Work request
Content-Type: text/plain; charset=utf-8

Owner: q.test
Deadline: 2026-08-10
Amount: 4700
Category: REVIEW
Notes: Sent without a reference number.
"""


def _normalized(fields: dict, order: int) -> dict:
    raw = {"id": None, "source_format": "eml", "source_file": f"x{order}.eml", "source_version_hash": None,
           "intake_order": order, "raw_fields": fields}
    return normalize_record(raw, _load_alias_map(SCHEMA_DIR))


def test_id_less_records_get_distinct_placeholder_ids_and_count_as_missing():
    a = _normalized({"Owner": "a", "Amount": "1"}, 0)
    b = _normalized({"Owner": "b", "Amount": "2"}, 1)
    assert a["id"] != b["id"]
    assert "id" in check_missing(a)
    kept, superseded = resolve_versions([a, b])
    assert len(kept) == 2 and superseded == []


def test_pipeline_quarantines_id_less_records(tmp_path):
    seed = tmp_path / "seed"
    shutil.copytree(SEED_DIR, seed)
    (seed / "inbox" / "REC-NOID_v1.eml").write_text(NO_ID_EML)
    feed = json.loads((seed / "feed.json").read_text())
    feed.append({"owner": "r.test", "deadline": "2026-08-11", "category": "REPORT", "notes": "no id", "version": 1, "amount": 5100})
    (seed / "feed.json").write_text(json.dumps(feed))

    out = tmp_path / "out"
    proc = subprocess.run([sys.executable, "-m", "tinycedx.pipeline.run"], cwd=REPO_ROOT, capture_output=True, text=True,
                          env={**_env(), "SEED_DIR": str(seed), "OUT_DIR": str(out)}, check=False)
    assert proc.returncode == 0, proc.stderr

    audit = json.loads((out / "audit.json").read_text())
    no_id = [r for r in audit["records"] if r["id"].startswith("NO-ID:")]
    assert len(no_id) == 2
    assert {(r["status"], r["reason_code"]) for r in no_id} == {("exception", "MISSING_INPUT")}

    gate = subprocess.run([sys.executable, "verify_audit.py", "--audit", str(out / "audit.json"), "--transcripts", "transcripts",
                           "--schema", "audit.schema.json"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert gate.returncode == 0, gate.stdout


def _env() -> dict:
    import os
    env = {**os.environ, "REPLAY_LLM": "true", "CASE_ID": "CEDX-82C0A1", "PIPELINE_NOW": "2026-06-26"}
    env.pop("LLM_API_KEY", None)
    return env
