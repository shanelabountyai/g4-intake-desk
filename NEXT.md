# NEXT

State (2026-11-04): PRD only (`docs/prd.md`, v0.1). No code, no git repo yet.

Next: owner creates the repo if wanted, then pastes `KICKOFF.md` into Claude Code. The session plans first and stops for review.

Order: G1 -> G0 (shared layer) -> G2 -> G3 -> G4 -> G5 (see ../README.md). If G0 isn't built when this starts, use stubs with the same contract shape.

## 2026-11-21 — G4·C built unattended (branch `build/g4c`, draft PR)

**State:** G4·C (Python 3.12 + Claude Agent SDK + FastAPI) is built end to end on the recorded router path, attached to G0 at `6f5e605`. G4·B (n8n) was not built (D-1; owner's hand build). Nothing is merged; nothing is sent anywhere; no API key was used and no model was called ($0).

**Done** (backlog T0–T11, `docs/BACKLOG.md`): decisions D-1..D-31; safety invariants with tests first; 40 labeled synthetic intakes (36 HVAC, 4 wrong-trade; 11 emergencies, vague, duplicates, price shoppers, consent edge cases) with hand-written recorded router responses; router contract `schemas/router_v1.json`; G0 adapter (consent, brand v1 + `g4-followup-1`, evaluation rubric `g4_route_v1`, observability, measurement); desk pipeline (book on a synthetic calendar, templated follow-up, escalation queue with owner approve/reject, duplicates); FastAPI webhooks; `intake-desk demo|eval|route|queue|serve`; `docs/eval-report.md`; CI workflow; README.

**Gate (fresh clone of `build/g4c`, 2026-11-21):** `uv sync --frozen` ok · `ruff check .` all checks passed · `mypy` no issues in 12 source files · `pytest` 115 passed · `intake-desk eval` exit 0: accuracy 36/40 (90.0%), router-only 35/40 (87.5%), escalation rate 16/40 (40.0%), **missed emergencies 0 of 11** (recorded router alone missed 2, caught by guard/threshold), booked below threshold 0, 0 tokens / $0 — on hand-written recorded responses, not a model. CI result: see the PR.

**Model / SDK checked 2026-11-21:** Anthropic models overview lists `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-fable-5-2`; router set to `claude-sonnet-5-5` (G0 price table $2/$10 per MTok matches). `claude-agent-sdk` 0.2.187 on PyPI (lock pins 0.2.187).

**Provisional decisions for Shane** (`docs/DECISIONS.md`): D-2 HVAC · D-3 threshold 0.7 · D-4 text/forms only · D-5 GHL narrative only · D-11 deterministic emergency guard alongside the router · D-13 labeling rules (after-hours clear request = follow-up, per the PRD) · D-15 duplicates · D-16/D-25 consent-blocked messages and held bookings.

**Not verified:**
- No live model call: `AgentSdkRouter` is implemented but has never run; real router accuracy, escalation rate, tokens and cost are unmeasured.
- The recorded responses and labels are hand-made by this run; a real router will disagree in other places.
- The emergency guard is keyword/regex based; it is tuned on these 40 texts plus the unit examples, not on real calls.
- FastAPI app tested with TestClient only; never served beyond a test process, no auth.
- G4 seeds go into G0's store through G0's loader, not a tool (same exception as G2/G3).

**Next / You:**
1. Review the draft PR and the provisional decisions above; check the labels in `fixtures/intakes.json` (edit `fixtures/make_fixtures.py`, rerun it, then `uv run intake-desk eval`).
2. Build G4·B in n8n by hand: form webhook + missed-call-text trigger → router AI Agent → Switch → book / follow-up / escalate sub-workflows, Wait node on escalate; use the same 40 fixtures and `config/business.json`.
3. For real numbers: put `ANTHROPIC_API_KEY` in a gitignored `.env`, export it, re-check prices on Anthropic's pricing page, then `uv run intake-desk eval --live --record fixtures/recorded.live.json --report docs/eval-report-live.md` (40 router calls; G0's $10 run cap applies). Compare with the recorded report.
4. Merge the PR yourself when satisfied (this run never merges).
