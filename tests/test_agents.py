from __future__ import annotations

import pytest

from tests.conftest import good_draft
from tinycedx import config
from tinycedx.agents import router, verifier
from tinycedx.agents.contracts import ContractError
from tinycedx.agents.orchestrator import process_record
from tinycedx.eval import scenarios


def test_router_defaults_to_cheap():
    out = router.decide(record_id="R", low_confidence_flag=False, prior_retry_count=0, amount=100.0,
                        amendment_threshold=42000)
    assert (out["model_tier"], out["reason"]) == ("cheap", "clean_record_default_cheap")


@pytest.mark.parametrize("kwargs,reason", [
    ({"low_confidence_flag": True}, "low_confidence_prefilter"),
    ({"prior_retry_count": 1}, "escalate_on_verifier_retry"),
    ({"amount": 42000.0}, "amount_at_or_above_amendment_threshold"),
])
def test_router_escalates(kwargs, reason):
    args = {"record_id": "R", "low_confidence_flag": False, "prior_retry_count": 0, "amount": 100.0,
            "amendment_threshold": 42000, **kwargs}
    out = router.decide(**args)
    assert out["model_tier"] == "strong"
    assert out["model_name"] == config.MODEL_PRICING_PER_1K["strong"]["model"]
    assert reason in out["reason"]


def test_router_rejects_bad_input():
    with pytest.raises(ContractError):
        router.decide(record_id="R", low_confidence_flag="no", prior_retry_count=0, amount=1.0, amendment_threshold=None)


def test_verifier_passes_grounded_draft(clean_record):
    out = verifier.verify(source=clean_record, worker_output=good_draft(clean_record, summary="Matter value $5,000 due 2026-09-01."))
    assert out["verdict"] == "pass" and out["mismatches"] == []


def test_verifier_rejects_invented_field(clean_record):
    out = verifier.verify(source=clean_record, worker_output=good_draft(clean_record, risk_rating="high"))
    assert out["verdict"] == "fail" and out["overruled"] is True
    assert "risk_rating" in out["mismatches"][0]


def test_verifier_rejects_changed_passthrough_value(clean_record):
    out = verifier.verify(source=clean_record, worker_output=good_draft(clean_record, matter_value=9999))
    assert any("matter_value" in m for m in out["mismatches"])


def test_verifier_rejects_ungrounded_number_in_summary(clean_record):
    out = verifier.verify(source=clean_record, worker_output=good_draft(clean_record, summary="Value $9,999."))
    assert any("not grounded" in m for m in out["mismatches"])


def test_verifier_routes_abstain_to_human(clean_record):
    draft = {"record_id": clean_record["id"], "delivered_fields": None, "confidence": 0.3, "abstain": True,
             "abstain_reason": "ambiguous"}
    out = verifier.verify(source=clean_record, worker_output=draft)
    assert (out["verdict"], out["notes"]) == ("needs_human", "ambiguous")


def test_orchestrator_assembles_clean_record(clean_record):
    res = process_record(record=clean_record, low_confidence_flag=False, worker_fn=scenarios.clean_worker)
    assert res["status"] == "assembled" and res["model_tier"] == "cheap"
    assert [s["agent"] for s in res["agent_trace"]] == ["router", "worker", "verifier"]


def test_orchestrator_retries_then_raises_hallucination(clean_record):
    res = process_record(record=clean_record, low_confidence_flag=False, worker_fn=scenarios.hallucinating_worker)
    assert res["reason_code"] == "AGENT_HALLUCINATION"
    workers = [s for s in res["agent_trace"] if s["agent"] == "worker"]
    assert [s["status"] for s in workers] == ["overruled", "overruled"]
    assert [s["model"] for s in workers] == ["gpt-4o-mini", "gpt-4o"]


def test_orchestrator_bounds_malformed_retries(clean_record):
    res = process_record(record=clean_record, low_confidence_flag=False, worker_fn=scenarios.malformed_worker)
    assert res["reason_code"] == "AGENT_MALFORMED"
    assert res["delivered_fields"] is None


def test_orchestrator_kills_non_converging_worker(clean_record):
    res = process_record(record=clean_record, low_confidence_flag=False, max_steps=4,
                         worker_fn=scenarios.make_flapping_worker())
    assert res["reason_code"] == "AGENT_LOOP"
    assert res["agent_trace"][-1]["status"] == "killed"


def test_orchestrator_abstain_becomes_low_confidence(clean_record):
    res = process_record(record=clean_record, low_confidence_flag=True, worker_fn=scenarios.abstain_worker)
    assert res["reason_code"] == "LOW_CONFIDENCE"


def test_budget_downgrades_strong_to_cheap(clean_record):
    ceiling = (config.estimate_cost("strong") + config.estimate_cost("cheap")) / 2
    res = process_record(record=clean_record, low_confidence_flag=True, amendment_threshold=10**9,
                         max_cost_usd=ceiling, worker_fn=scenarios.priced_worker)
    assert (res["status"], res["model_tier"]) == ("assembled", "cheap")


def test_budget_exceeded_when_nothing_fits(clean_record):
    res = process_record(record=clean_record, low_confidence_flag=False, max_cost_usd=config.estimate_cost("cheap") / 10,
                         worker_fn=scenarios.priced_worker)
    assert res["reason_code"] == "BUDGET_EXCEEDED"
