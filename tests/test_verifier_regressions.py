from __future__ import annotations

import pytest

from tests.conftest import good_draft
from tinycedx import config
from tinycedx.agents import verifier
from tinycedx.agents.orchestrator import process_record
from tinycedx.eval import scenarios


@pytest.mark.parametrize("summary", ["Retainer $4,800.50.", "Retainer 4800.5.", "Retainer $4,800.", "Retainer $4,800.50 due 2026-09-01."])
def test_decimal_amount_in_summary_is_grounded(clean_record, summary):
    rec = {**clean_record, "amount": 4800.5}
    out = verifier.verify(source=rec, worker_output=good_draft(rec, summary=summary))
    assert out["verdict"] == "pass", out["mismatches"]


def test_near_miss_decimal_is_still_rejected(clean_record):
    rec = {**clean_record, "amount": 4800.5}
    out = verifier.verify(source=rec, worker_output=good_draft(rec, summary="Retainer $4,800.75."))
    assert out["verdict"] == "fail"


def test_id_digits_are_matched_as_written(clean_record):
    out = verifier.verify(source=clean_record, worker_output=good_draft(clean_record, summary="Matter 1 of 1."))
    assert out["verdict"] == "fail"


def test_low_confidence_draft_goes_to_a_human(clean_record):
    draft = good_draft(clean_record)
    draft["confidence"] = config.LOW_CONFIDENCE_THRESHOLD - 0.01
    out = verifier.verify(source=clean_record, worker_output=draft)
    assert out["verdict"] == "needs_human"
    assert "confidence" in out["notes"]


def test_threshold_confidence_is_accepted(clean_record):
    draft = good_draft(clean_record)
    draft["confidence"] = config.LOW_CONFIDENCE_THRESHOLD
    assert verifier.verify(source=clean_record, worker_output=draft)["verdict"] == "pass"


def test_orchestrator_never_delivers_an_unsure_draft(clean_record):
    def unsure_worker(**kw):
        result = scenarios.clean_worker(**kw)
        result["response"]["confidence"] = 0.2
        return result

    res = process_record(record=clean_record, low_confidence_flag=False, worker_fn=unsure_worker)
    assert (res["status"], res["reason_code"]) == ("exception", "LOW_CONFIDENCE")
