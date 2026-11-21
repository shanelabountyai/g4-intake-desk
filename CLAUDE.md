# Home-Services Intake Desk (G4)

Agentic AI track, build-log G4. Spec: `docs/prd.md`. Start: `KICKOFF.md`. Status: `NEXT.md`.

Rules for any Claude Code session here:
- Synthetic data only. All outbound texts/emails and calendar bookings are logged, never sent. Zero missed labeled emergencies is the bar.
- No merges to main, deploys, live external writes or account changes without the owner's explicit go.
- Shared capabilities come from ../shared (G0) or local stubs with the same contract; never inline them in prompts.
- Log tokens and cost per run. Keep NEXT.md and docs/DECISIONS.md current.
