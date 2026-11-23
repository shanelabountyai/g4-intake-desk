"""Fixed customer-message and owner-alert templates (D-17).

Templates are filled with intake facts only; no model writes customer text in v1. Every customer message is still
checked by G0 brand.policy (v1 + g4-followup-1) and G0 audience.consent before it is logged, so a template edit that
breaks tone is caught there, not here.
"""

from __future__ import annotations

from intake_desk.models import Intake

BUSINESS = "Example Comfort HVAC"

FOLLOW_UP = {
    "missing_details": "Hi, this is {business}. Thanks for reaching out. So we can help, could you reply with what the system is doing, "
                       "the type of system (furnace, AC, heat pump) and a good time to reach you?",
    "price_inquiry": "Hi, this is {business}. Thanks for asking about pricing. A team member will call you during business hours to go "
                     "over options. If you would like a visit, reply with a couple of times that work.",
    "after_hours": "Hi, this is {business}. We got your message after hours. We will reach out when we open to confirm a time. "
                   "If anything changes or it becomes urgent, call us back.",
    "out_of_scope": "Hi, this is {business}. Thanks for reaching out. We only handle heating and cooling, so we are not the right fit "
                    "for this job. A team member can suggest where to look if you reply.",
    "general": "Hi, this is {business}. Thanks for your message. A team member will follow up during business hours.",
}

BOOKING_CONFIRMATION = ("Hi, this is {business}. You are on the schedule for {slot_local}. The technician will confirm the "
                        "arrival window the day before. Reply to this message to change the time.")

OWNER_ALERT = "ESCALATION {intake_id} ({source}, {received_local}): {why}. Reasons: {reasons}. Awaiting approve or reject in the queue."


def pick_follow_up(tags_hint: str | None, after_hours: bool, reasons: list[str]) -> str:
    """Choose a follow-up template from the router's reasons (lower-cased keyword match) and the clock."""
    joined = " ".join(reasons).lower() + " " + (tags_hint or "")
    if any(w in joined for w in ("outside hvac", "out of scope", "wrong trade", "plumbing", "electrical", "roofing")):
        return "out_of_scope"
    if any(w in joined for w in ("price", "fee", "financing", "cost", "quote")):
        return "price_inquiry"
    if after_hours:
        return "after_hours"
    if any(w in joined for w in ("detail", "vague", "no request", "not enough", "no service", "no system")):
        return "missing_details"
    return "general"


def render_follow_up(template: str) -> str:
    return FOLLOW_UP[template].format(business=BUSINESS)


def render_confirmation(slot_local: str) -> str:
    return BOOKING_CONFIRMATION.format(business=BUSINESS, slot_local=slot_local)


def render_owner_alert(intake: Intake, received_local: str, why: str, reasons: list[str]) -> str:
    return OWNER_ALERT.format(intake_id=intake.id, source=intake.source, received_local=received_local, why=why,
                              reasons="; ".join(reasons))
