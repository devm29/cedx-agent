# Tiny CEDX Agent Fleet — Law Firms

## 1. Industry & Scope

**Industry:** Law Firms, Tier 2
**CASE_ID:** `CEDX-82C0A1`


The seed data models generic work request records. In this project they are treated as law firm matter operations:

- `amount` → matter value or retainer
- `owner` → responsible attorney
- `deadline` → filing or engagement deadline
- `category` → `ONBOARDING` (new matter or client onboarding), `RENEWAL` (engagement letter renewal), `REVIEW` (matter or conflict review), `REPORT` (billing status report), `INTAKE` (new matter intake)
- `notes` → client or partner instructions (also the natural home for the injection attempt record)


## 2. Agent topology

There are five agents. The brief only requires three roles at minimum (Orchestrator, Worker, Verifier); this fleet also adds a Router and an Operator. The full diagram, contracts, and file pointers are in **ARCHITECTURE.md**.

| Agent | Can call | File |
|---|---|---|
| Orchestrator | router, worker, verifier, operator | `tinycedx/agents/orchestrator.py` |
| Router | none | `tinycedx/agents/router.py` |
| Worker | none | `tinycedx/agents/worker.py` |
| Verifier | none | `tinycedx/agents/verifier.py` |
| Operator | none | `tinycedx/agents/operator.py`, `tinycedx/review/operator_actions.py` |

Every agent's input and output is a typed contract, declared in `tinycedx/agents/contracts.py` and checked on every handoff.

## 3. How to Run

```
make demo      # runs the full fleet with REPLAY_LLM=true on SEED_DIR
make verify    # runs the provided verify_audit.py gate against out/audit.json
make trace ID=REC-018     # prints the full agent decision path for one record
make replay ID=REC-016    # rebuilds the data lineage for one record from the audit log
make eval      # runs the golden test cases plus an LLM judge for each agent
```

Or run everything with one command: `docker compose up`. This is offline by default, and `SEED_DIR` can be swapped to point at the held out seed with an environment variable.

To use a real LLM instead of replayed transcripts:
`REPLAY_LLM=false LLM_API_KEY=... LLM_MODEL=gpt-4o-mini make demo`

## 4. Controls

All required probe commands are wired up and pass.

| Command | What it proves |
|---|---|
| `make probe-approval` | A record that was never approved is refused and logged. A high value record missing its amendment role approval is also refused. A fully approved record is delivered. |
| `make probe-agent-failure` | A hallucinated, malformed, or looping worker output is always caught (`AGENT_HALLUCINATION`, `AGENT_MALFORMED`, `AGENT_LOOP`) and never delivered. |
| `make probe-budget` | A record that would go over the cost ceiling is downgraded to the cheap tier if that fits, or raises `BUDGET_EXCEEDED` if it does not. |
| `make probe-append-only` | There is no update or delete method on `AuditLog`. If a past event is hand edited or deleted, the hash chain independently detects it. |
| `make probe-idempotency` | Running demo twice produces the exact same records and events. No duplicates. |

## 5. Planted Problem Handling (Data + Agent Layer)

**Data layer** (see `tinycedx/detectors/`, run in order by `registry.py`):

- `STALE`
- `MISSING_INPUT`
- `OUTLIER` (a robust median and MAD statistic)
- `INJECTION_BLOCKED` (a family of patterns)
- `LOW_CONFIDENCE` (a prefilter plus the worker's own ability to abstain)
- `UNVERIFIED_ANOMALY` (the catch all)
- `SCHEMA_DRIFT` (detected structurally, see `normalize.py`)
- `SUPERSEDED_VERSION` (see `versions.py`)

**Agent layer** (see `tinycedx/agents/verifier.py` and `orchestrator.py`):

- `AGENT_HALLUCINATION`: the Verifier's cross check catches a fabricated field or value. The record is retried, and if it still fails, it is routed to a human.
- `AGENT_MALFORMED`: the worker's output fails its own contract. It is retried a bounded number of times, then it abstains.
- `AGENT_LOOP`: the record hits the step ceiling and the run is killed.
- `BUDGET_EXCEEDED`: the record would cost too much, so it is downgraded or routed.

On the dev seed, running `make demo` delivers 14 of 23 records. Eight become exceptions (`STALE`, `MISSING_INPUT`, `OUTLIER`, `INJECTION_BLOCKED`, two `LOW_CONFIDENCE`, `UNVERIFIED_ANOMALY`, and the seeded `AGENT_HALLUCINATION` case on `REC-018`). One record is superseded (`REC-017` version 1, replaced by version 2). No record with a Class A code or an agent failure code ever reaches delivery, enforced by `verify_audit.py` and by `make probe-agent-failure`.

## 6. Generalization

Every detector works from structure, not from specific seed values. See the "Thresholds, and why they generalize" section of DECISIONS.md for the reasoning behind each one.

As a concrete test: a synthetic record with a field rename that was never seen before (`TotalFeeXYZ`, not present in `field_mapping.v1.json`) still resolves correctly to `amount`, because the detector infers the rename structurally instead of relying on a lookup table.

## 7. LLM / Agent Contract & Eval

By default (`REPLAY_LLM=true`), every agent's LLM call replays a committed transcript from `/transcripts`. Each transcript is hash verified and tagged with the agent that made the call. This includes the planted low confidence abstain cases (`REC-015`, `REC-021`) and the seeded agent failure hallucination (`REC-018`, both attempts).

Set `REPLAY_LLM=false` to call a real model instead. This reads `LLM_API_KEY`, `LLM_MODEL`, and `LLM_BASE_URL`, and supports `gpt-4o-mini`, `claude-3-5-haiku`, and `gemini-1.5-flash` (see `tinycedx/llm/live.py`). Live calls write their own transcript, so the real path stays just as traceable as replay.

`make eval` runs 14 golden cases across all 5 agents, each through the real pipeline plus an LLM judge pass. Current result: 14 out of 14 correct.

## 8. Cost & Scale

On the dev seed (23 records): total cost $0.004962, average $0.000216 per record, p95 latency 610 ms. The router sent 15 of 18 worker calls (83%) to the cheap tier.

Projected at 10,000 records a day: about $2.16 a day in LLM cost. See DECISIONS.md for what actually breaks first at that scale — the single audit file rebuild and sequential processing, not the LLM cost.

## 9. AI Usage / Real vs Faked

This was built with AI assistance (Claude Code), as the brief expects. Every claim here can be checked independently, not just taken on faith:

- `make verify` derives `delivered_fields_hash` and `transcript_hash` again from the committed transcripts, and fails if they do not match a real, hash verified worker response.
- The Verifier's rejection of the seeded hallucination is visible in `make trace ID=REC-018`.
- The structural schema drift generalization is shown on a synthetic, never seen rename.
- The agent failure and budget probes use dependency injected worker fixtures instead of pre baked transcripts, so they are not just replaying a fixed answer (see `tinycedx/eval/scenarios.py`).

## 10. Tradeoffs & Next Week

See DECISIONS.md for the full list of what was deliberately left out and what breaks first at scale. Given another week, the next priorities would be:

- A real, durable audit store, replacing the single file rebuild.
- Parallel per record processing, bounded by the budget ledger.
- A genuinely interactive CLI review surface. Today it is exercised directly through `review/operator_actions.py` plus the demo's auto policy; a thin `click` or `argparse` wrapper for a human operator is the natural next layer.
- A larger golden case set, with more held out style adversarial examples per detector.
