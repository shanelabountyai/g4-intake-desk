"""The router agent behind one interface (D-6, D-7, D-19).

- `RecordedRouter` answers from `fixtures/recorded.json`, keyed `router:<intake id>`. No network, no key, zero usage.
  The file is hand-written in the router_v1 shape; it is not a recording of a live model.
- `AgentSdkRouter` runs one turn in a Claude Agent SDK session (`claude_agent_sdk.query`): its own system prompt, no
  built-in tools, structured output against router_v1, a budget cap. Implemented, **never run in this build**; it
  refuses to construct without `ANTHROPIC_API_KEY`.
- `RecordingRouter` wraps a live router and saves what it got in the recorded file's shape.

The prompt carries pointers, never rules: consent and tone live in G0 (audience.consent, brand.policy), the emergency
guard and the threshold live in `safety.py`, and all of them are applied after the router in code
(`tests/test_safety.py` pins that no rule text leaks in here).
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from intake_desk.models import REPO_DIR, Intake, RouterDecision

RECORDED_FILE = REPO_DIR / "fixtures" / "recorded.json"
MODEL = "claude-sonnet-5-5"  # D-7

INSTRUCTIONS = (
    "You are the intake router for a home-services business (HVAC). Read one missed-call transcript or web form and "
    "choose exactly one route: book (a clear service request with enough detail and normal urgency), follow_up "
    "(something is missing, or it can wait for a reply), or escalate (a person should decide now). Give a confidence "
    "from 0 to 1 and one to five short reasons a dispatcher can read. If you are unsure, say so with a lower "
    "confidence rather than guessing: low-confidence answers go to a person. Consent, message tone and safety checks "
    "are applied after you by the business's own systems. Return JSON only, matching the schema."
)


def user_prompt(intake: Intake, local_time: str, after_hours: bool, on_call: bool) -> str:
    return json.dumps({
        "source": intake.source,
        "received_local": local_time,
        "after_hours": after_hours,
        "on_call_available": on_call,
        "text": intake.text,
    }, ensure_ascii=False)


class RouterCallError(RuntimeError):
    """The router could not produce a response."""


class NoRecording(RouterCallError):
    """The recorded file has no response for this intake."""


class LiveCallRefused(RuntimeError):
    """A live model call was asked for without a key (D-6)."""


@dataclass
class RouterCall:
    model: str
    raw: str | dict[str, Any]  # validated by the desk (parse_router), never trusted here
    input_tokens: int = 0
    output_tokens: int = 0
    sdk_cost_usd: float | None = None
    duration_ms: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Router(Protocol):
    name: str
    measured: bool
    calls: Counter[str]

    async def route(self, intake: Intake, prompt: str) -> RouterCall: ...


class RecordedRouter:
    name = "recorded"
    measured = False

    def __init__(self, path: Path | None = None, responses: dict[str, Any] | None = None) -> None:
        self.path = path or RECORDED_FILE
        if responses is None:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            responses = doc["responses"]
            self.model = str(doc.get("model", MODEL))
        else:
            self.model = MODEL
        self.responses: dict[str, Any] = responses
        self.calls: Counter[str] = Counter()

    @staticmethod
    def key(intake: Intake) -> str:
        return f"router:{intake.id}"

    def has(self, intake: Intake) -> bool:
        return self.key(intake) in self.responses

    async def route(self, intake: Intake, prompt: str) -> RouterCall:
        k = self.key(intake)
        if k not in self.responses:
            raise NoRecording(f"no recording for {k!r}; a live run needs a key (D-6)")
        self.calls["router"] += 1
        return RouterCall(model=self.model, raw=self.responses[k], extra={"recorded_key": k})


class AgentSdkRouter:
    name = "claude-agent-sdk"
    measured = True

    def __init__(self, model: str = MODEL, max_budget_usd: float = 10.0) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LiveCallRefused("ANTHROPIC_API_KEY is not set; this build runs on the recorded router only (D-6).")
        self.model = model
        self.max_budget_usd = max_budget_usd
        self.calls: Counter[str] = Counter()

    async def route(self, intake: Intake, prompt: str) -> RouterCall:  # pragma: no cover - never run in this build
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=INSTRUCTIONS,
            tools=[],
            allowed_tools=[],
            permission_mode="dontAsk",
            setting_sources=[],
            max_turns=1,
            output_format={"type": "json_schema", "schema": RouterDecision.json_schema()},
            max_budget_usd=self.max_budget_usd,
        )
        started = time.monotonic()
        text_parts: list[str] = []
        result: Any = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                text_parts.extend(b.text for b in message.content if isinstance(b, TextBlock))
            elif isinstance(message, ResultMessage):
                result = message
        if result is None or result.is_error:
            raise RouterCallError(f"router: the SDK returned no usable result for {intake.id}")
        self.calls["router"] += 1
        usage = result.usage or {}
        raw: str | dict[str, Any] = result.structured_output if isinstance(result.structured_output, dict) else (
            text_parts[-1] if text_parts else (result.result or ""))
        return RouterCall(model=self.model, raw=raw,
                          input_tokens=int(usage.get("input_tokens", 0)) + int(usage.get("cache_read_input_tokens", 0))
                          + int(usage.get("cache_creation_input_tokens", 0)),
                          output_tokens=int(usage.get("output_tokens", 0)), sdk_cost_usd=result.total_cost_usd,
                          duration_ms=int((time.monotonic() - started) * 1000))


class RecordingRouter:  # pragma: no cover - only meaningful with a live router
    """Wraps a live router and saves each response under its key, in the recorded file's shape."""

    def __init__(self, inner: Router, path: Path) -> None:
        self.inner, self.path = inner, path
        self.name, self.measured = f"recording({inner.name})", inner.measured
        self.calls = inner.calls
        self.saved: dict[str, Any] = {}

    async def route(self, intake: Intake, prompt: str) -> RouterCall:
        r = await self.inner.route(intake, prompt)
        self.saved[f"router:{intake.id}"] = r.raw
        doc = {"_about": "Recorded from a live run (RecordingRouter).", "model": r.model, "responses": self.saved}
        self.path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return r
