"""Shapes: the intake, the router contract (D-19), the final decision (D-12) and the per-intake outcome."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

REPO_DIR = Path(__file__).resolve().parents[2]

Route = Literal["book", "follow_up", "escalate"]
ROUTES: tuple[Route, ...] = ("book", "follow_up", "escalate")
Source = Literal["form", "missed_call"]
ReplyChannel = Literal["sms", "email"]


class Intake(BaseModel):
    """One missed-call transcript or web form, as the webhooks receive it. Synthetic only."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    source: Source
    received_at: datetime = Field(description="ISO 8601 with offset; business hours are judged in the business's zone (D-14).")
    text: str = Field(min_length=1, max_length=4000)
    phone: str | None = Field(default=None, description="Caller ID or form phone; synthetic 555-01xx numbers only.")
    email: str | None = None
    reply_channel: ReplyChannel = "sms"

    @field_validator("received_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("received_at must carry a UTC offset")
        return v


class RouterOutputInvalid(ValueError):
    """The router's output is not JSON or does not match router_v1 (D-19)."""


class RouterDecision(BaseModel):
    """The router contract, published as schemas/router_v1.json."""

    model_config = ConfigDict(extra="forbid")

    route: Route
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(min_length=1, max_length=5)

    @field_validator("reasons")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if any(not r.strip() for r in v):
            raise ValueError("every reason must be a non-empty string")
        return v

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        schema = cls.model_json_schema()
        schema["$id"] = "router_v1"
        schema["title"] = "RouterDecision v1"
        return schema


def parse_router(raw: str | dict[str, Any]) -> RouterDecision:
    """Validate raw router output. Anything else raises RouterOutputInvalid; the desk then escalates (D-12)."""
    data: Any = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RouterOutputInvalid(f"router output is not JSON: {e.msg}") from e
    if not isinstance(data, dict):
        raise RouterOutputInvalid(f"router output must be a JSON object, got {type(data).__name__}")
    try:
        return RouterDecision.model_validate(data)
    except ValidationError as e:
        raise RouterOutputInvalid(f"router output fails router_v1: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}") from e


class FinalDecision(BaseModel):
    """What the desk does, and why. Keeps the router's raw answer next to the override (D-12)."""

    model_config = ConfigDict(extra="forbid")

    route: Route
    confidence: float
    reasons: list[str]
    router: RouterDecision | None = Field(description="Null when the router output was invalid.")
    overrides: list[Literal["router_invalid", "emergency_guard", "below_threshold", "after_hours"]] = Field(default_factory=list)
    emergency_signals: list[str] = Field(default_factory=list)
    threshold: float


class OutboundRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outbound_id: str
    intake_id: str
    kind: Literal["follow_up", "booking_confirmation", "owner_alert"]
    channel: Literal["sms", "email", "internal"]
    to: str = Field(description="A contact id, or 'owner' / 'on_call_tech'. Never a raw number or address.")
    template: str
    body: str
    status: Literal["logged_not_sent", "blocked_consent", "blocked_brand", "suppressed_duplicate"]
    detail: str = ""
    logged_at: str


class Outcome(BaseModel):
    """Everything that happened to one intake."""

    model_config = ConfigDict(extra="forbid")

    intake_id: str
    contact_id: str | None
    after_hours: bool
    duplicate_of: str | None
    decision: FinalDecision
    booking_id: str | None = None
    queue_id: str | None = None
    outbound: list[OutboundRecord] = Field(default_factory=list)
    status: Literal["booked", "follow_up_logged", "queued", "suppressed_duplicate", "blocked"]
