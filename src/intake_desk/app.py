"""FastAPI webhooks (T7). Local demo only: no auth, not deployed (BACKLOG "Later").

    POST /webhooks/form          web form       → Outcome
    POST /webhooks/missed-call   missed-call/voicemail transcript text (no audio, D-4) → Outcome
    GET  /queue                  escalation queue (?status=pending|approved|rejected)
    POST /queue/{id}/approve     owner approves (optional action override: book | follow_up | owner_handled)
    POST /queue/{id}/reject      owner rejects; nothing is sent
    GET  /outbox                 every outbound, all logged, none sent
    GET  /bookings               the synthetic calendar
    GET  /health                 G0 health + desk settings

An intake with no recorded router answer escalates (router unavailable → fail closed, D-12) unless the app was started
with a live router, which needs ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from intake_desk.desk import Desk, DeskConfig, OwnerAction
from intake_desk.layer import Layer
from intake_desk.models import Intake, Outcome
from intake_desk.router import AgentSdkRouter, RecordedRouter, Router
from intake_desk.store import QueueError, Store


class FormIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    received_at: datetime | None = None
    text: str = Field(min_length=1, max_length=4000)
    phone: str | None = None
    email: str | None = None
    reply_channel: Literal["sms", "email"] = "sms"


class MissedCallIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    received_at: datetime | None = None
    text: str = Field(min_length=1, max_length=4000, description="The missed-call or voicemail transcript.")
    phone: str | None = None


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: OwnerAction | None = None
    note: str | None = Field(default=None, max_length=500)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=500)


def create_app(*, g0_db: str | None = None, desk_db: str | Path = ":memory:", threshold: float | None = None,
               live: bool = False, run_id: str = "api", router: Router | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Built inside the lifespan so the SQLite connections live on the serving thread.
        layer = Layer(db_path=g0_db)
        layer.require_healthy()
        store = Store(desk_db)
        r: Router = router or (AgentSdkRouter() if live else RecordedRouter())
        app.state.desk = Desk(layer, store, r, DeskConfig.load(threshold=threshold), run_id)
        try:
            yield
        finally:
            store.close()
            layer.close()

    app = FastAPI(title="G4 Intake Desk (synthetic)", version="0.1.0", lifespan=lifespan)

    def desk(request: Request) -> Desk:
        d: Desk = request.app.state.desk
        return d

    async def _process(request: Request, intake: Intake) -> Outcome:
        return await desk(request).process(intake)

    @app.post("/webhooks/form")
    async def form(body: FormIn, request: Request) -> Outcome:
        return await _process(request, Intake(id=body.id or f"form-{uuid.uuid4().hex[:8]}", source="form",
                                              received_at=body.received_at or datetime.now(UTC), text=body.text,
                                              phone=body.phone, email=body.email, reply_channel=body.reply_channel))

    @app.post("/webhooks/missed-call")
    async def missed_call(body: MissedCallIn, request: Request) -> Outcome:
        return await _process(request, Intake(id=body.id or f"call-{uuid.uuid4().hex[:8]}", source="missed_call",
                                              received_at=body.received_at or datetime.now(UTC), text=body.text,
                                              phone=body.phone, reply_channel="sms"))

    @app.get("/queue")
    async def queue(request: Request, status: Literal["pending", "approved", "rejected"] | None = None) -> list[dict[str, Any]]:
        return desk(request).store.queue(status)

    @app.post("/queue/{queue_id}/approve")
    async def approve(queue_id: str, body: DecisionIn, request: Request) -> dict[str, Any]:
        try:
            return desk(request).approve(queue_id, body.action, body.note)
        except QueueError as e:
            raise HTTPException(status_code=404 if "no queue item" in str(e) else 409, detail=str(e)) from e

    @app.post("/queue/{queue_id}/reject")
    async def reject(queue_id: str, body: RejectIn, request: Request) -> dict[str, Any]:
        try:
            return desk(request).reject(queue_id, body.note)
        except QueueError as e:
            raise HTTPException(status_code=404 if "no queue item" in str(e) else 409, detail=str(e)) from e

    @app.get("/outbox")
    async def outbox(request: Request) -> list[dict[str, Any]]:
        return [o.model_dump() for o in desk(request).store.outbox()]

    @app.get("/bookings")
    async def bookings(request: Request) -> list[dict[str, Any]]:
        return desk(request).store.bookings()

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        d = desk(request)
        h = d.layer.health()
        return {"g0": h.model_dump(), "threshold": d.config.threshold, "router": d.router.name, "sends_anything": False}

    return app
