# Kickoff — Home-Services Intake Desk (Build Log G4, Agentic AI track)

Paste the block below into Claude Code started in `~/Projects/agentic-track/g4-intake-desk`, on Fable (`/model`).

```
You are starting a new build: Home-Services Intake Desk (Build Log G4, Agentic AI track,
graphic row "Decisions"). The spec is docs/prd.md. Read it fully before doing anything.
Also read ../README.md for the track order and the shared-layer (G0) contract rule.

The project is built twice, in this order:
- G4·B (n8n first): n8n: form webhook + missed-call-text trigger -> router AI Agent -> Switch -> one sub-workflow per route (book / follow up / escalate); escalate uses a Wait node for owner approve/reject.
  Deliver it as importable workflow JSON in n8n/, with a README on how to import it
  into the owner's self-hosted n8n.
- G4·C (code second): Python 3.12 + Claude Agent SDK + FastAPI webhook: router returns {route, confidence, reasons}; below the threshold always goes to an escalation queue; accuracy and escalation rate reported against the labeled set.
  Start G4·C only after G4·B passes its acceptance criteria.

Test data: ~40 synthetic intakes weighted to HVAC, hand-labeled with the correct route, including after-hours emergencies, vague messages, duplicates and wrong-trade requests.

Safety invariants (land with tests BEFORE any code path can reach a live system):
Synthetic data only. All outbound texts/emails and calendar bookings are logged, never sent. Zero missed labeled emergencies is the bar.

Shared layer (G0): the PRD lists the shared capabilities this project calls
(claims.registry, brand.policy, audience.consent, measurement, evaluation,
observability). If ../shared/ does not exist yet, build local stubs with the same
input and output shape, in one clearly named module, so they can be swapped for G0
later. Never copy rules into an agent's prompt that belong in the shared layer.

Open decisions in the PRD: Trade focus (PRD recommends HVAC), confidence threshold (start 0.7), voice element or text/forms only, GHL tie-in (PRD recommends narrative only in v1).
Take the PRD's recommendation for each unless I say otherwise, and record each as a
D- entry in docs/DECISIONS.md before writing code.

Working rules:
- Confirm current Claude model IDs and prices from Anthropic's docs before using them.
  Confirm current n8n node names and options from n8n's docs; record what you found.
- Log tokens and cost per run from the first live call. Hard cap: $10 of live model
  calls for the whole build unless I raise it.
- Keep NEXT.md current, matching the other build-log repos: what is done, what is
  next, and exact hand steps for the owner.
- Commit at the end of every task with a clear message. Never commit secrets; keys
  live in a gitignored .env.
- Work on a branch named `kickoff`. No merges to main, no deploys, no live external
  writes, and no account changes without my explicit go.

Step 1, plan first: write docs/BACKLOG.md breaking G4·B then G4·C into tasks
you can finish and test in one sitting, each with acceptance criteria taken from the
PRD. List owner hand steps separately. Then stop and show me the backlog and
DECISIONS.md before building.
```
