# ARCHITECTURE — Tiny CEDX Agent Fleet (Law Firms, Tier 2)

## 1. Agent Topology

```
                              ┌───────────────────────── ┐
                              │      ORCHESTRATOR        │
                              │  (agents/orchestrator.py)│
                              │  owns the run, retry/    │
                              │  escalate/kill loop,     │
                              │  budget + step ceiling   │
                              └────┬────────┬────────┬───┘
                     can_call:     │        │        │        can_call: []
                 ┌─────────────────┘        │        └─────────────────┐
                 ▼                          ▼                          ▼
          ┌─────────────┐             ┌─────────────┐            ┌─────────────┐
          │   ROUTER    │             │   WORKER    │            │  VERIFIER   │
          │ (router.py) │───tier───▶  │ (worker.py) │──draft───▶ │(verifier.py)│
          │ cheap/strong│             │ LLM Assembly│            │ rule-based  │
          │ rule-based, │             │ call, may   │            │ cross-check,│
          │ no LLM call │             │ abstain     │            │ can OVERRULE│
          │ can_call: []│             │ can_call: []│            │ can_call: []│
          └─────────────┘             └─────────────┘            └──────┬──────┘
                                                                          │ pass
                                                                          ▼
                                                                   ┌─────────────┐
                                                                   │  OPERATOR    │
                                                                   │(operator.py+ │
                                                                   │review/*)     │
                                                                   │approval FSM, │
                                                                   │amendment gate│
                                                                   │can_call: []  │
                                                                   └─────────────┘
```

The `agents` ist inside `out/audit.json` is generated directly from the five `Agent` dataclasses in `tinycedx/agents/base.py`. It is not a separate document that could drift out of sync with the code.

## 2. List, Typed Contracts, File Pointers

| Agent | Role | Models | `can_call` | Contract (in) | Contract (out) | File |
|---|---|---|---|---|---|---|
| Orchestrator | `orchestrator` | none (no LLM of its own) | `[router, worker, verifier, operator]` | `NormalizedRecord` + detector verdict | `RoutingDecision` / final result | `agents/orchestrator.py` |
| Router | `router` | none (rule based policy) | `[]` | `ROUTER_INPUT` | `ROUTER_OUTPUT` | `agents/router.py` |
| Worker | `worker` | `gpt-4o-mini`, `gpt-4o` | `[]` | `WORKER_INPUT` | `WORKER_OUTPUT` | `agents/worker.py` |
| Verifier | `verifier` | `rule-based-verifier-v1` (no LLM) | `[]` | `VERIFIER_INPUT` | `VERIFIER_OUTPUT` | `agents/verifier.py` |
| Operator | `operator` | none (policy) | `[]` | `OPERATOR_ACTION` | `ApprovalTrailEntry` | `agents/operator.py` + `review/operator_actions.py` |

Every contract in the table above is a JSON Schema object declared in `agents/contracts.py`. Every handoff between agents calls `validate()` against that schema. A mismatch raises `ContractError` instead of silently passing a malformed dictionary along. This is what "typed contracts, no free form string passing" means in practice: agents never exchange raw prose with each other, only these validated shapes.

**No god function.** `pipeline/run.py` calls exactly one entry point per record: `agents.orchestrator.process_record()`. That function is the only caller of `router.decide()`, `worker.run()`, and `verifier.verify()`. Each of those lives in its own module, can be imported on its own, and is exercised directly, without going through the Orchestrator, by the golden cases in `eval/run_eval.py` and by every probe in `cli/probes/`. None of them inline another agent's logic.

## 3. Why the Verifier Uses Rules Instead of Another LLM Call

The Verifier's job is to catch the Worker being wrong. An LLM checking another LLM shares the same failure modes as what it is checking: the kind of hallucination that fooled the Worker can just as easily fool an LLM verifier. Instead, `agents/verifier.py` checks the draft deterministically:

- Every passthrough field (`matter_id`, `responsible_attorney`, `deadline`, `matter_type`, `matter_value`) is compared against the exact source record. Any mismatch fails.
- Every key in `delivered_fields` is checked against an allow list. An invented field, such as a fabricated `risk_rating`, fails.
- Every digit sequence in the generated `summary` is checked against the source's own digits. A number that cannot be traced back to the record fails.

This catches 100% of these failure types, every time, for zero dollars. That is strictly stronger than an LLM judge verifier, and it is what actually produces the `AGENT_HALLUCINATION` catch. See DECISIONS.md for the full tradeoff discussion.

## 4. Where the Verifier Overrules the Worker

`agents/orchestrator.py::process_record()` runs the retry, escalate, and kill loop:

1. The Router picks a model tier, cheap or strong. It escalates to strong on a retry.
2. The Worker drafts an answer, or abstains.
3. If the Worker's output fails its own contract, that is the `AGENT_MALFORMED` path. It is retried once more; two malformed attempts in a row raise an exception and route the record to a human.
4. If the Worker abstains, the Verifier returns `verdict=needs_human`, which raises a `LOW_CONFIDENCE` exception and routes the record. The system never guesses.
5. Otherwise the Verifier checks the draft. If `verdict=fail`, the record is marked `overruled=true`. Both sides are logged in `agent_trace`: the Worker's span with `status=overruled`, and the Verifier's span with `status=rejected, verdict=fail` plus its list of mismatches. The record is retried at an escalated tier. Two Verifier rejections in a row raise an `AGENT_HALLUCINATION` exception, route the record to a human, and it is never delivered.
6. If the total number of attempts goes over `MAX_STEPS_PER_RECORD`, no matter why, the orchestrator kills the run with `AGENT_LOOP` and logs `status=killed`.

Here is a live example from the seeded agent failure demo, record `REC-018` (run `make trace ID=REC-018` to see it): on attempt one, using the cheap tier, the Worker invents a `risk_rating` field and reports the wrong `matter_value`. The Verifier rejects it. On attempt two, escalated to the strong tier, the Worker fixes the value but still invents `risk_rating`. The Verifier rejects it again, which raises `AGENT_HALLUCINATION` and routes it to a human. It is never delivered. Six spans are recorded in total: router, worker (overruled), verifier (rejected), router, worker (overruled), verifier (rejected).

## 5. Where the Budget & Router Decisions Live

**Router policy** (`agents/router.py::decide`): use the strong tier only when the record was flagged by the `LOW_CONFIDENCE` prefilter, or this is a retry after a Verifier rejection, or the amount is at or above the CASE_ID amendment threshold. Otherwise use the cheap tier. This is a pure function with no LLM call, so it is fully unit testable.

**Cost ceiling** (`budget/ledger.py::RecordLedger`): tracks the dollars spent per record. Before calling the Worker, the Orchestrator proactively downgrades from strong to cheap if strong would not fit the ceiling but cheap would (`config.estimate_cost`). If even cheap does not fit once the real cost is known, `RecordLedger.record_step` raises `BudgetExceeded`, and the Orchestrator routes the record with `BUDGET_EXCEEDED`. There is never a silent overspend. This is proven end to end by `make probe-budget`.

**Step ceiling and loop detection:** a simple attempt counter inside `process_record()`, compared against `MAX_STEPS_PER_RECORD`. This is separate from the cost ledger, and it is specifically what produces `AGENT_LOOP` (an agent that does not converge), as opposed to `BUDGET_EXCEEDED` (a dollar ceiling). This is exercised by `make probe-agent-failure`.

## 6. The Five Governed Stages, Mapped to Code

| Stage | Code | Notes |
|---|---|---|
| 1. Intake | `intake/parse_feed.py`, `parse_eml.py`, `parse_pdf.py`, `store.py` | Parses both formats. Persists every raw record to `out/state/intake.jsonl` before anything else runs; nothing is kept only in memory. |
| 2. Orchestration | `normalize/normalize.py`, `normalize/versions.py`, `detectors/registry.py` | Declarative normalization onto `schema/canonical_schema.v1.json` plus `field_mapping.v1.json`. Detects `SCHEMA_DRIFT` structurally and resolves `SUPERSEDED_VERSION`. Runs the ordered Class A rule pipeline; Class A records never reach the Worker. |
| 3. Assembly | `agents/worker.py`, `llm/client.py` | The Worker's LLM call, replayed deterministically from `/transcripts`, or live through `llm/live.py`. Every call's `transcript_hash` and `delivered_fields_hash` are recorded. |
| 4. Review | `review/state_machine.py`, `review/operator_actions.py`, `review/amendment.py` | The explicit `draft → in_review → changes_requested → approved → delivered/blocked` state machine, plus the CASE_ID amendment second approval gate. `deliver()` is the server side refusal point (`make probe-approval`). |
| 5. Delivery | `delivery/package.py`, `delivery/audit.py`, `delivery/exceptions_queue.py` | A branded package for delivered records only. A hash chained, append only `audit.json`. An exception queue dump. |

## 7. Observability

Every record that was not superseded carries an ordered `agent_trace`: one span per agent step, with `agent, model, prompt_version, tokens_in/out, cost_usd, latency_ms, retries, transcript_hash, status, verdict`. `make trace ID=<id>` (see `cli/trace.py`) prints this. `make replay ID=<id>` (see `cli/replay_cmd.py`) rebuilds the data lineage for that record: its source, any drift or supersede events, and which committed transcript backs the delivered content, all from the append only audit log alone.

## 8. CASE_ID Amendment

`review/amendment.py::compute_amendment(CASE_ID)` computes role R and threshold T using the Step 8 formula. Both are printed at startup as `AMENDMENT: role=<R> threshold=<T>` and recorded under `audit.json["amendment"]`. Any record whose normalized amount is at or above T needs a second `approval_trail` entry, tagged with role R (`operator_actions.approve(..., role=R)`), before `deliver()` will accept it. This is enforced the same way whether the amount comes from the dev seed, the held out seed, or a probe built synthetic record.
