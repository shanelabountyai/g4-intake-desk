"""The desk pipeline (T6): book, follow up, escalate, duplicates, consent, brand, owner approve/reject."""

from __future__ import annotations

from datetime import datetime

import anyio
import pytest

from intake_desk import templates
from intake_desk.desk import DeskConfig
from intake_desk.models import Intake
from intake_desk.router import RecordedRouter
from intake_desk.store import QueueError


def run(desk, *intakes):
    return [anyio.run(desk.process, i) for i in intakes]


def test_book_creates_synthetic_booking_and_logged_confirmation(desk, by_id) -> None:
    [o] = run(desk, by_id["i01"])
    assert o.status == "booked" and o.booking_id and o.contact_id == "g4-c01"
    [b] = desk.store.bookings()
    assert b["slot_start"] == "2026-01-14T08:00:00-06:00" and b["calendar"] == "synthetic"  # next business day, first slot
    [rec] = o.outbound
    assert rec.kind == "booking_confirmation" and rec.status == "logged_not_sent" and rec.channel == "email"


def test_bookings_take_the_next_free_slot(desk, by_id) -> None:
    run(desk, by_id["i01"], by_id["i02"])
    assert [b["slot_start"][11:16] for b in desk.store.bookings()] == ["08:00", "10:00"]


@pytest.mark.parametrize("case,template", [("i11", "price_inquiry"), ("i13", "after_hours"), ("i17", "out_of_scope"), ("i22", "missing_details")])
def test_follow_up_templates(desk, by_id, case, template) -> None:
    [o] = run(desk, by_id[case])
    assert o.status == "follow_up_logged" and o.outbound[0].template == template and o.outbound[0].status == "logged_not_sent"


def test_emergency_goes_to_queue_with_on_call_alert_after_hours(desk, by_id) -> None:
    [o] = run(desk, by_id["i24"])
    assert o.decision.route == "escalate" and o.after_hours and o.queue_id
    [alert] = o.outbound
    assert alert.kind == "owner_alert" and alert.to == "on_call_tech" and alert.channel == "internal" and alert.status == "logged_not_sent"
    [q] = desk.store.queue("pending")
    assert q["intake_id"] == "i24" and q["proposed_action"] == "owner_handled" and "possible emergency" in q["why"]


def test_business_hours_escalation_alerts_owner(desk, by_id) -> None:
    [o] = run(desk, by_id["i26"])
    assert not o.after_hours and o.outbound[0].to == "owner"


def test_low_confidence_queue_item_proposes_router_route(desk, by_id) -> None:
    [o] = run(desk, by_id["i21"])
    q = desk.store.queue_item(o.queue_id)
    assert q["proposed_action"] == "follow_up" and "low confidence" in q["why"]


def test_duplicates_create_nothing_new_but_emergencies_requeue(desk, by_id) -> None:
    run(desk, by_id["i01"], by_id["i24"], by_id["i11"])
    d_book, d_emergency, d_follow = run(desk, by_id["i38"], by_id["i37"], by_id["i39"])
    assert d_book.duplicate_of == "i01" and d_book.status == "suppressed_duplicate" and d_book.booking_id is None
    assert len(desk.store.bookings()) == 1
    assert d_follow.duplicate_of == "i11" and d_follow.outbound[0].status == "suppressed_duplicate"
    assert d_emergency.duplicate_of == "i24" and d_emergency.status == "queued" and len(desk.store.queue("pending")) == 2


def test_unknown_callers_are_never_deduplicated(desk, by_id) -> None:
    a, b = run(desk, by_id["i14"], by_id["i14"].model_copy(update={"id": "i14b"}))
    assert a.contact_id is None and b.duplicate_of is None


@pytest.mark.parametrize("case,reason", [("i14", "unknown_contact"), ("i19", "do_not_contact"), ("i40", "not_consented")])
def test_consent_blocks_customer_outbound(desk, by_id, case, reason) -> None:
    [o] = run(desk, by_id[case])
    [rec] = o.outbound
    assert rec.status == "blocked_consent" and reason in rec.detail


def test_brand_failure_blocks_and_queues(desk, by_id, monkeypatch) -> None:
    monkeypatch.setitem(templates.FOLLOW_UP, "price_inquiry", "A tune-up is only $79, we guarantee it.")
    [o] = run(desk, by_id["i11"])
    assert o.outbound[0].status == "blocked_brand" and o.status == "blocked" and o.queue_id
    assert "g4.no_price_figures" in o.outbound[0].detail


def test_approve_executes_through_the_same_gates(desk, by_id) -> None:
    [o] = run(desk, by_id["i21"])
    res = desk.approve(o.queue_id, "book", "owner called back")
    assert res["queue"]["status"] == "approved" and res["queue"]["decided_action"] == "book" and res["booking_id"]
    assert [x["status"] for x in res["outbound"]] == ["logged_not_sent"]
    with pytest.raises(QueueError):
        desk.approve(o.queue_id)


def test_approve_emergency_default_sends_nothing_to_customer(desk, by_id) -> None:
    [o] = run(desk, by_id["i25"])
    res = desk.approve(o.queue_id, None, "dispatched")
    assert res["queue"]["decided_action"] == "owner_handled" and res["outbound"] == [] and res["booking_id"] is None


def test_reject_closes_with_nothing_sent(desk, by_id) -> None:
    [o] = run(desk, by_id["i36"])
    before = len(desk.store.outbox())
    res = desk.reject(o.queue_id, "handled in person")
    assert res["queue"]["status"] == "rejected" and len(desk.store.outbox()) == before
    with pytest.raises(QueueError):
        desk.reject(o.queue_id)
    with pytest.raises(QueueError):
        desk.approve("q_missing")


def test_after_hours_calendar() -> None:
    cfg = DeskConfig.load()
    assert cfg.after_hours(datetime.fromisoformat("2026-01-13T07:59:00-06:00"))
    assert not cfg.after_hours(datetime.fromisoformat("2026-01-13T08:00:00-06:00"))
    assert cfg.after_hours(datetime.fromisoformat("2026-01-13T17:00:00-06:00"))
    assert not cfg.after_hours(datetime.fromisoformat("2026-01-17T12:59:00-06:00"))  # Saturday
    assert cfg.after_hours(datetime.fromisoformat("2026-01-18T10:00:00-06:00"))  # Sunday
    assert not cfg.after_hours(datetime.fromisoformat("2026-01-13T15:30:00+00:00"))  # 09:30 Chicago


def test_observability_and_measurement_per_intake(desk, by_id) -> None:
    run(desk, by_id["i01"], by_id["i24"])
    total = desk.layer.run_total(desk.run_id)
    assert total.calls == 2 and total.cost_usd == 0.0
    n = desk.layer.db.conn.execute("SELECT COUNT(*) FROM events WHERE event = 'intake.routed' AND run_id = ?", (desk.run_id,)).fetchone()[0]
    assert n == 2


def test_free_text_intake_without_recording_escalates(desk) -> None:
    i = Intake(id="adhoc-1", source="form", received_at=datetime.fromisoformat("2026-07-14T10:00:00-05:00"), text="Tune-up please",
               phone="+1-312-555-0101")
    [o] = run(desk, i)
    assert o.decision.route == "escalate" and isinstance(desk.router, RecordedRouter)


def test_booking_with_blocked_confirmation_goes_to_owner(desk, by_id) -> None:
    [o] = run(desk, by_id["i40"])
    assert o.status == "booked" and o.booking_id and o.outbound[0].status == "blocked_consent"
    q = desk.store.queue_item(o.queue_id)
    assert q["proposed_action"] == "owner_handled" and "confirm by phone" in q["why"]
