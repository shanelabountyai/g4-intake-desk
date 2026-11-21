"""Safety invariants (T2), landed before any route action existed.

1. `emergency_signals`: a deterministic guard, independent of the router (D-11). Any hit forces escalate.
2. `decide_final`: the fail-closed order — invalid router output, emergency guard, below threshold, then the router's
   route (D-12). Nothing below the threshold is ever booked (AC3).
3. `FORBIDDEN_MODULES`: network, SMS, mail and calendar clients the package must never import (D-18). Pinned by
   `tests/test_safety.py`, which scans every module's imports.

These are G4's own safety rules. They are not a shared-layer capability and are never copied into the router prompt.
"""

from __future__ import annotations

import re
from typing import Literal

from intake_desk.models import FinalDecision, Route, RouterDecision

Override = Literal["router_invalid", "emergency_guard", "below_threshold"]

DEFAULT_THRESHOLD = 0.7  # D-3, provisional

# Strong hazard signals: any one is an emergency on its own.
_HAZARD = {
    "gas_smell": r"\b(smell(s|ing)?|odou?r) (of |like )?(natural )?gas\b|\bgas (smell|odou?r|leak)\b",
    "carbon_monoxide": r"\bcarbon monoxide\b|\bco (alarm|detector)\b",
    "burning_or_smoke": r"\bburning smell\b|\bsmell(s|ing)? (of |like )?burning\b|\bsmoke\b",
    "sparks": r"\bspark(s|ing)?\b",
    "water_pouring": r"\bwater (is )?(pouring|everywhere|gushing|flooding)\b|\b(pipe|pipes) (has |have )?burst\b|\bburst pipe\b|\bflood(ed|ing)\b",
    "no_heat": r"\bno heat\b|\bheat (went|is|has gone) out\b|\bfurnace (is )?(off|out|dead)\b|\bfurnace (won'?t|will not) (turn|come|start)\b",
}
# An outage alone is not always an emergency (a summer AC outage for a healthy adult may be next-day work);
# an outage plus a vulnerability or an extreme temperature is.
_OUTAGE = r"\b(ac|a/c|air|air conditioning|cooling|heat pump|furnace)\b.{0,30}\b(quit|died|dead|stopped|out|not working|won'?t (turn|come) on)\b"
_VULNERABLE = (r"\b(newborn|infant|baby|elderly|oxygen|medical|disabled|pregnant)\b"
               r"|\b(1[0-2]\d|9[5-9]) ?(degrees|°|out)\b|\b([0-9]|1[0-9]) ?(degrees|°) (outside|out)\b")


def emergency_signals(text: str) -> list[str]:
    """Names of the emergency signals found in `text` (empty when none)."""
    t = text.lower()
    hits = [name for name, pat in _HAZARD.items() if re.search(pat, t)]
    if re.search(_OUTAGE, t) and re.search(_VULNERABLE, t):
        hits.append("outage_with_vulnerability")
    return hits


def decide_final(router: RouterDecision | None, text: str, threshold: float = DEFAULT_THRESHOLD,
                 invalid_reason: str | None = None) -> FinalDecision:
    """The fail-closed decision order (D-12). `router is None` means its output was invalid."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be within 0..1, got {threshold}")
    signals = emergency_signals(text)
    if router is None:
        reasons = [f"router output invalid, escalated with confidence 0: {invalid_reason or 'unknown error'}"]
        if signals:
            reasons.append(f"emergency guard: {', '.join(signals)}")
        return FinalDecision(route="escalate", confidence=0.0, reasons=reasons, router=None,
                             overrides=["router_invalid"] + (["emergency_guard"] if signals else []),
                             emergency_signals=signals, threshold=threshold)
    reasons = list(router.reasons)
    overrides: list[Override] = []
    route: Route = router.route
    if signals and route != "escalate":
        overrides.append("emergency_guard")
        reasons.append(f"emergency guard overrode router route '{router.route}': {', '.join(signals)}")
        route = "escalate"
    if router.confidence < threshold and route != "escalate":
        overrides.append("below_threshold")
        reasons.append(f"confidence {router.confidence:.2f} < threshold {threshold:.2f}: escalated instead of '{router.route}'")
        route = "escalate"
    return FinalDecision(route=route, confidence=router.confidence, reasons=reasons, router=router,
                         overrides=overrides, emergency_signals=signals, threshold=threshold)


# Modules the package must never import: no code path may reach a real phone, inbox, calendar or HTTP endpoint (D-18).
FORBIDDEN_MODULES = frozenset({
    "requests", "httpx", "aiohttp", "urllib.request", "urllib3", "http.client", "smtplib", "imaplib", "poplib",
    "socket", "ftplib", "telnetlib", "twilio", "sendgrid", "boto3", "googleapiclient", "google.oauth2",
    "msal", "o365", "caldav", "icalendar", "exchangelib", "slack_sdk", "websockets",
})
