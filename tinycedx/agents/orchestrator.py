from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tinycedx import config
from tinycedx.agents import router as router_agent
from tinycedx.agents import verifier as verifier_agent
from tinycedx.agents import worker as worker_agent
from tinycedx.agents.base import Agent, make_span
from tinycedx.budget.ledger import BudgetExceeded, RecordLedger

ORCHESTRATOR_AGENT = Agent(
    name="orchestrator", role="orchestrator", models=[],
    can_call=["router", "worker", "verifier", "operator"],
    prompt_version="orchestrator-v1",
)

WorkerFn = Callable[..., dict[str, Any]]


def process_record(
    *,
    record: dict[str, Any],
    low_confidence_flag: bool,
    amendment_threshold: float | None = None,
    max_cost_usd: float | None = None,
    max_steps: int | None = None,
    worker_fn: WorkerFn = worker_agent.run,
) -> dict[str, Any]:
    max_cost_usd = config.MAX_COST_USD_PER_RECORD if max_cost_usd is None else max_cost_usd
    max_steps = config.MAX_STEPS_PER_RECORD if max_steps is None else max_steps

    ledger = RecordLedger(max_cost_usd=max_cost_usd)
    trace: list[dict[str, Any]] = []
    prior_retry_count = 0
    repair_hint: str | None = None
    last_failure_type: str | None = None
    consecutive_same = 0
    attempt = 1

    def exception(reason_code: str, detail: str | None = None) -> dict[str, Any]:
        return {
            "status": "exception", "reason_code": reason_code, "reason_class": "A",
            "detail": detail, "delivered_fields": None, "delivered_fields_hash": None,
            "transcript_hash": None, "agent_trace": trace,
        }

    while True:
        if attempt > max_steps:
            trace.append(make_span(agent="orchestrator", status="killed", retries=attempt - 1))
            return exception("AGENT_LOOP", f"exceeded MAX_STEPS_PER_RECORD={max_steps} without resolving")

        route = router_agent.decide(
            record_id=record["id"], low_confidence_flag=low_confidence_flag,
            prior_retry_count=prior_retry_count, amount=record.get("amount"),
            amendment_threshold=amendment_threshold,
        )
        tier, model = route["model_tier"], route["model_name"]
        trace.append(make_span(agent="router", status="ok", prompt_version=router_agent.ROUTER_AGENT.prompt_version))

        if tier == "strong" and not ledger.would_fit(config.estimate_cost("strong")):
            if ledger.would_fit(config.estimate_cost("cheap")):
                tier, model = "cheap", config.MODEL_PRICING_PER_1K["cheap"]["model"]
            else:
                trace.append(make_span(agent="orchestrator", status="routed", retries=attempt - 1))
                return exception("BUDGET_EXCEEDED", "even the cheap tier would exceed MAX_COST_USD_PER_RECORD")

        worker_result = worker_fn(record=record, model_tier=tier, model_name=model,
                                   attempt=attempt, repair_hint=repair_hint)

        try:
            ledger.record_step(worker_result["cost_usd"])
        except BudgetExceeded as e:
            trace.append(make_span(
                agent="worker", status="routed", model=worker_result["model"],
                prompt_version=worker_result["prompt_version"], tokens_in=worker_result["tokens_in"],
                tokens_out=worker_result["tokens_out"], cost_usd=worker_result["cost_usd"],
                latency_ms=worker_result["latency_ms"], transcript_hash=worker_result["transcript_hash"],
                retries=attempt - 1,
            ))
            return exception("BUDGET_EXCEEDED", e.detail)

        if worker_result["malformed"]:
            trace.append(make_span(
                agent="worker", status="retried", model=worker_result["model"],
                prompt_version=worker_result["prompt_version"], tokens_in=worker_result["tokens_in"],
                tokens_out=worker_result["tokens_out"], cost_usd=worker_result["cost_usd"],
                latency_ms=worker_result["latency_ms"], transcript_hash=worker_result["transcript_hash"],
                retries=attempt - 1,
            ))
            last_failure_type, consecutive_same = (
                ("malformed", consecutive_same + 1) if last_failure_type == "malformed" else ("malformed", 1)
            )
            if consecutive_same >= 2:
                trace.append(make_span(agent="verifier", status="rejected", verdict="needs_human"))
                return exception("AGENT_MALFORMED", "worker output failed contract validation on bounded retry")
            prior_retry_count += 1
            attempt += 1
            repair_hint = "previous response was not valid JSON matching the WorkerOutput contract; return well-formed JSON."
            continue

        response = worker_result["response"]
        verdict = verifier_agent.verify(source=record, worker_output=response)

        worker_status = "abstained" if response.get("abstain") else ("ok" if verdict["verdict"] == "pass" else "overruled")
        trace.append(make_span(
            agent="worker", status=worker_status, model=worker_result["model"],
            prompt_version=worker_result["prompt_version"], tokens_in=worker_result["tokens_in"],
            tokens_out=worker_result["tokens_out"], cost_usd=worker_result["cost_usd"],
            latency_ms=worker_result["latency_ms"], transcript_hash=worker_result["transcript_hash"],
            retries=attempt - 1,
        ))
        trace.append(make_span(
            agent="verifier", status=("ok" if verdict["verdict"] == "pass" else "rejected"),
            verdict=verdict["verdict"], retries=attempt - 1,
        ))

        if verdict["verdict"] == "needs_human":
            return exception("LOW_CONFIDENCE", verdict.get("notes"))

        if verdict["verdict"] == "pass":
            return {
                "status": "assembled", "reason_code": None, "reason_class": None, "detail": None,
                "delivered_fields": response["delivered_fields"],
                "transcript_hash": worker_result["transcript_hash"],
                "model_tier": tier, "agent_trace": trace,
            }

        last_failure_type, consecutive_same = (
            ("hallucination", consecutive_same + 1) if last_failure_type == "hallucination" else ("hallucination", 1)
        )
        if consecutive_same >= 2:
            return exception("AGENT_HALLUCINATION", "; ".join(verdict["mismatches"]))
        prior_retry_count += 1
        attempt += 1
        repair_hint = "Verifier rejected the previous draft: " + "; ".join(verdict["mismatches"])
