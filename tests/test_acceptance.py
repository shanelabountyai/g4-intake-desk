"""PRD acceptance criteria AC1–AC5, on the full synthetic labeled set (recorded router)."""

from __future__ import annotations

import json

import anyio
import pytest

from intake_desk import cli
from intake_desk.models import RouterDecision
from intake_desk.report import SWEEP, run_eval
from intake_desk.safety import decide_final

ALLOWED_STATUSES = {"logged_not_sent", "blocked_consent", "blocked_brand", "suppressed_duplicate"}


@pytest.fixture()
def full_run(make_desk, labeled):
    desk = make_desk(jsonl=True)
    intakes, labels = labeled
    return desk, anyio.run(run_eval, desk, intakes, labels)


def test_ac1_every_intake_gets_a_route_with_logged_reasons(full_run, labeled) -> None:
    desk, ev = full_run
    intakes, _ = labeled
    assert len(ev.outcomes) == len(intakes) == 40
    for o in ev.outcomes:
        assert o.decision.route in ("book", "follow_up", "escalate") and o.decision.reasons and all(r.strip() for r in o.decision.reasons)
    rows = desk.layer.db.conn.execute("SELECT step, note FROM run_log WHERE run_id = ?", (desk.run_id,)).fetchall()
    logged = {r["step"].split(":", 1)[1]: json.loads(r["note"]) for r in rows}
    assert set(logged) == {i.id for i in intakes}
    assert all(n["final_route"] and "confidence" in n for n in logged.values())
    events = desk.layer.db.conn.execute("SELECT COUNT(*) FROM events WHERE event='intake.routed' AND run_id=?", (desk.run_id,)).fetchone()[0]
    assert events == 40
    assert ev.g0_passed == ev.g0_correct  # reasons_logged never the failing criterion


def test_ac2_every_labeled_emergency_is_escalated(full_run) -> None:
    _, ev = full_run
    assert ev.current.emergencies == 11 and ev.current.missed_emergencies == []
    assert all(s.missed_emergencies == [] for s in ev.sweep)


def test_ac2_guard_catches_router_misses_at_any_threshold(full_run, labeled) -> None:
    _, ev = full_run
    intakes, labels = labeled
    assert set(ev.current.missed_router_only) == {"i29", "i33"}  # the recorded router got these wrong
    for t in (0.0, 0.3, 0.5, 0.7, 1.0):
        for o in ev.outcomes:
            if labels[o.intake_id].emergency:
                text = next(i.text for i in intakes if i.id == o.intake_id)
                assert decide_final(o.decision.router, text, t).route == "escalate", (o.intake_id, t)


def test_ac3_low_confidence_is_escalated_never_auto_booked(full_run, labeled) -> None:
    desk, ev = full_run
    intakes, _ = labeled
    texts = {i.id: i.text for i in intakes}
    for o in ev.outcomes:
        r = o.decision.router
        if r is not None and r.confidence < desk.config.threshold:
            assert o.decision.route == "escalate" and o.booking_id is None and o.queue_id, o.intake_id
    for step in range(0, 21):
        t = step / 20
        for o in ev.outcomes:
            r = o.decision.router
            d = decide_final(r, texts[o.intake_id], t)
            if d.route == "book":
                assert r is not None and r.confidence >= t
    assert all(s.auto_booked_below_threshold == [] for s in ev.sweep)
    # A confident-looking book just under the threshold goes to the queue, not the calendar.
    assert decide_final(RouterDecision(route="book", confidence=0.6999, reasons=["routine"]), "tune-up", 0.7).route == "escalate"


def test_ac4_no_real_message_sent_all_outbound_logged(full_run) -> None:
    desk, ev = full_run
    rows = desk.store.outbox()
    assert {r.status for r in rows} <= ALLOWED_STATUSES
    assert len(rows) == sum(len(o.outbound) for o in ev.outcomes)
    assert len(desk.store.jsonl.read_text().splitlines()) == len(rows)
    customer = [r for r in rows if r.kind != "owner_alert"]
    assert all(r.to.startswith("g4-c") or r.to == "unknown_caller" for r in customer)  # ids, never a raw number or address
    assert all(b["calendar"] == "synthetic" for b in desk.store.bookings())
    assert ev.outbound_status["blocked_consent"] == 3 and ev.outbound_status["suppressed_duplicate"] == 2


def test_ac5_accuracy_and_escalation_rate_reported_with_a_tunable_threshold(full_run, make_desk, labeled, tmp_path) -> None:
    _, ev = full_run
    assert [s.threshold for s in ev.sweep] == list(SWEEP)
    assert ev.g0_correct == ev.current.correct  # accuracy read from G0 evaluation agrees with the local count
    m7 = ev.current
    intakes, labels = labeled
    ev8 = anyio.run(run_eval, make_desk(threshold=0.8), intakes, labels)
    assert ev8.current.threshold == 0.8 and ev8.current.escalated > m7.escalated
    report = tmp_path / "report.md"
    assert cli.main(["eval", "--threshold", "0.8", "--run-id", "t", "--out", str(tmp_path), "--report", str(report)]) == 0
    text = report.read_text()
    for section in ("Routing accuracy", "Escalation rate", "Missed labeled emergencies", "Per-route confusion", "Threshold sweep",
                    "0.8 (current)", "not a model"):
        assert section in text, section
