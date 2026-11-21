# G4 Home-Services Intake Desk — PRD v0.1

Nov 3, 2026 · @Shane LaBounty

## Summary

Agentic AI track, build-log G4. A missed call or web form arrives, and a router agent decides what happens next: book it, follow up, or escalate to a person. The agent makes a choice from context (urgency, business hours) and knows when not to decide.

Built twice: **G4·B in n8n first**, then **G4·C in Python with the Claude Agent SDK**.

**From the build-log card (already set):** router/handoff pattern; Switch plus a sub-workflow per path; Wait node for human approval when unsure; synthetic leads only; graphic row "Decisions"; doubles as a GoHighLevel offer demo. The C version adds a confidence score, an escalation queue below a threshold, and routing accuracy measured against a hand-labeled set.

**Everything else here is a proposal.**

## Why it's in the portfolio

It's the most sellable build in the track. It is the same intake problem as your GHL home-services offer and your Grok Bot HVAC work, so one demo supports the portfolio and two sales conversations. It also shows an agent that hands off to a human instead of guessing.

## Routes

| Route | When (proposed) | Action |
| --- | --- | --- |
| **Book** | Clear service request, normal urgency, enough detail | Offer booking slots; create the appointment (synthetic calendar) |
| **Follow up** | Missing details, price shopping, after hours and not urgent | Send a templated text/email asking for what's missing; schedule a reminder |
| **Escalate** | Emergency (e.g., no heat in winter, active leak), angry customer, or low confidence | Alert the owner; Wait node for a human decision |

## Inputs (synthetic)

- Missed-call transcripts or voicemail text
- Web form submissions
- Business hours and an on-call flag

*Proposal:* about 40 synthetic intakes, hand-labeled with the correct route, weighted toward HVAC. Include deliberate edge cases: after-hours emergencies, vague messages, duplicates, and wrong-trade requests.

## Shared-layer hooks (proposed)

- **audience.consent:** check before any text or email goes out.
- **brand.policy:** tone for follow-up messages.
- **evaluation:** stores the labeled set and routing accuracy.
- **observability:** logs each route, its confidence, and cost.

## G4·B (n8n) build notes

- Webhook trigger (form) plus a second trigger for missed-call text
- Router AI Agent → Switch → one sub-workflow per route
- Escalate path uses a Wait node; resumes on owner approve or reject
- Synthetic calendar and outbound messages logged, not sent

## G4·C (code) build notes

- FastAPI webhook
- Router returns `{ route, confidence, reasons }`
- Below the threshold → escalation queue, regardless of route
- Routing accuracy and escalation rate reported against the labeled set

## Acceptance criteria (proposed)

1. Every synthetic intake gets a route with logged reasons.
2. Every labeled emergency is escalated (zero missed emergencies is the bar).
3. Low-confidence intakes are escalated, never auto-booked.
4. No real message is sent; all outbound is logged only.
5. **C only:** routing accuracy and escalation rate reported, with a threshold you can tune.

## Decisions needed (one at a time)

**1. Trade focus for synthetic data** *Recommendation: HVAC,* matching your Grok Bot HVAC work and the first-trade recommendation in the GHL PRD.

**2. Confidence threshold (C version)** *Recommendation:* start at 0.7, then tune using the labeled set. Optimize for zero missed emergencies, even at the cost of more escalations.

**3. Run it inside GoHighLevel too?** *Recommendation: not in v1.* Keep it n8n and code as the build log defines; show the GHL connection in the demo narrative only, until the GHL offer is live.

## Questions for you

1. Do you want the demo to include a voice element (missed call → transcript), or text and forms only?
2. Should this become the live demo for GHL prospects, or stay a portfolio piece?
