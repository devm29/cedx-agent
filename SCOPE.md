# SCOPE — push this during the live call (tracer checkpoint)

- **CASE_ID (assigned live):** CEDX-82C0A1
- **Industry chosen (from cedxsystems.com/workflows):** Law Firms
- **Tier:** Tier 2
- **Stack / language:** Python, stdlib-heavy (+ `jsonschema`, `pypdf`)

## Amendment (compute from your CASE_ID)
```
H = sha256(CASE_ID)
role R      = ["risk_officer","legal_counsel","compliance","finance_controller"][ int(H[0],16) % 4 ]
threshold T = 10000 + (int(H[1:3],16) % 50) * 1000
```
- **My role R (for CASE_ID=CEDX-82C0A1):** finance_controller
- **My threshold T (for CASE_ID=CEDX-82C0A1):** 42000

## What I will build (the 5 governed stages)
- [ ] Sources/Intake (parse feed.json + inbox PDF/email) — `tinycedx/intake/`
- [ ] Orchestration (declarative normalize + exception queue, all reason codes) — `tinycedx/normalize/`, `tinycedx/detectors/`
- [ ] Assembly (LLM structured output + abstain path) — `tinycedx/agents/worker.py`
- [ ] Review (operator surface + approval state machine + my CASE_ID amendment) — `tinycedx/review/`
- [ ] Delivery (branded package + append-only audit + replay) — `tinycedx/delivery/`

## What I will deliberately NOT build (and why)
- An auto resolver for exception queue items — see DECISIONS.md, "What I did NOT automate."
- An LLM based Verifier — deterministic cross check is stronger and free; see ARCHITECTURE.md.
- Incremental checkpoint/resume across runs — full rebuild per run is idempotent and
  simpler at this scale; see DECISIONS.md, "How provenance survives a re run."
