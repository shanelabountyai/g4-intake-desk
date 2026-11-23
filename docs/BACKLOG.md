# Backlog — G4·C Intake Desk (code version)

G4·B (n8n) is not in this backlog: the owner builds it by hand (D-1). Each task is one sitting, ends with a commit on `build/g4c`, and carries acceptance criteria taken from the PRD (`docs/prd.md`, AC1–AC5) or from CLAUDE.md. All tasks were built in the 2026-11-21 unattended run.

| # | Task | Acceptance | Status |
|---|---|---|---|
| T0 | DECISIONS (D-1…D-24) and this backlog, before code | Every open PRD decision recorded with the option taken | done |
| T1 | Project skeleton: `pyproject.toml` (G0 git pin, claude-agent-sdk, FastAPI), ruff, mypy strict, `.gitignore`, `.env.example` | `uv sync`, `ruff check`, `mypy` clean on an empty package | done |
| T2 | **Safety invariants with tests first**: no network/SMS/SMTP/calendar client importable from the package; the outbox is the only sink and every row is `logged_not_sent`/`blocked_*`; the emergency guard; the threshold rule; live router refuses without a key | `tests/test_safety.py` green before any route action exists (CLAUDE.md, AC2, AC4) | done |
| T3 | Synthetic data: 40 labeled intakes (HVAC-weighted; after-hours emergencies, vague, duplicates, wrong trade), synthetic contacts with consent flags, business hours, hand-written recorded router responses, generator script | No real names/numbers/businesses (555-01xx, `@example.com`, "Synthetic Caller NN"); every intake has a label and a recording (test) | done |
| T4 | Router contract (`schemas/router_v1.json`), `parse_router`, `RecordedRouter`, `AgentSdkRouter` (never run), prompt with pointers only | Malformed outputs rejected (test); prompt carries no G0 rule text (test) | done |
| T5 | G0 adapter: health first, g4 seeds through G0's loader, consent, brand (v1 + g4-followup-1), evaluation, observability, measurement | Seeds namespaced `g4` only; degraded layer stops the run (tests) | done |
| T6 | Desk pipeline: decide final route (D-12), book on the synthetic calendar, templated follow-up, escalation queue, duplicates, consent/brand gates, owner approve/reject | AC1 (route + reasons logged), AC2, AC3 (never auto-booked below threshold), AC4 (tests) | done |
| T7 | FastAPI: `POST /webhooks/form`, `POST /webhooks/missed-call`, `GET /queue`, `POST /queue/{id}/approve`, `POST /queue/{id}/reject`, `GET /outbox`, `GET /health` | TestClient tests for each endpoint; outbound only via the outbox | done |
| T8 | Report: routing accuracy, router accuracy, escalation rate, missed emergencies (final and router-only), per-route confusion, threshold sweep → `docs/eval-report.md` | AC5; numbers labelled as describing recorded fixtures | done |
| T9 | Acceptance tests named `test_ac1_*`…`test_ac5_*` | One or more per AC | done |
| T10 | CI workflow (lint, typecheck, tests, report) like G3's | Runs on push and pull_request | done |
| T11 | README (at-a-glance block, how it works, demo script), NEXT.md hand-off | No invented numbers; demo is one command | done |

## Owner hand steps (not done by this run)

1. Review the provisional decisions (D-2…D-5, D-11, D-13, D-15, D-16) and the labels in `fixtures/intakes.json`.
2. Build G4·B in n8n by hand (form webhook + missed-call trigger → router AI Agent → Switch → book / follow up / escalate sub-workflows, Wait node on escalate), against the same fixtures.
3. For a live run: add `ANTHROPIC_API_KEY` to a local, gitignored `.env`, re-confirm prices, run `intake-desk eval --live --record fixtures/recorded.live.json` and compare with the recorded numbers.
4. Merge the PR when satisfied (this run never merges).

## Later (not in v1)

- Live router comparison Sonnet vs Haiku on the same labeled set (cost vs accuracy vs escalation rate).
- Owner notification through a real channel (needs explicit go; outbox stays the sink until then).
- Auth on the FastAPI app before it is ever exposed beyond localhost.
- GHL tie-in beyond the narrative (D-5).
