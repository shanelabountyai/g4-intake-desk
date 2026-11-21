"""Router contract router_v1 (T4, D-19): malformed router output is caught and fails closed."""

from __future__ import annotations

import json
from pathlib import Path

import anyio
import jsonschema
import pytest

from intake_desk.models import RouterDecision, RouterOutputInvalid, parse_router
from intake_desk.router import RecordedRouter

REPO = Path(__file__).resolve().parents[1]


def test_published_schema_equals_model() -> None:
    assert json.loads((REPO / "schemas" / "router_v1.json").read_text()) == RouterDecision.json_schema()


def test_every_recorded_response_validates() -> None:
    schema = RouterDecision.json_schema()
    for key, raw in RecordedRouter().responses.items():
        jsonschema.validate(raw, schema)
        assert parse_router(raw).reasons, key


@pytest.mark.parametrize("raw", [
    "not json",
    "[]",
    '"book"',
    {},
    {"route": "book", "confidence": 0.9},
    {"route": "book", "confidence": 0.9, "reasons": []},
    {"route": "book", "confidence": 0.9, "reasons": ["  "]},
    {"route": "dispatch", "confidence": 0.9, "reasons": ["x"]},
    {"route": "book", "confidence": 1.2, "reasons": ["x"]},
    {"route": "book", "confidence": -0.1, "reasons": ["x"]},
    {"route": "book", "confidence": "high", "reasons": ["x"]},
    {"route": "book", "confidence": 0.9, "reasons": ["a", "b", "c", "d", "e", "f"]},
    {"route": "book", "confidence": 0.9, "reasons": ["x"], "slot": "Mon 8am"},
])
def test_malformed_router_output_is_rejected(raw) -> None:
    with pytest.raises(RouterOutputInvalid):
        parse_router(raw)


def test_valid_json_string_is_accepted() -> None:
    d = parse_router('{"route": "follow_up", "confidence": 0.8, "reasons": ["missing details"]}')
    assert d.route == "follow_up" and d.confidence == 0.8


def test_malformed_output_escalates_with_zero_confidence(make_desk, by_id) -> None:
    router = RecordedRouter(responses={"router:i01": {"route": "book", "confidence": 0.99}})  # no reasons
    desk = make_desk(router=router)
    o = anyio.run(desk.process, by_id["i01"])
    assert o.decision.route == "escalate" and o.decision.confidence == 0.0 and o.decision.overrides == ["router_invalid"]
    assert o.booking_id is None and o.queue_id


def test_missing_recording_escalates(make_desk, by_id) -> None:
    desk = make_desk(router=RecordedRouter(responses={}))
    o = anyio.run(desk.process, by_id["i03"])
    assert o.decision.route == "escalate" and "router_invalid" in o.decision.overrides
