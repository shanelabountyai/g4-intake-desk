"""Evaluation run and report (T8, AC5, D-22, D-24).

`run_eval` sends every labeled intake through the real desk (router → decide_final → actions → outbox) in arrival
order. Each outcome is scored by G0 `evaluation` against rubric `g4_route_v1`; accuracy is read from those G0 results.
The threshold sweep re-applies `decide_final` to the router answers already collected (no new router calls).
On the recorded router these numbers describe the hand-written fixtures, not a model.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from intake_desk.desk import Desk
from intake_desk.fixtures import Label, by_time
from intake_desk.models import ROUTES, Intake, Outcome
from intake_desk.safety import decide_final

SWEEP = (0.5, 0.6, 0.7, 0.8, 0.9)


@dataclass
class Metrics:
    threshold: float
    n: int
    correct: int
    router_correct: int
    escalated: int
    emergencies: int
    missed_emergencies: list[str]
    missed_router_only: list[str]
    auto_booked_below_threshold: list[str]
    confusion: dict[str, dict[str, int]]
    errors: list[str] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0

    @property
    def router_accuracy(self) -> float:
        return self.router_correct / self.n if self.n else 0.0

    @property
    def escalation_rate(self) -> float:
        return self.escalated / self.n if self.n else 0.0


def compute(rows: Sequence[tuple[str, str, str | None, float, Label]], threshold: float) -> Metrics:
    """rows: (intake_id, final_route, router_route or None, router_confidence, label)."""
    confusion: dict[str, dict[str, int]] = {lab: dict.fromkeys(ROUTES, 0) for lab in ROUTES}
    correct = router_correct = escalated = emergencies = 0
    missed, missed_router, booked_low, errors = [], [], [], []
    for iid, final, rroute, conf, label in rows:
        confusion[label.route][final] += 1
        if final == label.route:
            correct += 1
        else:
            errors.append(f"{iid}: labeled {label.route}, routed {final}")
        router_correct += int(rroute == label.route)
        escalated += int(final == "escalate")
        if label.emergency:
            emergencies += 1
            if final != "escalate":
                missed.append(iid)
            if rroute != "escalate":
                missed_router.append(iid)
        if final == "book" and conf < threshold:
            booked_low.append(iid)
    return Metrics(threshold=threshold, n=len(rows), correct=correct, router_correct=router_correct, escalated=escalated,
                   emergencies=emergencies, missed_emergencies=missed, missed_router_only=missed_router,
                   auto_booked_below_threshold=booked_low, confusion=confusion, errors=errors)


@dataclass
class EvalRun:
    outcomes: list[Outcome]
    labels: dict[str, Label]
    intakes: dict[str, Intake]
    current: Metrics
    sweep: list[Metrics]
    g0_correct: int
    g0_passed: int
    run_total: dict[str, Any]
    router_name: str
    outbound_status: Counter[str]
    queue_pending: int


async def run_eval(desk: Desk, intakes: list[Intake], labels: dict[str, Label]) -> EvalRun:
    outcomes = [await desk.process(i) for i in by_time(intakes)]
    rows = [(o.intake_id, o.decision.route, o.decision.router.route if o.decision.router else None,
             o.decision.router.confidence if o.decision.router else 0.0, labels[o.intake_id]) for o in outcomes]
    current = compute(rows, desk.config.threshold)

    g0_correct = g0_passed = 0
    for o in outcomes:
        lab = labels[o.intake_id]
        item = {"intake_id": o.intake_id, "label": lab.route, "final_route": o.decision.route,
                "route_correct": "yes" if o.decision.route == lab.route else "no", "emergency": lab.emergency,
                "emergency_safe": ("yes" if o.decision.route == "escalate" else "no") if lab.emergency else "n/a",
                "reasons": "; ".join(o.decision.reasons)}
        ev = desk.layer.evaluate(item, run_id=desk.run_id)
        if not ev.ok:
            raise RuntimeError(f"G0 evaluation refused {o.intake_id}: {ev.error}")
        g0_passed += int(ev.passed)
        g0_correct += int(next(s.score for s in ev.scores if s.criterion == "route_correct") >= 1.0)

    texts = {i.id: i.text for i in intakes}
    sweep = []
    for t in SWEEP:
        srows = []
        for o in outcomes:
            r = o.decision.router
            d = decide_final(r, texts[o.intake_id], t, invalid_reason=None if r else "invalid", after_hours=o.after_hours)
            srows.append((o.intake_id, d.route, r.route if r else None, r.confidence if r else 0.0, labels[o.intake_id]))
        sweep.append(compute(srows, t))

    total = desk.layer.run_total(desk.run_id)
    status: Counter[str] = Counter(str(rec.status) for o in outcomes for rec in o.outbound)
    return EvalRun(outcomes=outcomes, labels=labels, intakes={i.id: i for i in intakes}, current=current, sweep=sweep,
                   g0_correct=g0_correct, g0_passed=g0_passed, run_total=total.model_dump(), router_name=desk.router.name,
                   outbound_status=status, queue_pending=len(desk.store.queue("pending")))


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def render(ev: EvalRun, run_id: str) -> str:
    m = ev.current
    recorded = ev.router_name == "recorded"
    lines = [
        "# Eval report — G4·C Intake Desk",
        "",
        f"Run `{run_id}` · router `{ev.router_name}` · threshold **{m.threshold:.2f}** · {m.n} labeled synthetic intakes.",
        "",
    ]
    if recorded:
        lines += ["> **These numbers describe the hand-written recorded router responses in `fixtures/recorded.json`, not a model.** "
                  "Several recorded answers are deliberately wrong or unsure so the threshold and the emergency guard have something to catch. "
                  "No live model call was made; tokens and cost are 0 (D-6).", ""]
    lines += [
        "## At the current threshold",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Routing accuracy (final route = label; from G0 `evaluation`, rubric `g4_route_v1`) | {ev.g0_correct}/{m.n} = {_pct(ev.g0_correct / m.n)} |",
        f"| Router-only accuracy (raw router route = label) | {m.router_correct}/{m.n} = {_pct(m.router_accuracy)} |",
        f"| Escalation rate | {m.escalated}/{m.n} = {_pct(m.escalation_rate)} |",
        f"| Missed labeled emergencies (final) | **{len(m.missed_emergencies)}** of {m.emergencies} {m.missed_emergencies or ''} |",
        f"| Emergencies the router alone did not escalate (caught by guard/threshold) | {len(m.missed_router_only)} {m.missed_router_only or ''} |",
        f"| Booked below threshold | {len(m.auto_booked_below_threshold)} |",
        f"| G0 rubric passes (route correct, emergency safe, reasons logged) | {ev.g0_passed}/{m.n} |",
        f"| Queue items pending owner decision (escalations + held bookings, D-25) | {ev.queue_pending} |",
        f"| Outbound by status (all logged, none sent) | {', '.join(f'{k}: {v}' for k, v in sorted(ev.outbound_status.items()))} |",
        f"| Run cost (G0 observability) | {ev.run_total['calls']} router calls, {ev.run_total['input_tokens']} in / "
        f"{ev.run_total['output_tokens']} out tokens, ${ev.run_total['cost_usd']:.4f} |",
        "",
        "## Per-route confusion (rows = label, columns = final route)",
        "",
        "| label \\ routed | " + " | ".join(ROUTES) + " |",
        "|---|" + "---|" * len(ROUTES),
    ]
    for route in ROUTES:
        lines.append(f"| {route} | " + " | ".join(str(m.confusion[route][r]) for r in ROUTES) + " |")
    lines += [
        "",
        "## Threshold sweep",
        "",
        "| Threshold | Accuracy | Router-only accuracy | Escalation rate | Missed emergencies | Booked below threshold |",
        "|---|---|---|---|---|---|",
    ]
    for s in ev.sweep:
        mark = " (current)" if abs(s.threshold - m.threshold) < 1e-9 else ""
        lines.append(f"| {s.threshold:.1f}{mark} | {_pct(s.accuracy)} | {_pct(s.router_accuracy)} | {_pct(s.escalation_rate)} | "
                     f"{len(s.missed_emergencies)} | {len(s.auto_booked_below_threshold)} |")
    lines += ["", "## Misroutes at the current threshold", ""]
    lines += [f"- {e} — tags: {', '.join(ev.labels[e.split(':')[0]].tags)}" for e in m.errors] or ["- none"]
    lines += ["", "## Per-intake trace", "",
              "| Intake | Label | Router (conf) | Final | Overrides | Status | Outbound |",
              "|---|---|---|---|---|---|---|"]
    for o in sorted(ev.outcomes, key=lambda x: x.intake_id):
        r = o.decision.router
        lab = ev.labels[o.intake_id]
        lines.append(f"| {o.intake_id} | {lab.route}{' (emergency)' if lab.emergency else ''} | "
                     f"{f'{r.route} ({r.confidence:.2f})' if r else 'invalid'} | {o.decision.route} | {', '.join(o.decision.overrides) or '–'} | "
                     f"{o.status} | {', '.join(f'{x.kind}:{x.status}' for x in o.outbound) or '–'} |")
    lines.append("")
    return "\n".join(lines)


def write(ev: EvalRun, run_id: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(ev, run_id), encoding="utf-8")
    return path
