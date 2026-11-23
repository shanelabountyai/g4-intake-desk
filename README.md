# g4-intake-desk — Home-Services Intake Desk (G4·C)

Build log G4, Agentic AI track, graphic row "Decisions". A missed call or a web form arrives at an HVAC business; a **router agent** decides what happens next — **book** it, **follow up**, or **escalate** to a person — and returns `{route, confidence, reasons}`. Anything below the confidence threshold goes to an **escalation queue** regardless of route, and a deterministic **emergency guard** escalates gas, CO, no-heat, active-leak and similar calls even when the router gets them wrong. Every outbound text, email and booking is **logged, never sent**.

This is a portfolio sample build on **synthetic data** and **hand-written recorded router responses** (no API key, no live model call, $0; D-6). **The numbers below describe those recorded fixtures, not a model.** Only the code version is built here; the n8n version (G4·B) is the owner's hand build (D-1).

Spec: `docs/prd.md` · decisions: `docs/DECISIONS.md` · backlog: `docs/BACKLOG.md` · eval: `docs/eval-report.md` · state and hand steps: `NEXT.md`.

## At a glance

- **Who it's for.** An owner-operated HVAC shop (or the agency that runs its front desk) that loses jobs to missed calls and after-hours forms, and cannot afford a bot that confidently books a gas leak for next Tuesday.
- **The journey.** A caller hangs up or a form lands → the transcript/form hits a webhook → the router picks a route with reasons → book: a slot on the calendar and a confirmation draft; follow up: a templated text or email asking for what is missing; escalate: an alert to the owner or on-call tech and a queue item that waits for **approve** or **reject**. Consent and tone are checked before any customer message; the message is written to the outbox, not sent.
- **Why they'd come back in week three.** The queue is where the judgement calls collect, so the owner stops reading every voicemail and only reads the ones the desk would not decide on its own; the report says how often that happens at each threshold, so the owner can move the threshold on evidence instead of a feeling.
- **Design intent.** An agent that knows when not to decide. Zero missed emergencies is the bar, paid for with extra escalations. Rules live in one place each: emergency guard and threshold in `safety.py`, consent and tone in the shared layer (G0), never in the prompt.
- **Controls & cuts.** Synthetic data only; outbox is the only sink (no network/SMS/mail/calendar client in the package — a test scans the imports); live router needs a key and was never run; no voice (transcript text only, D-4); GoHighLevel appears in the narrative only (D-5); the API is localhost-only with no auth; G4·B (n8n) not built here.

**GoHighLevel, narrative only (D-5):** the same three routes map onto a GHL home-services setup — missed-call text-back and form triggers in, a pipeline stage per route, an internal notification plus a manual-approval step for escalations. This repo does not call GHL or mimic its API; it shows the decision logic a GHL workflow would sit on.

## Demo (one command)

```bash
uv sync --frozen && uv run intake-desk demo
```

On a throwaway store it walks seven fixture intakes in arrival order — a clean booking, its duplicate form (nothing new booked), a vague unknown caller below the threshold (queued), a furnace "bang + burning smell" the recorded router wanted to book (the emergency guard escalates it), an after-hours no-heat emergency (on-call alert), a price shopper (templated follow-up), and a customer without messaging consent (slot held, confirmation blocked, owner asked to call) — then rejects one queue item and approves another, prints the outbox (every row logged, none sent) and runs the full 40-intake eval.

## How it works

```
POST /webhooks/form | /webhooks/missed-call        (or: intake-desk route --case iNN / eval / demo)
  │
  ├─ G0 health first (degraded layer or missing g4 seed → stop)
  ├─ contact lookup: caller ID / form email → g4 synthetic contact (seeded into G0)
  ├─ router (RecordedRouter | AgentSdkRouter) ─► parse_router (router_v1) ─ invalid ─► escalate, confidence 0
  ├─ decide_final:  emergency guard → escalate  ·  confidence < threshold → escalate  ·  after-hours book → follow up (D-40)  ·  else router route
  ├─ G0 observability (route, confidence, tokens, cost, run total, $10 cap) · G0 measurement intake.routed
  └─ book       first free synthetic slot → confirmation → G0 audience.consent → G0 brand.policy (v1 + g4-followup-1) → outbox
     follow_up  template → consent → brand → outbox                      (brand failure → queue)
     escalate   queue (pending approve/reject) + internal owner/on-call alert → outbox
     duplicate of a book/follow-up within 24 h → nothing new booked or sent; a repeat emergency is queued again
```

| File | What |
|---|---|
| `src/intake_desk/safety.py` | The emergency guard, the fail-closed decision order, the forbidden-import list. Landed with its tests first. |
| `src/intake_desk/models.py` | `Intake`, `RouterDecision` (router_v1) and `parse_router`, `FinalDecision`, `OutboundRecord`, `Outcome`. |
| `src/intake_desk/router.py` | `RecordedRouter` (used), `AgentSdkRouter` (Claude Agent SDK `query`, structured output, no tools; implemented, never run), `RecordingRouter`. Prompt = pointers only (test). |
| `src/intake_desk/layer.py` | The one G0 adapter (in-process, pinned SHA). Seeds g4 contacts, brand policy `g4-followup-1` and rubric `g4_route_v1` through G0's loader, `g4`-namespaced only (D-9). |
| `src/intake_desk/desk.py` | The pipeline, the three actions, duplicates, owner approve/reject. |
| `src/intake_desk/store.py` | Desk SQLite: outbox (the only sink; no "sent" status exists), synthetic calendar, escalation queue. |
| `src/intake_desk/templates.py` | Fixed follow-up, confirmation and owner-alert templates. |
| `src/intake_desk/app.py` | FastAPI webhooks, queue approve/reject, outbox, bookings, health. |
| `src/intake_desk/report.py`, `cli.py` | `intake-desk eval` → accuracy, escalation rate, missed emergencies, confusion, threshold sweep. |
| `fixtures/` | 40 labeled synthetic intakes, hand-written recorded router responses, and the generator script. |
| `contacts/`, `brand/`, `rubrics/`, `config/` | The three G0 seeds and the synthetic business profile (hours, on-call, slots). |
| `schemas/router_v1.json` | The published router contract (equals the model; test). |

## Shared layer (G0)

Pinned to `shanelabountyai/g0-shared-layer@6f5e605` like G3·C (D-8). `audience.consent` before every customer message (fails closed: unknown caller, opted out, no flag); `brand.policy` v1 **and** `g4-followup-1` on every customer message (no price figures, no guarantees or arrival promises, texts ≤ 60 words, plus G0's own never-use list); `evaluation` scores every labeled intake against rubric `g4_route_v1` and the report's accuracy is read from those results; `observability` logs every router call with route, confidence and cost; `measurement` records `intake.routed` and owner decisions. G0's v1 contracts have no register tool, so the three g4 seeds go in through G0's own seed loader (the same documented exception G2 and G3 make; D-9).

## Acceptance (PRD) — where each is proved

| AC | Test |
|---|---|
| 1 Every intake gets a route with logged reasons | `test_ac1_every_intake_gets_a_route_with_logged_reasons` (40/40 routed, reasons non-empty, one G0 observability row and one `intake.routed` event each) |
| 2 Every labeled emergency is escalated | `test_ac2_every_labeled_emergency_is_escalated` (11/11, at every sweep threshold), `test_ac2_guard_catches_router_misses_at_any_threshold` (recorded router misses `i29`, `i33`; final route escalates at thresholds 0.0–1.0), `test_guard_alone_flags_every_labeled_emergency` |
| 3 Low confidence escalated, never auto-booked | `test_ac3_low_confidence_is_escalated_never_auto_booked` (thresholds 0.00–1.00 in 0.05 steps), `test_decision_order_fails_closed` (0.69 → queue, 0.70 → not below) |
| 4 No real message sent; all outbound logged | `test_ac4_no_real_message_sent_all_outbound_logged`, `test_no_module_imports_a_network_mail_sms_or_calendar_client`, `test_outbox_cannot_hold_a_sent_status`, `test_calendar_is_synthetic_only` |
| 5 Accuracy and escalation rate reported, threshold tunable | `test_ac5_accuracy_and_escalation_rate_reported_with_a_tunable_threshold` (`--threshold`, `G4_THRESHOLD`, sweep 0.5–0.9) |

## Results on the recorded fixtures (threshold 0.7)

From `docs/eval-report.md`. **Hand-written recorded router responses, not a model**; several are deliberately wrong or unsure so the guard and threshold have work to do.

| | |
|---|---|
| Routing accuracy (final route = label) | 37/40 (92.5%) |
| Router-only accuracy | 35/40 (87.5%) |
| Escalation rate | 16/40 (40.0%) |
| Missed labeled emergencies | **0 of 11** (the recorded router alone missed 2; the guard and threshold caught both) |
| Booked below threshold | 0 |
| Live model calls / cost | 0 / $0.00 |

The sweep in the report shows the trade: raising the threshold to 0.9 escalates far more and lowers accuracy; lowering it to 0.5 lets one angry customer (`i36`, recorded at 0.68) through as a follow-up. Missed emergencies stay at 0 across the sweep because the guard does not depend on the threshold.

## Running it

```bash
uv sync --frozen
uv run ruff check . && uv run mypy && uv run pytest
uv run intake-desk demo                                  # the walkthrough above
uv run intake-desk eval                                  # all 40 → docs/eval-report.md (exit 3 if an emergency is missed)
uv run intake-desk eval --threshold 0.8 --report out/r08.md
uv run intake-desk route --case i29                      # one fixture intake
uv run intake-desk queue list --status pending --run-id manual
uv run intake-desk serve                                 # http://127.0.0.1:8040/docs (recorded router, localhost only)
```

Run state lives under `out/<run_id>/` (G0 SQLite, desk SQLite, `outbox.jsonl`); `--g0-db` points at another G0 file. `--live` needs `ANTHROPIC_API_KEY` and was not used in this build; `--record` saves live answers in the recorded file's shape.
