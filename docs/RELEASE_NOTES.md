# Release notes — G4·C Intake Desk

## Not deployed — portfolio pack 2026-11-24

There is no deployment, hosting, account or live model call behind anything here. This entry records what exists in the repo and the docs pack built around it. All results are on **synthetic intakes and hand-written recorded router responses** (D-6).

### What exists (verified with git on 2026-11-24)

| What | Where | Commit |
|---|---|---|
| Kickoff kit (PRD, KICKOFF, CLAUDE.md, NEXT.md) | `main` | `a9f4d0b` (2026-11-21) |
| G4·C build: 23 commits from plan (`d6dba00`) through safety invariants (`10cf9ea`), report + CLI (`9bff64c`), CI (`36f1c16`), the 2026-11-22 review fixes (`7b6e55b`…`622658a`) and owner decisions D-40/D-41 (`b230c79`, `e414336`) | PR #1 from `build/g4c`, merged into `main` | merge `ec70d30` (2026-11-23), branch head `45c319b` |
| This pack: D-43, DEMO.md, LINKEDIN_DRAFTS.md, D-44, these notes, NEXT.md | branch `portfolio-pack/2026-11-24`, draft PR (not merged) | see the PR |

Gate on `main` @ `ec70d30`, run 2026-11-24 with the steps in `.github/workflows/ci.yml`: `uv sync --frozen` 0 · `ruff check .` 0, all checks passed · `mypy` 0, no issues in 12 source files · `pytest` 0, 135 passed · eval exit 0 and `diff` against `docs/eval-report.md` exit 0 · `intake-desk demo` 0.

Recorded-fixture results (threshold 0.7, `docs/eval-report.md`): routing accuracy 37/40 · router-only 35/40 · escalation rate 16/40 · missed labeled emergencies 0 of 11 (router alone missed 2) · booked below threshold 0 · cost $0.00.

### The pack

| Item | Where | State |
|---|---|---|
| Gate results | PR description, NEXT.md | Run 2026-11-24, all green locally; CI on the PR: see the PR |
| Demo walk-through | `docs/DEMO.md` | 12 stops, each verified by a named test or command; not yet clicked through by Shane |
| Exec brief "G4·C Intake Desk in Brief" | [Claude Docs](https://claude.ai/artifact/W2h3DJ2r1W8RoScuDsUZ8w) (private, not shared) | Written 2026-11-23; re-read 2026-11-24 and kept unchanged (D-43) |
| LinkedIn drafts | `docs/LINKEDIN_DRAFTS.md` | Two drafts (D-11, D-3); drafted, unposted |
| Cost note | `docs/DECISIONS.md` D-44 | Measured $0 on the recorded path; build and live cost not measured |
| Judgment calls | `docs/DECISIONS.md` D-43 | Recorded |
| Hand-off | `NEXT.md` (2026-11-24 section) | "You:" steps listed |

### Not verified

No live model call; no deployment; the API never ran beyond localhost and has no auth; the emergency guard is tested only on synthetic text; no stop in DEMO.md has been clicked through by Shane.
