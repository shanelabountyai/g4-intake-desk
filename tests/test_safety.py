"""Safety invariants (T2): written before any route action existed. No code path can send a real message or touch a
real calendar; every labeled emergency is escalated; nothing below the threshold is booked; no live call without a key."""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from intake_desk import fixtures
from intake_desk.models import OutboundRecord, RouterDecision
from intake_desk.router import INSTRUCTIONS, AgentSdkRouter, LiveCallRefused
from intake_desk.safety import FORBIDDEN_MODULES, decide_final, emergency_signals
from intake_desk.store import Store

PKG = Path(__file__).resolve().parents[1] / "src" / "intake_desk"
ALLOWED_STATUSES = {"logged_not_sent", "blocked_consent", "blocked_brand", "suppressed_duplicate"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


@pytest.mark.parametrize("module", sorted(PKG.glob("*.py")), ids=lambda p: p.name)
def test_no_module_imports_a_network_mail_sms_or_calendar_client(module: Path) -> None:
    bad = {n for n in _imports(module) for f in FORBIDDEN_MODULES if n == f or n.startswith(f + ".")}
    assert not bad, f"{module.name} imports {bad}: no code path may reach a real phone, inbox, calendar or endpoint (D-18)"


def test_outbox_cannot_hold_a_sent_status() -> None:
    with pytest.raises(ValidationError):
        OutboundRecord(outbound_id="o", intake_id="i", kind="follow_up", channel="sms", to="g4-c01", template="t", body="b",
                       status="sent", logged_at="now")  # type: ignore[arg-type]
    store = Store(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        with store.conn:
            store.conn.execute("INSERT INTO outbox VALUES ('o','i','follow_up','sms','g4-c01','t','b','sent','','now')")
    store.close()


def test_calendar_is_synthetic_only() -> None:
    store = Store(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        with store.conn:
            store.conn.execute("INSERT INTO bookings VALUES ('b','i',NULL,'2026-01-01T08:00:00-06:00','google','now')")
    store.close()


@pytest.mark.parametrize("text", [
    "I smell gas near the furnace", "Carbon monoxide detector is going off", "burning smell from the vents", "saw sparks at the condenser",
    "water pouring from the ceiling", "pipe burst in the basement", "No heat at all", "heat went out this morning", "furnace won't turn on",
    "furnace off again", "AC quit completely, it's 101 out", "the air stopped and my dad is on oxygen", "smoke coming out of the furnace",
])
def test_guard_flags_hazards(text: str) -> None:
    assert emergency_signals(text), text


@pytest.mark.parametrize("text", [
    "Annual furnace tune-up please", "AC is a little noisy when it starts", "How much for a tune-up?", "upstairs a few degrees colder",
    "furnace is short cycling, house still warm", "condensate drips into the pan", "Need service.", "AC not working right.",
])
def test_guard_is_quiet_on_routine_requests(text: str) -> None:
    assert emergency_signals(text) == []


def test_guard_alone_flags_every_labeled_emergency() -> None:
    intakes, labels = fixtures.load()
    missed = [i.id for i in intakes if labels[i.id].emergency and not emergency_signals(i.text)]
    assert missed == []


def test_decision_order_fails_closed() -> None:
    invalid = decide_final(None, "Need service.", 0.7, invalid_reason="not JSON")
    assert invalid.route == "escalate" and invalid.confidence == 0.0 and invalid.overrides == ["router_invalid"]

    sure_book = RouterDecision(route="book", confidence=0.99, reasons=["looks routine"])
    guarded = decide_final(sure_book, "I smell gas in the basement", 0.7)
    assert guarded.route == "escalate" and "emergency_guard" in guarded.overrides and guarded.router == sure_book

    low = decide_final(RouterDecision(route="book", confidence=0.69, reasons=["ok"]), "tune-up please", 0.7)
    assert low.route == "escalate" and low.overrides == ["below_threshold"]

    boundary = decide_final(RouterDecision(route="follow_up", confidence=0.7, reasons=["ok"]), "Need service.", 0.7)
    assert boundary.route == "follow_up" and boundary.overrides == []

    low_escalate = decide_final(RouterDecision(route="escalate", confidence=0.2, reasons=["angry"]), "call me", 0.7)
    assert low_escalate.route == "escalate"

    with pytest.raises(ValueError):
        decide_final(sure_book, "x", 1.5)


def test_live_router_refuses_without_key() -> None:
    with pytest.raises(LiveCallRefused):
        AgentSdkRouter()


def test_router_prompt_carries_pointers_not_rules() -> None:
    low = INSTRUCTIONS.lower()
    # G0 brand policy v1 / g4-followup-1 rule text, the emergency guard's signals and the threshold value stay out of the prompt.
    for leaked in ("excited to share", "hope this finds you well", "60 words", "guarantee", "price", "$",
                   "gas", "carbon monoxide", "smoke", "spark", "oxygen", "0.7", "consented", "do not contact"):
        assert leaked not in low, leaked
