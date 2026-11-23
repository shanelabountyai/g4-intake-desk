"""Writes the synthetic labeled set, the hand-written recorded router responses and the synthetic contacts.

Run: `uv run python fixtures/make_fixtures.py`. Everything here is invented for the demo (D-2, D-13):
- names are "Synthetic Caller NN", emails are @example.com, phone numbers are in the 555-0100..0199 fictional range;
- no real person, number, address or business appears;
- `recorded.json` is hand-written in the router's output shape (D-6). It is not a recording of a live model, and some
  answers are deliberately wrong or unsure so the threshold, the emergency guard and the report have something to show.

Times are America/Chicago (CST -06:00 in January, CDT -05:00 in July). Business hours: Mon-Fri 08-17, Sat 09-13 (D-14).
2026-01-13 is a Tuesday; 2026-07-14 is a Tuesday.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def phone(n: int) -> str:
    return f"+1-312-555-{100 + n:04d}"


# contact number -> consent flags. Default: sms and email allowed.
CONSENT_OVERRIDES = {
    19: {"sms": True, "email": True, "do_not_contact": True},  # opted out of everything
    40: {"sms": False, "email": False},  # never consented to messages
}

W, S = "-06:00", "-05:00"  # winter (CST), summer (CDT)

# id, source, received_at, contact (None = unknown caller), reply, text, label, emergency, tags, recorded, duplicate_of
# recorded = (route, confidence, [reasons]) or a raw string for a malformed response
ROWS: list[tuple] = [
    # --- book: clear HVAC request, normal urgency, business hours ----------------------------------------------
    ("i01", "form", f"2026-01-13T09:12:00{W}", 1, "email",
     "Annual furnace tune-up for a two-story house, gas furnace about 8 years old. Any weekday morning next week works.",
     "book", False, ["heating", "maintenance"],
     ("book", 0.93, ["Clear maintenance request with system details", "Normal urgency, flexible timing", "Received in business hours"]), None),
    ("i02", "missed_call", f"2026-01-13T10:40:00{W}", 2, "sms",
     "Hi, this is about our heat pump. It's running but upstairs is a few degrees colder than downstairs. Not urgent, could someone come take a look this week? Call back at this number.",
     "book", False, ["heating", "heat_pump"],
     ("book", 0.86, ["Specific comfort issue, system still running", "Caller says not urgent and asks for a visit this week"]), None),
    ("i03", "form", f"2026-07-15T11:05:00{S}", 3, "email",
     "AC tune-up before the heat gets worse. Central air, 3-ton unit. Afternoons are best.",
     "book", False, ["cooling", "maintenance"],
     ("book", 0.91, ["Clear maintenance request with unit size", "Preferred time given", "Business hours"]), None),
    ("i04", "form", f"2026-07-14T14:20:00{S}", 4, "sms",
     "Thermostat replacement: want to swap our old dial thermostat for a programmable one. You can come any day this week.",
     "book", False, ["controls"],
     ("book", 0.88, ["Specific install request", "Flexible availability this week"]), None),
    ("i05", "missed_call", f"2026-07-15T09:30:00{S}", 5, "sms",
     "Calling to set up a maintenance visit for the AC in our rental unit. Tenant is home on weekdays.",
     "book", False, ["cooling", "maintenance"],
     ("book", 0.84, ["Maintenance visit requested", "Access window given (weekdays)"]), None),
    ("i06", "form", f"2026-01-14T15:10:00{W}", 6, "email",
     "Furnace filter change and inspection, we're on the maintenance plan. Thursday or Friday please.",
     "book", False, ["heating", "maintenance"],
     ("book", 0.90, ["Plan customer asking for routine inspection", "Days given"]), None),
    ("i07", "form", f"2026-07-16T10:00:00{S}", 7, "sms",
     "Mini split in the garage is not cooling as well as last summer. Still works. Would like someone out this week.",
     "book", False, ["cooling", "mini_split"],
     ("book", 0.78, ["Performance issue, unit still running", "Visit requested this week"]), None),
    ("i08", "form", f"2026-01-15T13:30:00{W}", 8, "email",
     "Need an install estimate for a new furnace. Ours is 22 years old but still working. Can someone come do an assessment?",
     "book", False, ["heating", "estimate_visit"],
     ("follow_up", 0.72, ["Asks about pricing for a new furnace", "Treating as price inquiry; send pricing info"]), None),
    ("i09", "missed_call", f"2026-01-17T10:15:00{W}", 9, "sms",
     "The furnace is short cycling, turns on and off every few minutes. House is still warm. Can someone come Monday?",
     "book", False, ["heating", "saturday_hours"],
     ("book", 0.80, ["Specific symptom, house still warm", "Caller proposes Monday", "Saturday business hours"]), None),
    ("i10", "form", f"2026-07-17T08:45:00{S}", 10, "email",
     "Our AC condensate line drips into the pan a lot. Nothing on the floor. Schedule a check when you can.",
     "book", False, ["cooling"],
     ("book", 0.82, ["Minor issue contained in the pan", "No urgency stated"]), None),
    # --- follow up: price shopping, vague, missing details, after hours not urgent, wrong trade -----------------
    ("i11", "form", f"2026-07-14T12:00:00{S}", 11, "sms",
     "How much do you charge for an AC tune-up? Comparing a few companies.",
     "follow_up", False, ["price_shopping"],
     ("follow_up", 0.90, ["Price shopping, no service requested yet"]), None),
    ("i12", "missed_call", f"2026-01-13T16:20:00{W}", None, "sms",
     "Hey it's about the thing at the house, call me back.",
     "follow_up", False, ["vague", "unknown_caller"],
     ("follow_up", 0.45, ["No service, system or urgency stated", "Unknown caller", "Not enough to act on"]), None),
    ("i13", "form", f"2026-01-13T21:40:00{W}", 13, "email",
     "Would like to schedule a furnace tune-up sometime in the next couple of weeks.",
     "follow_up", False, ["after_hours", "maintenance"],
     ("follow_up", 0.87, ["After hours, not urgent", "Confirm a slot in the morning"]), None),
    ("i14", "missed_call", f"2026-07-18T19:30:00{S}", None, "sms",
     "Hi, the AC is a little noisy when it starts up, still cooling fine. Call me next week.",
     "follow_up", False, ["after_hours", "unknown_caller"],
     ("follow_up", 0.83, ["After hours, still cooling, caller asks for next week"]), None),
    ("i15", "form", f"2026-07-15T13:00:00{S}", 15, "sms",
     "AC not working right.",
     "follow_up", False, ["missing_details"],
     ("follow_up", 0.74, ["Too little detail to book", "Ask what the unit is doing"]), None),
    ("i16", "form", f"2026-01-14T10:30:00{W}", 16, "email",
     "Do you offer financing on new heat pumps? What's a ballpark for a 3-ton?",
     "follow_up", False, ["price_shopping", "heat_pump"],
     ("follow_up", 0.88, ["Financing and price question, no visit requested"]), None),
    ("i17", "form", f"2026-07-14T10:10:00{S}", 17, "sms",
     "Can you replace the garbage disposal in my kitchen sink?",
     "follow_up", False, ["wrong_trade", "plumbing"],
     ("follow_up", 0.92, ["Plumbing request, outside HVAC", "Not urgent"]), None),
    ("i18", "missed_call", f"2026-01-14T11:00:00{W}", 18, "sms",
     "I need an electrician to add an outlet in my garage.",
     "follow_up", False, ["wrong_trade", "electrical"],
     ("follow_up", 0.90, ["Electrical work, outside HVAC", "Not urgent"]), None),
    ("i19", "form", f"2026-07-16T15:45:00{S}", 19, "email",
     "Looking for someone to clean out our gutters and fix a roof shingle.",
     "follow_up", False, ["wrong_trade", "roofing", "do_not_contact"],
     ("follow_up", 0.93, ["Roofing/gutter work, outside HVAC"]), None),
    ("i20", "form", f"2026-01-18T09:00:00{W}", 20, "email",
     "Can I get on the schedule for a duct inspection? Moved in last month.",
     "follow_up", False, ["after_hours", "sunday"],
     ("book", 0.74, ["Clear inspection request", "Book next available slot"]), None),
    ("i21", "missed_call", f"2026-07-15T12:30:00{S}", 21, "sms",
     "Yeah I filled out something on your site before, just checking.",
     "follow_up", False, ["vague"],
     ("follow_up", 0.62, ["Refers to an earlier form we can't match", "No request stated"]), None),
    ("i22", "form", f"2026-07-17T16:30:00{S}", 22, "sms",
     "Need service.",
     "follow_up", False, ["missing_details", "threshold_boundary"],
     ("follow_up", 0.70, ["No system or symptom given", "Ask for details"]), None),
    ("i23", "form", f"2026-01-15T09:50:00{W}", 23, "sms",
     "What's your diagnostic fee?",
     "follow_up", False, ["price_shopping"],
     ("follow_up", 0.86, ["Fee question only"]), None),
    # --- escalate: emergencies (many after hours) -------------------------------------------------------------
    ("i24", "missed_call", f"2026-01-17T23:10:00{W}", 24, "sms",
     "No heat at all, the furnace won't turn on. It's 8 degrees outside and we have a newborn.",
     "escalate", True, ["after_hours", "emergency", "no_heat"],
     ("escalate", 0.97, ["No heat in sub-freezing weather", "Infant in the home", "After hours: alert on-call"]), None),
    ("i25", "form", f"2026-01-18T02:30:00{W}", 25, "sms",
     "I smell gas near the furnace in the basement.",
     "escalate", True, ["after_hours", "emergency", "gas"],
     ("escalate", 0.98, ["Possible gas leak", "Safety hazard"]), None),
    ("i26", "missed_call", f"2026-01-13T14:00:00{W}", 26, "sms",
     "Carbon monoxide detector is going off and it's near the furnace room.",
     "escalate", True, ["emergency", "co"],
     ("escalate", 0.97, ["CO alarm near furnace", "Life-safety hazard"]), None),
    ("i27", "missed_call", f"2026-07-19T15:00:00{S}", 27, "sms",
     "AC quit completely, it's 101 out and my mother is 88 and on oxygen at home.",
     "escalate", True, ["after_hours", "sunday", "emergency", "no_cooling_vulnerable"],
     ("escalate", 0.90, ["No cooling in extreme heat", "Vulnerable occupant on oxygen"]), None),
    ("i28", "form", f"2026-07-14T22:15:00{S}", 28, "sms",
     "Water pouring from the ceiling under the attic air handler.",
     "escalate", True, ["after_hours", "emergency", "active_leak"],
     ("escalate", 0.93, ["Active leak from air handler", "Property damage in progress"]), None),
    ("i29", "missed_call", f"2026-01-14T06:10:00{W}", 29, "sms",
     "Furnace made a loud bang and now there's a burning smell coming from the vents.",
     "escalate", True, ["after_hours", "emergency", "router_miss"],
     ("book", 0.76, ["Noise from furnace", "Schedule a diagnostic visit"]), None),
    ("i30", "form", f"2026-01-13T12:40:00{W}", 30, "sms",
     "Heat went out this morning, house is down to 50 degrees, elderly residents.",
     "escalate", True, ["emergency", "no_heat"],
     ("escalate", 0.91, ["Heating outage in winter", "Elderly residents"]), None),
    ("i31", "missed_call", f"2026-07-18T01:20:00{S}", 31, "sms",
     "Breaker for the AC keeps tripping and I saw sparks at the outdoor unit.",
     "escalate", True, ["after_hours", "emergency", "electrical_hazard"],
     ("escalate", 0.95, ["Sparks at condenser", "Fire risk"]), None),
    ("i32", "missed_call", f"2026-01-17T20:00:00{W}", 32, "sms",
     "Pipe burst in the basement, water everywhere, do you do plumbing?",
     "escalate", True, ["after_hours", "emergency", "wrong_trade", "plumbing"],
     ("escalate", 0.88, ["Active flooding", "Plumbing, outside HVAC, but an emergency: owner decides referral"]), None),
    ("i33", "form", f"2026-01-18T07:30:00{W}", 33, "sms",
     "furnace off again, real cold in here, kids at home",
     "escalate", True, ["after_hours", "emergency", "vague_emergency"],
     ("follow_up", 0.66, ["Possible repeat issue", "Ask for more detail"]), None),
    # --- escalate: angry customers / disputes ----------------------------------------------------------------
    ("i34", "form", f"2026-07-15T10:20:00{S}", 34, "email",
     "Your tech came Tuesday and the AC is worse now. This is the second time. I want a manager to call me today.",
     "escalate", False, ["angry", "callback_complaint"],
     ("escalate", 0.90, ["Angry repeat-visit complaint", "Asks for a manager"]), None),
    ("i35", "missed_call", f"2026-01-14T16:45:00{W}", 35, "sms",
     "I was charged twice for last week's furnace repair and nobody returns my calls.",
     "escalate", False, ["angry", "billing"],
     ("escalate", 0.88, ["Billing dispute", "Customer frustrated by no callback"]), None),
    ("i36", "form", f"2026-07-16T09:15:00{S}", 36, "sms",
     "I'm going to leave a review about how your crew left a mess after the AC install. Call me.",
     "escalate", False, ["angry", "review_threat"],
     ("follow_up", 0.68, ["Customer wants a callback about install cleanup"]), None),
    # --- duplicates ----------------------------------------------------------------------------------------------
    ("i37", "missed_call", f"2026-01-17T23:25:00{W}", 24, "sms",
     "Called 15 minutes ago, still no heat, please call back!",
     "escalate", True, ["after_hours", "emergency", "duplicate"],
     ("escalate", 0.96, ["Repeat call, no heat", "Same caller as an open emergency"]), "i24"),
    ("i38", "form", f"2026-01-13T09:20:00{W}", 1, "email",
     "Annual furnace tune-up for a two-story house, gas furnace about 8 years old. Any weekday morning next week works.",
     "book", False, ["duplicate", "resubmitted_form"],
     ("book", 0.92, ["Clear maintenance request", "Business hours"]), "i01"),
    ("i39", "form", f"2026-07-14T12:05:00{S}", 11, "sms",
     "how much for an AC tune up",
     "follow_up", False, ["duplicate", "price_shopping"],
     ("follow_up", 0.89, ["Price question"]), "i11"),
    # --- consent edge -------------------------------------------------------------------------------------------
    ("i40", "form", f"2026-07-16T11:30:00{S}", 40, "sms",
     "Schedule a heat pump maintenance visit, any morning next week is fine.",
     "book", False, ["no_consent", "heat_pump"],
     ("book", 0.90, ["Clear maintenance request", "Flexible timing"]), None),
]


def main() -> None:
    intakes, labels, recorded = [], {}, {}
    contacts: dict[int, dict] = {}
    for (iid, source, at, cnum, reply, text, label, emergency, tags, rec, dup) in ROWS:
        item: dict = {"id": iid, "source": source, "received_at": at, "text": text, "reply_channel": reply}
        if cnum is None:
            item["phone"] = phone(90 + int(iid[1:]) % 10)  # fictional numbers not in the contact seed
        else:
            item["phone"] = phone(cnum)
            if source == "form" and reply == "email":
                item["email"] = f"synthetic.caller{cnum:02d}@example.com"
            contacts.setdefault(cnum, {})
        intakes.append(item)
        labels[iid] = {"route": label, "emergency": emergency, "tags": tags, "duplicate_of": dup}
        route, conf, reasons = rec
        recorded[f"router:{iid}"] = {"route": route, "confidence": conf, "reasons": reasons}
    out_contacts = []
    for n in sorted(contacts):
        flags = CONSENT_OVERRIDES.get(n, {})
        out_contacts.append({
            "contact_id": f"g4-c{n:02d}",
            "email": f"synthetic.caller{n:02d}@example.com",
            "phone": phone(n),
            "name": f"Synthetic Caller {n:02d}",
            "title": None,
            "company": None,
            "do_not_contact": bool(flags.get("do_not_contact", False)),
            "consent_recorded_at": "2026-01-01T00:00:00Z",
            "source": "g4-intake-desk synthetic seed (fixtures/make_fixtures.py)",
            "consent": {"sms": flags.get("sms", True), "email": flags.get("email", True)},
        })
    (HERE / "intakes.json").write_text(json.dumps({
        "_about": "40 synthetic intakes for the G4 intake desk, hand-labeled (D-2, D-13). Generated by fixtures/make_fixtures.py. Synthetic only.",
        "intakes": intakes, "labels": labels}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (HERE / "recorded.json").write_text(json.dumps({
        "_about": "Hand-written router responses in the router_v1 shape, keyed router:<intake id> (D-6). NOT a recording of a live model; "
                  "some answers are deliberately wrong or unsure (i08, i20, i29, i33, i36, and low-confidence i12, i21).",
        "model": "claude-sonnet-5-5", "responses": recorded}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPO / "contacts" / "g4_contacts.json").write_text(json.dumps({
        "_about": "Synthetic contacts for G4, seeded into G0 through its own loader (D-9). All @example.com, fictional 555-01xx numbers. "
                  "`phone` is read by the G4 caller-ID lookup; G0's loader ignores it.",
        "contacts": out_contacts}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(intakes)} intakes, {len(recorded)} recorded responses, {len(out_contacts)} contacts")


if __name__ == "__main__":
    main()
