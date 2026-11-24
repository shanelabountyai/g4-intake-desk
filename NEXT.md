# NEXT

## 2026-11-24 — pre-live portfolio pack, docs only (branch `portfolio-pack/2026-11-24`, draft PR, unmerged)

**Not deployed.** Nothing here is live; all numbers are on synthetic intakes and hand-written recorded router responses (D-6).

**Done** (one commit each, cut from `main` @ `ec70d30`): D-43 judgment calls · `docs/DEMO.md` (12 stops) · `docs/LINKEDIN_DRAFTS.md` (2 drafts on D-11 and D-3, drafted, unposted) · D-44 cost note · `docs/RELEASE_NOTES.md` ("Not deployed — portfolio pack 2026-11-24") · this section. Exec brief [G4·C Intake Desk in Brief](https://claude.ai/artifact/W2h3DJ2r1W8RoScuDsUZ8w) re-read and kept unchanged (accurate against today's files and gate; not shared).

**Verified, and how** (2026-11-24, `main` @ `ec70d30`, the steps in `.github/workflows/ci.yml`): `uv sync --frozen` exit 0 · `uv run ruff check .` exit 0, All checks passed! · `uv run mypy` exit 0, no issues in 12 source files · `uv run pytest` exit 0, 135 passed · `intake-desk eval --run-id eval` exit 0 and `diff -u docs/eval-report.md` exit 0 (identical) · `uv run intake-desk demo` exit 0. Every DEMO.md stop names its test or command; `intake-desk serve` was started once on 127.0.0.1:8040 (`/health` `sends_anything: false`, `/docs` 200, i25 webhook escalated) and stopped.

**Not verified:** no live model call; no stop clicked through by Shane; build cost and live running cost not measured (D-44); the API has no auth and never ran beyond localhost; model price ($2/$10 per MTok) not re-checked since 2026-11-21. No doc fix needed a code change.

**You:**
1. Review the draft PR (docs only) and merge it if you are happy; this run never merges.
2. Click through `docs/DEMO.md` yourself, starting with `uv sync --frozen && uv run intake-desk demo`.
3. Read the brief (link above); it is private and unshared.
4. Edit the two LinkedIn drafts in your own words before posting anything.
5. Decide whether to deploy. If yes, auth (BACKLOG "Later") and one live eval run come first.

## 2026-11-23 — owner decisions built (branch `build/g4c`, PR #1 still draft, unmerged)

Shane approved the review's recommendations. Built, each with tests first:
- `b230c79` **D-40** after hours, a book becomes a follow-up in code (after the guard and threshold, so escalations are never downgraded). **Measured change on the recorded fixtures:** routing accuracy 36/40 (90.0%) → **37/40 (92.5%)** (i20); router-only 35/40, escalation rate 16/40, missed emergencies 0 of 11, outbox 3/35/2 unchanged. `docs/eval-report.md` regenerated, README updated.
- `e414336` **D-41** Saturday slots 09:00 and 11:00 (Sunday closed). Eval unchanged.
- `1da4e44` **D-42** kept as they are: follow-up after a booking is still sent; guard false positives stay.

**Gate (local, head `1da4e44`):** ruff All checks passed! · mypy no issues in 12 files · pytest 135 passed · eval exit 0, report identical to the committed one · **CI:** push and pull_request runs on `1da4e44`: success.

**Still open:** D-2..D-5, D-11, D-13, D-15, D-16, D-25 provisional; router model; the 7 nits (D-39). Merge stays yours.

## 2026-11-22 — overnight review (branch `build/g4c`, PR #1 stays draft and unmerged)

**Review** (fresh review agent on PR #1's diff + PRD/backlog/decisions): **2 must-fix, 6 should-fix, 7 nits**, plus owner calls. Every README / NEXT / eval-report number was reproduced (36/40, 35/40, 16/40, 0 of 11 missed, i29/i33, sweep, outbox 3/35/2, 17 pending). G0 pinned by SHA and not copied; no secrets; no skipped tests; data synthetic.

**Fixed (8, each with a failing test first except the CI step; D-32..D-38):**
- `7b6e55b` M1 duplicate suppression from state: a second "book" after an earlier follow-up, or after an owner-approved booking, no longer books a second slot.
- `f384a6f` M2 any router exception, or a router call over 60 s, escalates (`router_invalid`) instead of losing the intake before the guard runs.
- `4d1fb0f` S2 emergency guard widened: ceiling leaks, "heat isn't working", heat/heater outages, cold 0–32 degrees outside, and the "101° " degree-sign regex bug.
- `3370fde` S3 final reasons logged in the G0 observability note for every route (AC1 on the webhook path).
- `ec6c4a3` S4 G0's run cost cap enforced before every live router call (it was reported, not enforced).
- `13cd9ae` S5 webhook with an already-processed intake id → 409, nothing booked or sent.
- `bb5c352` S6 no free synthetic slot → queued for the owner instead of an uncaught `LookupError`.
- `622658a` S1 CI now diffs `docs/eval-report.md` against a fresh run.

Eval report is byte-identical before and after every fix (no number moved). Tests 115 → 132.

**Left (nits, D-39):** recorded router keyed by id only (ignores text); approve not atomic and can re-book a held booking; naive `received_at` → 500; bad threshold fails per intake; import scan misses `subprocess`/`asyncio.open_connection`; `layer.py` uses G0's private `db._seed_*`.

**Decisions for Shane:**
1. After-hours clear requests: today the router decides (i20, Sunday, is booked if the router says book though D-13 labels it follow-up). Options: (a) keep router judgement, (b) force follow-up in code after hours. *Recommend (b)* if the PRD row "after hours and not urgent → follow up" is a rule, not a hint.
2. Follow-up after a booking for the same caller within 24 h (D-15 allows a different-route message). Options: allow / suppress. *Recommend allow* (new information).
3. Guard false positives ("no gas smell" escalates; the widened guard escalates more). *Recommend keep* (fails safe) until a live run shows queue load.
4. Saturday counts as business hours but has no slots (D-14/D-21). *Recommend* add Saturday 09:00/11:00 slots or drop Saturday hours.
5. Still provisional: D-2..D-5, D-11, D-13, D-15, D-16, D-25; router model Sonnet vs Haiku (BACKLOG "Later").

**Gate (local, 2026-11-22, branch head before this NEXT commit `5ec3171`):** `uv sync --frozen` ok · `uv run ruff check .` All checks passed! · `uv run mypy` Success: no issues found in 12 source files · `uv run pytest` 132 passed · `intake-desk eval --run-id eval` exit 0, report identical to `docs/eval-report.md` · `intake-desk demo` exit 0. **CI:** run 3 (push) and run 4 (pull_request) on `5ec3171`: success.

**Not verified:** still no live model call (`AgentSdkRouter`, the 60 s timeout and the cap check have never met a real SDK); mypy skips `claude_agent_sdk` imports and the live router is excluded from coverage, so its SDK usage is unchecked; the widened guard is regex on text the reviewer and this run wrote, not real calls; the FastAPI app still has no auth and was only exercised with TestClient.

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
