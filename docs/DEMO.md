# Demo walk-through — G4·C Intake Desk

**Not deployed.** Everything below runs on one machine, on 40 synthetic intakes and **hand-written recorded router responses** (not a model, D-6). Nothing is sent to anyone: every text, email, alert and booking is a row in a local outbox or a synthetic calendar (D-18).

Checked on 2026-11-24 against `main` @ `ec70d30`. "Verified by" names the test or command this pack's run used; **none of these stops has been clicked through by Shane yet.**

## At a glance

- **Who it is for.** An owner-run HVAC shop, or the agency running its front desk, that loses jobs to missed calls and after-hours forms and cannot risk a bot booking a gas leak for next week.
- **What was decided.** A deterministic emergency guard in code escalates gas, CO, burning smell, no heat and active leaks whatever the router says (D-11, widened in D-34). Below confidence 0.7 the intake goes to a person (D-3, D-12). After hours a booking becomes a follow-up (D-40). The outbox is the only sink (D-18). Consent and tone come from the shared layer G0, not the prompt (D-16, D-17).
- **What was left out.** Voice (transcript text only, D-4). GoHighLevel beyond the narrative (D-5). The n8n version G4·B (owner's hand build, D-1). Any live model call (D-6). Auth and hosting: localhost only (D-29).
- **The complete journey.** A missed-call transcript or form hits a webhook → the router returns `{route, confidence, reasons}` → guard and threshold decide the final route → **book**: a synthetic slot and a confirmation draft; **follow up**: a templated text or email asking for what is missing; **escalate**: an owner or on-call alert plus a queue item waiting for approve or reject. Consent and brand are checked before any customer message; the message is logged, not sent.
- **Why someone would come back in week three.** The queue holds only the calls the desk would not decide alone, so the owner stops reading every voicemail. The eval report shows the escalation rate at each threshold (35.0% at 0.5 to 77.5% at 0.9 on the recorded fixtures), so the threshold moves on evidence.
- **The design.** An agent that knows when not to decide: zero missed emergencies is the bar, paid for with extra escalations (16 of 40 at 0.7 on the recorded fixtures). Each rule lives in one place: guard and threshold in `safety.py`, consent and tone in G0, never in the prompt.

## Start it

```bash
uv sync --frozen
uv run intake-desk demo
```

Needs Python 3.12 and `uv`. No API key, no `.env`, no network after install. Verified by: both commands, exit 0, on 2026-11-24; `tests/test_cli.py::test_demo_runs_end_to_end`.

## Stops

The demo prints stops 1–8 in this order on a throwaway store.

1. **Clean booking (i01).** Furnace tune-up in business hours → router `book (0.93)` → a synthetic booking and a confirmation `logged_not_sent` after consent and brand pass.
   Verified by `tests/test_desk.py::test_book_creates_synthetic_booking_and_logged_confirmation` and the demo output.
2. **Duplicate form (i38).** Same caller, same request within 24 h → nothing new booked or sent (`suppressed_duplicate`, D-15/D-32).
   Verified by `tests/test_desk.py::test_duplicates_create_nothing_new_but_emergencies_requeue`.
3. **Vague unknown caller (i12).** "Call me back" → router `follow_up (0.45)` → below 0.70, so **escalate** to the queue with an internal owner alert.
   Verified by `tests/test_acceptance.py::test_ac3_low_confidence_is_escalated_never_auto_booked` and the demo output.
4. **The router gets an emergency wrong (i29).** Furnace bang + burning smell → router `book (0.76)` → the emergency guard overrides to **escalate** (`burning_or_smoke`), on-call alert after hours.
   Verified by `tests/test_acceptance.py::test_ac2_guard_catches_router_misses_at_any_threshold`.
5. **After-hours no-heat emergency (i24).** 8 °F outside, newborn → **escalate**, alert to the on-call tech, queue item pending.
   Verified by `tests/test_desk.py::test_emergency_goes_to_queue_with_on_call_alert_after_hours`.
6. **Price shopper (i11).** → **follow up** with the price-inquiry template; no price figure in the text (brand rule `g4-followup-1`).
   Verified by `tests/test_desk.py::test_follow_up_templates[i11-price_inquiry]`.
7. **No messaging consent (i40).** Clear booking → slot held, confirmation `blocked_consent`, queue item asks the owner to confirm by phone (D-25).
   Verified by `tests/test_desk.py::test_booking_with_blocked_confirmation_goes_to_owner`.
8. **Owner decisions.** Reject i12 (closed, nothing sent); approve i24 as `owner_handled` (nothing sent to the customer). Then the outbox prints: seven rows, none sent.
   Verified by `tests/test_desk.py::test_reject_closes_with_nothing_sent`, `tests/test_desk.py::test_approve_emergency_default_sends_nothing_to_customer`, `tests/test_acceptance.py::test_ac4_no_real_message_sent_all_outbound_logged`.
9. **Full labeled set.** The demo ends with the 40-intake eval: accuracy 37/40, escalation rate 16/40, missed emergencies 0 (router alone missed 2) — **recorded fixtures, not a model**. To regenerate the report exactly as CI does:
   ```bash
   export RUNNER_TEMP=$(mktemp -d); export G0_DB_PATH="$RUNNER_TEMP/layer.sqlite"
   uv run intake-desk eval --run-id eval --out "$RUNNER_TEMP/out" --report "$RUNNER_TEMP/eval-report.md"
   diff -u docs/eval-report.md "$RUNNER_TEMP/eval-report.md"
   ```
   Verified by those three lines on 2026-11-24 (eval exit 0, diff exit 0, no difference) and `tests/test_acceptance.py::test_ac5_accuracy_and_escalation_rate_reported_with_a_tunable_threshold`.
10. **Move the threshold.** `uv run intake-desk eval --threshold 0.8 --report out/r08.md` — the report's sweep table already shows 0.5–0.9 (escalation 35.0% → 77.5%, missed emergencies 0 at every row).
    Verified by `tests/test_cli.py::test_env_threshold` and `test_ac5_…` above; the 0.8 command itself was not run in this pack.
11. **One intake and the queue by hand.**
    ```bash
    uv run intake-desk route --case i29 --run-id manual
    uv run intake-desk queue list --status pending --run-id manual
    uv run intake-desk queue reject <queue_id> --note "handled" --run-id manual
    ```
    Verified by `tests/test_cli.py::test_route_and_queue_round_trip`.
12. **The webhook API.** `uv run intake-desk serve`, then open http://127.0.0.1:8040/docs (localhost only, no auth, recorded router). Try `POST /webhooks/missed-call` with the i25 gas-smell example from `tests/test_api.py`, then `GET /queue` and `GET /outbox`.
    Verified by `tests/test_api.py` (TestClient), and on 2026-11-24 by starting `serve` once: `/health` returned `"sends_anything": false`, `/docs` returned 200, the i25 webhook escalated with `gas_smell` and an on-call alert `logged_not_sent`; the server was then stopped.

## Not verified

- No stop has been clicked through by Shane.
- No live model call has ever run; `AgentSdkRouter`, its 60 s timeout and the cost-cap check have not met a real SDK (NEXT.md, 2026-11-22).
- The emergency guard is regex on synthetic text, not real calls.
- The API was never served beyond this machine and has no auth.
