# Eval report — G4·C Intake Desk

Run `eval` · router `recorded` · threshold **0.70** · 40 labeled synthetic intakes.

> **These numbers describe the hand-written recorded router responses in `fixtures/recorded.json`, not a model.** Several recorded answers are deliberately wrong or unsure so the threshold and the emergency guard have something to catch. No live model call was made; tokens and cost are 0 (D-6).

## At the current threshold

| Metric | Value |
|---|---|
| Routing accuracy (final route = label; from G0 `evaluation`, rubric `g4_route_v1`) | 36/40 = 90.0% |
| Router-only accuracy (raw router route = label) | 35/40 = 87.5% |
| Escalation rate | 16/40 = 40.0% |
| Missed labeled emergencies (final) | **0** of 11  |
| Emergencies the router alone did not escalate (caught by guard/threshold) | 2 ['i29', 'i33'] |
| Booked below threshold | 0 |
| G0 rubric passes (route correct, emergency safe, reasons logged) | 36/40 |
| Queue items pending owner decision (escalations + held bookings, D-25) | 17 |
| Outbound by status (all logged, none sent) | blocked_consent: 3, logged_not_sent: 35, suppressed_duplicate: 2 |
| Run cost (G0 observability) | 40 router calls, 0 in / 0 out tokens, $0.0000 |

## Per-route confusion (rows = label, columns = final route)

| label \ routed | book | follow_up | escalate |
|---|---|---|---|
| book | 11 | 1 | 0 |
| follow_up | 1 | 11 | 2 |
| escalate | 0 | 0 | 14 |

## Threshold sweep

| Threshold | Accuracy | Router-only accuracy | Escalation rate | Missed emergencies | Booked below threshold |
|---|---|---|---|---|---|
| 0.5 | 90.0% | 87.5% | 35.0% | 0 | 0 |
| 0.6 | 90.0% | 87.5% | 35.0% | 0 | 0 |
| 0.7 (current) | 90.0% | 87.5% | 40.0% | 0 | 0 |
| 0.8 | 82.5% | 87.5% | 52.5% | 0 | 0 |
| 0.9 | 57.5% | 87.5% | 77.5% | 0 | 0 |

## Misroutes at the current threshold

- i12: labeled follow_up, routed escalate — tags: vague, unknown_caller
- i08: labeled book, routed follow_up — tags: heating, estimate_visit
- i20: labeled follow_up, routed book — tags: after_hours, sunday
- i21: labeled follow_up, routed escalate — tags: vague

## Per-intake trace

| Intake | Label | Router (conf) | Final | Overrides | Status | Outbound |
|---|---|---|---|---|---|---|
| i01 | book | book (0.93) | book | – | booked | booking_confirmation:logged_not_sent |
| i02 | book | book (0.86) | book | – | booked | booking_confirmation:logged_not_sent |
| i03 | book | book (0.91) | book | – | booked | booking_confirmation:logged_not_sent |
| i04 | book | book (0.88) | book | – | booked | booking_confirmation:logged_not_sent |
| i05 | book | book (0.84) | book | – | booked | booking_confirmation:logged_not_sent |
| i06 | book | book (0.90) | book | – | booked | booking_confirmation:logged_not_sent |
| i07 | book | book (0.78) | book | – | booked | booking_confirmation:logged_not_sent |
| i08 | book | follow_up (0.72) | follow_up | – | follow_up_logged | follow_up:logged_not_sent |
| i09 | book | book (0.80) | book | – | booked | booking_confirmation:logged_not_sent |
| i10 | book | book (0.82) | book | – | booked | booking_confirmation:logged_not_sent |
| i11 | follow_up | follow_up (0.90) | follow_up | – | follow_up_logged | follow_up:logged_not_sent |
| i12 | follow_up | follow_up (0.45) | escalate | below_threshold | queued | owner_alert:logged_not_sent |
| i13 | follow_up | follow_up (0.87) | follow_up | – | follow_up_logged | follow_up:logged_not_sent |
| i14 | follow_up | follow_up (0.83) | follow_up | – | follow_up_logged | follow_up:blocked_consent |
| i15 | follow_up | follow_up (0.74) | follow_up | – | follow_up_logged | follow_up:logged_not_sent |
| i16 | follow_up | follow_up (0.88) | follow_up | – | follow_up_logged | follow_up:logged_not_sent |
| i17 | follow_up | follow_up (0.92) | follow_up | – | follow_up_logged | follow_up:logged_not_sent |
| i18 | follow_up | follow_up (0.90) | follow_up | – | follow_up_logged | follow_up:logged_not_sent |
| i19 | follow_up | follow_up (0.93) | follow_up | – | follow_up_logged | follow_up:blocked_consent |
| i20 | follow_up | book (0.74) | book | – | booked | booking_confirmation:logged_not_sent |
| i21 | follow_up | follow_up (0.62) | escalate | below_threshold | queued | owner_alert:logged_not_sent |
| i22 | follow_up | follow_up (0.70) | follow_up | – | follow_up_logged | follow_up:logged_not_sent |
| i23 | follow_up | follow_up (0.86) | follow_up | – | follow_up_logged | follow_up:logged_not_sent |
| i24 | escalate (emergency) | escalate (0.97) | escalate | – | queued | owner_alert:logged_not_sent |
| i25 | escalate (emergency) | escalate (0.98) | escalate | – | queued | owner_alert:logged_not_sent |
| i26 | escalate (emergency) | escalate (0.97) | escalate | – | queued | owner_alert:logged_not_sent |
| i27 | escalate (emergency) | escalate (0.90) | escalate | – | queued | owner_alert:logged_not_sent |
| i28 | escalate (emergency) | escalate (0.93) | escalate | – | queued | owner_alert:logged_not_sent |
| i29 | escalate (emergency) | book (0.76) | escalate | emergency_guard | queued | owner_alert:logged_not_sent |
| i30 | escalate (emergency) | escalate (0.91) | escalate | – | queued | owner_alert:logged_not_sent |
| i31 | escalate (emergency) | escalate (0.95) | escalate | – | queued | owner_alert:logged_not_sent |
| i32 | escalate (emergency) | escalate (0.88) | escalate | – | queued | owner_alert:logged_not_sent |
| i33 | escalate (emergency) | follow_up (0.66) | escalate | emergency_guard | queued | owner_alert:logged_not_sent |
| i34 | escalate | escalate (0.90) | escalate | – | queued | owner_alert:logged_not_sent |
| i35 | escalate | escalate (0.88) | escalate | – | queued | owner_alert:logged_not_sent |
| i36 | escalate | follow_up (0.68) | escalate | below_threshold | queued | owner_alert:logged_not_sent |
| i37 | escalate (emergency) | escalate (0.96) | escalate | – | queued | owner_alert:logged_not_sent |
| i38 | book | book (0.92) | book | – | suppressed_duplicate | booking_confirmation:suppressed_duplicate |
| i39 | follow_up | follow_up (0.89) | follow_up | – | suppressed_duplicate | follow_up:suppressed_duplicate |
| i40 | book | book (0.90) | book | – | booked | booking_confirmation:blocked_consent |
