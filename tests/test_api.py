"""FastAPI webhooks (T7)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from intake_desk.app import create_app


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(g0_db=str(tmp_path / "layer.sqlite"), desk_db=tmp_path / "desk.sqlite")) as c:
        yield c


def test_health(client) -> None:
    h = client.get("/health").json()
    assert h["g0"]["status"] == "ok" and h["threshold"] == 0.7 and h["router"] == "recorded" and h["sends_anything"] is False


def test_form_webhook_books(client) -> None:
    r = client.post("/webhooks/form", json={"id": "i03", "received_at": "2026-07-15T11:05:00-05:00",
                                            "text": "AC tune-up before the heat gets worse. Central air, 3-ton unit. Afternoons are best.",
                                            "phone": "+1-312-555-0103", "email": "synthetic.caller03@example.com", "reply_channel": "email"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"]["route"] == "book" and body["decision"]["reasons"] and body["booking_id"]
    assert len(client.get("/bookings").json()) == 1
    assert [o["status"] for o in client.get("/outbox").json()] == ["logged_not_sent"]


def test_missed_call_emergency_then_owner_approves(client) -> None:
    r = client.post("/webhooks/missed-call", json={"id": "i25", "received_at": "2026-01-18T02:30:00-06:00",
                                                    "text": "I smell gas near the furnace in the basement.", "phone": "+1-312-555-0125"})
    out = r.json()
    assert out["decision"]["route"] == "escalate" and out["queue_id"]
    pending = client.get("/queue", params={"status": "pending"}).json()
    assert [q["intake_id"] for q in pending] == ["i25"]
    ok = client.post(f"/queue/{out['queue_id']}/approve", json={"note": "dispatched"})
    assert ok.status_code == 200 and ok.json()["queue"]["status"] == "approved"
    assert client.post(f"/queue/{out['queue_id']}/reject", json={}).status_code == 409
    assert client.post("/queue/q_nope/approve", json={}).status_code == 404


def test_reject_and_unknown_intake_fails_closed(client) -> None:
    r = client.post("/webhooks/form", json={"text": "Can you come Tuesday for a tune-up?", "phone": "+1-312-555-0101"})
    out = r.json()
    assert out["decision"]["route"] == "escalate" and "router_invalid" in out["decision"]["overrides"]  # no recording → fail closed
    rej = client.post(f"/queue/{out['queue_id']}/reject", json={"note": "spam"})
    assert rej.json()["queue"]["status"] == "rejected" and rej.json()["outbound"] == []


def test_bad_payload_rejected(client) -> None:
    assert client.post("/webhooks/form", json={"text": ""}).status_code == 422
    assert client.post("/webhooks/missed-call", json={"text": "hi", "audio_url": "x"}).status_code == 422


def test_retried_webhook_is_idempotent(client) -> None:
    # Review 2026-11-22 S5: a retried POST with the same intake id must not book or message again.
    payload = {"id": "i03", "received_at": "2026-07-15T11:05:00-05:00",
               "text": "AC tune-up before the heat gets worse. Central air, 3-ton unit. Afternoons are best.",
               "phone": "+1-312-555-0103", "email": "synthetic.caller03@example.com", "reply_channel": "email"}
    assert client.post("/webhooks/form", json=payload).status_code == 200
    again = client.post("/webhooks/form", json=payload)
    assert again.status_code == 409 and "already processed" in again.json()["detail"]
    assert len(client.get("/bookings").json()) == 1 and len(client.get("/outbox").json()) == 1
    assert client.post("/webhooks/missed-call", json={"id": "i03", "text": "retry", "phone": "+1-312-555-0103"}).status_code == 409
