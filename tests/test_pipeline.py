"""End-to-end: run the real pipeline on the dev seed in replay mode, in a subprocess, into a temp OUT_DIR."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter

import pytest

from tests.conftest import REPO_ROOT, SEED_DIR
from tinycedx.intake.store import collect_raw_records


def _run(module: str, out_dir, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "OUT_DIR": str(out_dir), "SEED_DIR": str(SEED_DIR), "REPLAY_LLM": "true",
           "CASE_ID": "CEDX-82C0A1", "PIPELINE_NOW": "2026-06-26"}
    env.pop("LLM_API_KEY", None)
    return subprocess.run([sys.executable, "-m", module, *args], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, check=False)


@pytest.fixture(scope="module")
def demo_out(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    proc = _run("tinycedx.pipeline.run", out)
    assert proc.returncode == 0, proc.stderr
    return out


@pytest.fixture(scope="module")
def audit(demo_out):
    return json.loads((demo_out / "audit.json").read_text())


def test_intake_reads_feed_eml_and_pdf():
    raw = collect_raw_records(SEED_DIR)
    assert Counter(r["source_format"] for r in raw) == {"feed": 16, "eml": 3, "pdf": 4}
    assert all(r["source_version_hash"].startswith("sha256:") for r in raw)


def test_demo_outcome_on_dev_seed(audit):
    status = Counter(r["status"] for r in audit["records"])
    assert status == {"delivered": 14, "exception": 8, "superseded": 1}
    codes = {r["id"]: r["reason_code"] for r in audit["records"] if r["status"] == "exception"}
    assert codes["REC-014"] == "INJECTION_BLOCKED"
    assert codes["REC-018"] == "AGENT_HALLUCINATION"
    assert codes["REC-015"] == codes["REC-021"] == "LOW_CONFIDENCE"


def test_no_blocking_record_is_in_the_package(demo_out, audit):
    package = json.loads((demo_out / "branded_package.json").read_text())
    exception_ids = {r["id"] for r in audit["records"] if r["status"] == "exception"}
    assert package["record_count"] == 14
    assert not exception_ids & {r["id"] for r in package["records"]}


def test_provided_gate_passes(demo_out):
    proc = subprocess.run([sys.executable, "verify_audit.py", "--audit", str(demo_out / "audit.json"),
                           "--transcripts", "transcripts", "--schema", "audit.schema.json"],
                          cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout
    assert proc.stdout.startswith("PASS: 23 records")


def test_rerun_is_idempotent(demo_out, audit, tmp_path):
    assert _run("tinycedx.pipeline.run", tmp_path).returncode == 0
    second = json.loads((tmp_path / "audit.json").read_text())

    def fingerprint(a):
        return sorted((r["id"], r["version"], r["status"], r["reason_code"], r["delivered_fields_hash"]) for r in a["records"])

    assert fingerprint(second) == fingerprint(audit)
    assert len(second["events"]) == len(audit["events"])


def test_trace_prints_agent_path(demo_out):
    proc = _run("tinycedx.cli.trace", demo_out, "--id", "REC-018", "--audit", str(demo_out / "audit.json"))
    assert proc.returncode == 0
    assert "reason_code=AGENT_HALLUCINATION" in proc.stdout
    assert proc.stdout.count("agent=verifier") == 2


def test_replay_rebuilds_lineage(demo_out):
    proc = _run("tinycedx.cli.replay_cmd", demo_out, "--id", "REC-016", "--audit", str(demo_out / "audit.json"))
    assert proc.returncode == 0
    assert "matches audit entry: OK" in proc.stdout


def test_trace_unknown_id_fails(demo_out):
    proc = _run("tinycedx.cli.trace", demo_out, "--id", "NOPE", "--audit", str(demo_out / "audit.json"))
    assert proc.returncode == 1


@pytest.mark.parametrize("probe", ["approval", "agent_failure", "budget", "append_only"])
def test_probes_pass(demo_out, probe):
    proc = _run(f"tinycedx.cli.probes.{probe}", demo_out)
    assert proc.returncode == 0, proc.stdout
    assert "PASS" in proc.stdout


def test_eval_harness_passes(demo_out):
    proc = _run("tinycedx.eval.run_eval", demo_out)
    assert proc.returncode == 0, proc.stdout
    assert "overall: 14/14" in proc.stdout


def test_trace_of_superseded_id_shows_the_live_version(demo_out):
    proc = _run("tinycedx.cli.trace", demo_out, "--id", "REC-017", "--audit", str(demo_out / "audit.json"))
    assert proc.returncode == 0
    assert "status=delivered" in proc.stdout.splitlines()[0]
    assert "version=2" in proc.stdout
    assert "v1 (superseded)" in proc.stdout


def test_trace_can_select_an_older_version(demo_out):
    proc = _run("tinycedx.cli.trace", demo_out, "--id", "REC-017", "--version", "1", "--audit", str(demo_out / "audit.json"))
    assert proc.returncode == 0
    assert "status=superseded" in proc.stdout.splitlines()[0]
    assert _run("tinycedx.cli.trace", demo_out, "--id", "REC-017", "--version", "9",
                "--audit", str(demo_out / "audit.json")).returncode == 1


def test_replay_of_superseded_id_shows_the_delivered_lineage(demo_out):
    proc = _run("tinycedx.cli.replay_cmd", demo_out, "--id", "REC-017", "--audit", str(demo_out / "audit.json"))
    assert proc.returncode == 0
    assert "version: 2  final status: delivered" in proc.stdout
    assert "matches audit entry: OK" in proc.stdout


def test_exception_queue_names_the_responsible_attorney(demo_out):
    queue = {e["id"]: e for e in json.loads((demo_out / "exception_queue.json").read_text())}
    assert len(queue) == 8
    assert queue["REC-011"]["owner"] == "k.banerjee"
    assert all(e["owner"] for e in queue.values() if "'owner'" not in (e["detail"] or ""))
