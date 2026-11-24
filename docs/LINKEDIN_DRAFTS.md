# LinkedIn drafts — G4·C Intake Desk

Two drafts in Shane's voice for review. **Status of both: Drafted, unposted.** Every number comes from `docs/eval-report.md` or `docs/DECISIONS.md` and describes **hand-written recorded router responses on 40 synthetic intakes, not a live model**. The project is not deployed. Edit freely; nothing here has been posted anywhere.

---

## Draft 1 — the safety check that doesn't trust the model (D-11)

**Status: Drafted, unposted.**

I built a small intake desk for an HVAC shop: a missed call or web form comes in, and an AI router decides whether to book it, follow up, or hand it to a person.

The decision I spent the most time on was what happens when the router is wrong about an emergency.

So the router doesn't get the last word on safety. A plain rule in code checks every message for things like a gas smell, carbon monoxide, a burning smell, no heat or an active leak, and sends those to a person no matter what the router said (decision D-11 in my build log).

On my 40 synthetic test calls, using recorded router answers rather than a live model, the router alone missed 2 of the 11 emergencies. One was a furnace bang with a burning smell that it wanted to book for a diagnostic visit. The code rule caught both, so 0 of 11 were missed.

The cost is real: more calls go to a person, including some false alarms like "no gas smell". I accepted that on purpose. A shop owner can live with an extra callback. They can't live with a gas leak booked for next week.

It isn't deployed and it hasn't met a live model yet. That's the next test.

---

## Draft 2 — picking the confidence threshold (D-3)

**Status: Drafted, unposted.**

One number in my intake-desk build turned out to be a business decision, not a technical one: the confidence threshold.

The router returns a route and a confidence score. Below the threshold, the call goes to a person instead of being booked or followed up automatically. I started at 0.7 (decision D-3 in my build log) and made the report show what happens at other settings.

On 40 synthetic intakes with recorded router answers (not a live model):

- At 0.7, 16 of 40 went to a person and 37 of 40 ended up on the right route.
- At 0.9, 77.5% went to a person and only 57.5% were routed right, because careful turned into "send everything to the owner".
- At 0.5, an angry customer the router had marked as a routine follow-up at 0.68 slipped through without a person seeing it.

Missed emergencies stayed at 0 at every setting, because a separate code check handles those and doesn't depend on the threshold.

What I like about this setup is that the owner can move the number and see the trade before changing anything. Nothing is deployed yet. The real numbers will come from a live run.
