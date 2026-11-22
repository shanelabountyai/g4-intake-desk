"""The desk: one intake in, one route acted on, everything logged (T6).

    intake ─► contact lookup (G4 seed in G0) ─► router (recorded | Agent SDK) ─► parse_router (router_v1)
           ─► decide_final: invalid → guard → threshold → router route (safety.py, D-12)
           ─► G0 observability (route, confidence, cost) + G0 measurement intake.routed
           ─► book       : first free synthetic slot, confirmation → consent + brand → outbox
              follow_up  : template → consent + brand → outbox (brand failure → queue)
              escalate   : queue (pending owner approve/reject) + internal owner/on-call alert → outbox
           duplicates of a book/follow-up create nothing new (D-15); every outbound is logged, never sent (D-18).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import anyio

from intake_desk import templates
from intake_desk.layer import Layer
from intake_desk.models import REPO_DIR, FinalDecision, Intake, OutboundRecord, Outcome, RouterDecision, RouterOutputInvalid, parse_router
from intake_desk.router import Router, RouterCallError, user_prompt
from intake_desk.safety import DEFAULT_THRESHOLD, decide_final
from intake_desk.store import QueueError, Store, new_id, now_iso

CONFIG_FILE = REPO_DIR / "config" / "business.json"
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
OwnerAction = Literal["book", "follow_up", "owner_handled"]


@dataclass
class DeskConfig:
    timezone: str = "America/Chicago"
    hours: dict[str, list[str] | None] = field(default_factory=dict)
    on_call: bool = True
    slot_times: list[str] = field(default_factory=lambda: ["08:00", "10:00", "13:00", "15:00"])
    slot_days_ahead: int = 3
    duplicate_window_hours: int = 24
    threshold: float = DEFAULT_THRESHOLD
    router_timeout_s: float = 60.0  # a hung router call fails closed (escalates) instead of blocking the webhook

    @classmethod
    def load(cls, path: Path | None = None, threshold: float | None = None) -> DeskConfig:
        doc = json.loads((path or CONFIG_FILE).read_text(encoding="utf-8"))
        return cls(timezone=doc["timezone"], hours=doc["hours"], on_call=bool(doc["on_call"]), slot_times=list(doc["slot_times"]),
                   slot_days_ahead=int(doc["slot_days_ahead"]), duplicate_window_hours=int(doc["duplicate_window_hours"]),
                   threshold=DEFAULT_THRESHOLD if threshold is None else threshold)

    def local(self, dt: datetime) -> datetime:
        return dt.astimezone(ZoneInfo(self.timezone))

    def after_hours(self, dt: datetime) -> bool:
        loc = self.local(dt)
        span = self.hours.get(DAYS[loc.weekday()])
        if not span:
            return True
        start, end = (time.fromisoformat(x) for x in span)
        return not (start <= loc.time() < end)


class Desk:
    def __init__(self, layer: Layer, store: Store, router: Router, config: DeskConfig, run_id: str) -> None:
        self.layer, self.store, self.router, self.config, self.run_id = layer, store, router, config, run_id

    # -- one intake ------------------------------------------------------------

    async def process(self, intake: Intake) -> Outcome:
        cfg = self.config
        contact_id = self.layer.contact_for(intake.phone, intake.email)
        local = cfg.local(intake.received_at)
        after = cfg.after_hours(intake.received_at)
        prompt = user_prompt(intake, local.strftime("%a %Y-%m-%d %H:%M %Z"), after, cfg.on_call)

        router_decision: RouterDecision | None = None
        invalid: str | None = None
        model, tin, tout, cost, dur, status = getattr(self.router, "model", None), 0, 0, 0.0, None, "ok"
        try:
            with anyio.fail_after(cfg.router_timeout_s):
                call = await self.router.route(intake, prompt)
            model, tin, tout, dur = call.model, call.input_tokens, call.output_tokens, call.duration_ms
            if self.router.measured:
                cost = call.sdk_cost_usd if call.sdk_cost_usd is not None else self.layer.cost_usd(call.model, tin, tout)
            router_decision = parse_router(call.raw)
        except (RouterCallError, RouterOutputInvalid) as e:
            invalid, status = str(e), "error"
        except TimeoutError:
            invalid, status = f"router timed out after {cfg.router_timeout_s:g}s", "error"
        except Exception as e:  # noqa: BLE001 - any router failure must fail closed (escalate), never lose the intake
            invalid, status = f"router error: {type(e).__name__}: {e}", "error"
        decision = decide_final(router_decision, intake.text, cfg.threshold, invalid_reason=invalid)

        note = {"intake": intake.id, "router_route": router_decision.route if router_decision else None,
                "confidence": decision.confidence, "final_route": decision.route, "overrides": decision.overrides,
                "reasons": decision.reasons, "path": "measured" if self.router.measured else "recorded"}
        self.layer.log_call(run_id=self.run_id, step=f"route:{intake.id}", model=model, input_tokens=tin, output_tokens=tout,
                            cost_usd=cost, status=status, duration_ms=dur, note=json.dumps(note))

        dup = self.store.find_duplicate(intake.id, contact_id, intake.received_at, cfg.duplicate_window_hours)
        outcome = Outcome(intake_id=intake.id, contact_id=contact_id, after_hours=after,
                          duplicate_of=dup["intake_id"] if dup else None, decision=decision, status="queued")
        if decision.route == "escalate":
            self._escalate(intake, contact_id, decision, outcome, after)
        elif (prior := self.store.prior_action(intake.id, contact_id, intake.received_at, cfg.duplicate_window_hours,
                                               decision.route)) is not None:
            outcome.outbound.append(self._log(intake, kind="follow_up" if decision.route == "follow_up" else "booking_confirmation",
                                              channel=intake.reply_channel, to=contact_id or "unknown_caller", template="(none)", body="",
                                              status="suppressed_duplicate", detail=f"duplicate of {prior} within "
                                              f"{cfg.duplicate_window_hours}h; nothing new booked or sent (D-15)"))
            outcome.status = "suppressed_duplicate"
        elif decision.route == "book":
            self._book(intake, contact_id, outcome)
        else:
            self._follow_up(intake, contact_id, decision.reasons, after, outcome)

        self.layer.record("intake.routed", {
            "intake_id": intake.id, "source": intake.source, "router_route": note["router_route"], "confidence": decision.confidence,
            "final_route": decision.route, "overrides": decision.overrides, "after_hours": after, "duplicate": dup is not None,
            "status": outcome.status, "outbound_statuses": [o.status for o in outcome.outbound]}, run_id=self.run_id)
        self.store.remember_intake(intake.id, contact_id, intake.received_at, decision.route, outcome.status, intake.model_dump_json())
        return outcome

    # -- actions ---------------------------------------------------------------

    def _escalate(self, intake: Intake, contact_id: str | None, d: FinalDecision, outcome: Outcome, after: bool) -> None:
        proposed: str
        if d.router is not None and d.overrides == ["below_threshold"]:
            proposed, why = d.router.route, f"low confidence ({d.confidence:.2f} < {d.threshold:.2f})"
        elif "emergency_guard" in d.overrides or (d.router is not None and d.router.route == "escalate" and d.emergency_signals):
            proposed, why = "owner_handled", f"possible emergency ({', '.join(d.emergency_signals)})"
        elif "router_invalid" in d.overrides:
            proposed, why = "owner_handled", "router output invalid"
        else:
            proposed, why = "owner_handled", "router chose escalate"
        outcome.queue_id = self.store.enqueue(intake.id, contact_id, proposed, why, d.reasons)
        target = "on_call_tech" if (after and self.config.on_call) else "owner"
        body = templates.render_owner_alert(intake, self.config.local(intake.received_at).strftime("%a %H:%M"), why, d.reasons)
        outcome.outbound.append(self._log(intake, kind="owner_alert", channel="internal", to=target, template="owner_alert", body=body,
                                          status="logged_not_sent", detail=f"queue {outcome.queue_id}; internal alert, not consent-checked (D-16)"))
        outcome.status = "queued"

    def _book(self, intake: Intake, contact_id: str | None, outcome: Outcome) -> None:
        cfg = self.config
        booking_id, start = self.store.book_first_free(intake.id, contact_id, intake.received_at, cfg.timezone, cfg.slot_times, cfg.slot_days_ahead)
        outcome.booking_id = booking_id
        rec = self._customer_message(intake, contact_id, "booking_confirmation", "booking_confirmation",
                                     templates.render_confirmation(start.strftime("%A %B %d at %I:%M %p").replace(" 0", " ")))
        outcome.outbound.append(rec)
        outcome.status = "booked"
        if rec.status != "logged_not_sent":
            # The slot is held, but the customer cannot be told by message: a person confirms by phone (D-25).
            outcome.queue_id = self.store.enqueue(intake.id, contact_id, "owner_handled",
                                                  f"booking held but confirmation {rec.status}: confirm by phone", [rec.detail])

    def _follow_up(self, intake: Intake, contact_id: str | None, reasons: list[str], after: bool, outcome: Outcome) -> None:
        name = templates.pick_follow_up(None, after, reasons)
        rec = self._customer_message(intake, contact_id, "follow_up", name, templates.render_follow_up(name))
        outcome.outbound.append(rec)
        outcome.status = "follow_up_logged"
        if rec.status == "blocked_brand":
            outcome.queue_id = self.store.enqueue(intake.id, contact_id, "owner_handled", "follow-up blocked by brand policy", [rec.detail])
            outcome.status = "blocked"

    def _customer_message(self, intake: Intake, contact_id: str | None, kind: Literal["follow_up", "booking_confirmation"],
                          template: str, body: str) -> OutboundRecord:
        consent_ch, brand_ch = ("sms", "other") if intake.reply_channel == "sms" else ("email", "email")
        to = contact_id or "unknown_caller"
        c = self.layer.consent(contact_id, consent_ch)
        if not c.ok or not c.allowed:
            reason = c.reason if c.ok else (c.error.code if c.error else "refused")
            return self._log(intake, kind=kind, channel=intake.reply_channel, to=to, template=template, body=body,
                             status="blocked_consent", detail=f"audience.consent {consent_ch}: {reason}")
        ok, problems = self.layer.brand_gate(body, brand_ch)
        if not ok:
            return self._log(intake, kind=kind, channel=intake.reply_channel, to=to, template=template, body=body,
                             status="blocked_brand", detail="; ".join(problems))
        return self._log(intake, kind=kind, channel=intake.reply_channel, to=to, template=template, body=body,
                         status="logged_not_sent", detail=f"consent {consent_ch}: consented; brand v1 + g4-followup-1 passed")

    def _log(self, intake: Intake, **kw: Any) -> OutboundRecord:
        return self.store.log_outbound(OutboundRecord(outbound_id=new_id("out"), intake_id=intake.id, logged_at=now_iso(), **kw))

    # -- owner decisions (D-20) -------------------------------------------------

    def approve(self, queue_id: str, action: OwnerAction | None = None, note: str | None = None) -> dict[str, Any]:
        item = self.store.queue_item(queue_id)
        if item["status"] != "pending":
            raise QueueError(f"queue item {queue_id} is already {item['status']}")
        chosen: str = action or item["proposed_action"]
        if chosen not in ("book", "follow_up", "owner_handled"):
            raise ValueError(f"unknown owner action {chosen!r}")
        intake = Intake.model_validate_json(self.store.intake_payload(item["intake_id"]))
        outcome = Outcome(intake_id=intake.id, contact_id=item["contact_id"], after_hours=False, duplicate_of=None,
                          decision=FinalDecision(route="escalate", confidence=0.0, reasons=item["reasons"], router=None, threshold=self.config.threshold),
                          status="queued")
        if chosen == "book":
            self._book(intake, item["contact_id"], outcome)
        elif chosen == "follow_up":
            self._follow_up(intake, item["contact_id"], item["reasons"], self.config.after_hours(intake.received_at), outcome)
        decided = self.store.decide(queue_id, "approved", chosen, note)
        self.layer.record("intake.owner_decision", {"queue_id": queue_id, "intake_id": intake.id, "decision": "approved", "action": chosen},
                          run_id=self.run_id)
        return {"queue": decided, "booking_id": outcome.booking_id, "outbound": [o.model_dump() for o in outcome.outbound]}

    def reject(self, queue_id: str, note: str | None = None) -> dict[str, Any]:
        decided = self.store.decide(queue_id, "rejected", None, note)
        self.layer.record("intake.owner_decision", {"queue_id": queue_id, "intake_id": decided["intake_id"], "decision": "rejected"},
                          run_id=self.run_id)
        return {"queue": decided, "booking_id": None, "outbound": []}
