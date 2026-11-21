"""The shared layer (G0·C), called in-process (D-8), modelled on G3·C's adapter.

One adapter so every capability call goes through one place and is counted. Every method returns the capability's
typed `Output`; a `Refusal` becomes `Output(ok=False, error=…)` exactly as G0's MCP server does.

Three G4 seeds are loaded through G0's own idempotent seed loader, because the v1 contracts have no register tool (D-9):
synthetic contacts `g4-c*`, brand policy version `g4-followup-1` and rubric `g4_route_v1`. The adapter refuses anything
not namespaced `g4`, so G0's own contacts, rubrics and policy v1 can never be overwritten from here.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from shared_layer.capabilities import audience_consent, brand_policy, evaluation, measurement, observability
from shared_layer.capabilities import health as health_cap
from shared_layer.contracts import contract_versions
from shared_layer.errors import Refusal, ToolError
from shared_layer.storage import Database, open_database

from intake_desk.models import REPO_DIR

CONTACTS_FILE = REPO_DIR / "contacts" / "g4_contacts.json"
BRAND_FILE = REPO_DIR / "brand" / "brand_policy_g4_followup_1.json"
RUBRIC_FILE = REPO_DIR / "rubrics" / "g4_route_v1.json"
RUBRIC_ID = "g4_route_v1"
BRAND_POLICY_VERSION = "g4-followup-1"
# Every customer message must pass G0's own policy v1 AND the G4 delta (D-17).
BRAND_VERSIONS = ("1", BRAND_POLICY_VERSION)
AGENT = "intake-desk"


class LayerDegraded(RuntimeError):
    """health reported `degraded`, or a G4 seed is missing; the run must not start."""


class Layer:
    def __init__(self, db_path: str | None = None, db: Database | None = None, contacts_file: Path | None = None,
                 brand_file: Path | None = None, rubric_file: Path | None = None) -> None:
        self.db = db or open_database(db_path)
        self.calls: Counter[str] = Counter()
        self.contacts_file = contacts_file or CONTACTS_FILE
        self.brand_file = brand_file or BRAND_FILE
        self.rubric_file = rubric_file or RUBRIC_FILE
        self._phones: dict[str, str] = {}
        try:
            self.load_seeds()
        except Exception:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    # -- the one way a call is made ------------------------------------------

    def _run(self, module: Any, **kwargs: Any) -> Any:
        self.calls[module.TOOL] += 1
        output_cls = module.Output
        try:
            inp = module.Input(**kwargs)
        except ValidationError as e:
            return output_cls(ok=False, error=ToolError(code="INVALID_ARGUMENT", message=str(e).splitlines()[0]))
        try:
            return module.run(self.db, inp)
        except Refusal as r:
            return output_cls(ok=False, error=r.envelope)
        except sqlite3.Error as e:
            return output_cls(ok=False, error=ToolError(code="STORAGE_ERROR", message=f"SQLite refused the operation: {e}"))

    # -- seeds (D-9) -------------------------------------------------------------

    def load_seeds(self) -> None:
        contacts_doc = json.loads(self.contacts_file.read_text(encoding="utf-8"))
        ids = [c["contact_id"] for c in contacts_doc["contacts"]]
        if not ids or any(not i.startswith("g4-") for i in ids):
            raise LayerDegraded(f"this consumer may only seed contacts namespaced g4-*, got {ids[:5]}")
        brand_doc = json.loads(self.brand_file.read_text(encoding="utf-8"))
        rule_ids = [r["id"] for r in brand_doc["rules"]]
        if not str(brand_doc["policy_version"]).startswith("g4-") or any(not i.startswith("g4.") for i in rule_ids):
            raise LayerDegraded(f"this consumer may only seed brand policy versions g4-* with rules g4.*, "
                                f"got {brand_doc['policy_version']!r} / {rule_ids}")
        rubric_doc = json.loads(self.rubric_file.read_text(encoding="utf-8"))
        rubric_ids = [r["id"] for r in rubric_doc["rubrics"]]
        if not rubric_ids or any(not i.startswith("g4_") for i in rubric_ids):
            raise LayerDegraded(f"this consumer may only seed rubrics namespaced g4_*, got {rubric_ids}")
        with self.db.conn:
            # G0's own idempotent loaders (INSERT OR REPLACE by id). The contact loader refuses non-example.com.
            self.db._seed_contacts(contacts_doc)
            self.db._seed_brand_policy(brand_doc)
            self.db._seed_rubrics(rubric_doc)
        self._phones = {_digits(c["phone"]): c["contact_id"] for c in contacts_doc["contacts"] if c.get("phone")}

    def contact_for(self, phone: str | None, email: str | None) -> str | None:
        """Caller-ID / form lookup → G4 contact id, or None for an unknown caller (D-9)."""
        if phone and _digits(phone) in self._phones:
            return self._phones[_digits(phone)]
        if email:
            row = self.db.conn.execute("SELECT contact_id FROM contacts WHERE email = ? AND contact_id LIKE 'g4-%'",
                                       (email.strip().lower(),)).fetchone()
            if row is not None:
                return str(row["contact_id"])
        return None

    # -- capabilities ------------------------------------------------------------

    def health(self) -> health_cap.Output:
        self.calls[health_cap.TOOL] += 1
        return health_cap.run(self.db, health_cap.Input(), contracts=contract_versions())

    def require_healthy(self) -> health_cap.Output:
        h = self.health()
        if h.status != "ok":
            raise LayerDegraded(f"shared layer degraded: writable={h.db_writable} seeds={h.seeds} at {h.db_path}")
        if RUBRIC_ID not in h.rubrics:
            raise LayerDegraded(f"rubric {RUBRIC_ID} is not in the layer's store (have {h.rubrics})")
        missing = [v for v in BRAND_VERSIONS if v not in h.policy_versions]
        if missing:
            raise LayerDegraded(f"brand policy version(s) {missing} not in the layer's store (have {h.policy_versions})")
        n = int(self.db.conn.execute("SELECT COUNT(*) FROM contacts WHERE contact_id LIKE 'g4-%'").fetchone()[0])
        if n == 0:
            raise LayerDegraded("no g4 contacts in the layer's store")
        return h

    def consent(self, contact_id: str | None, channel: str) -> audience_consent.Output:
        """Fails closed. An unknown caller is asked about by a contact id that cannot exist, so G0 answers unknown_contact."""
        return self._run(audience_consent, contact_id=contact_id or "g4-unknown-caller", channel=channel)

    def check_brand(self, text: str, channel: str, policy_version: str = "1") -> brand_policy.Output:
        return self._run(brand_policy, text=text, channel=channel, policy_version=policy_version)

    def brand_gate(self, text: str, channel: str) -> tuple[bool, list[str]]:
        """Pass only when every version in BRAND_VERSIONS passes; a refusal counts as a failure (fail closed)."""
        ok, problems = True, list[str]()
        for v in BRAND_VERSIONS:
            out = self.check_brand(text, channel=channel, policy_version=v)
            if not out.ok:
                return False, [f"brand_policy {v} refused: {out.error.code if out.error else 'unknown'}"]
            ok = ok and out.passed
            problems.extend(f"{x.rule_id}: {x.excerpt}" for x in out.violations if x.severity == "fail")
        return ok, problems

    def evaluate(self, item: dict[str, Any], *, run_id: str | None = None) -> evaluation.Output:
        return self._run(evaluation, rubric_id=RUBRIC_ID, item=item, judge="deterministic", run_id=run_id)

    def log_call(self, *, run_id: str, step: str, model: str | None = None, input_tokens: int = 0, output_tokens: int = 0,
                 cost_usd: float = 0.0, status: str = "ok", duration_ms: int | None = None, note: str | None = None) -> observability.Output:
        return self._run(observability, run_id=run_id, agent=AGENT, step=step, model=model, input_tokens=input_tokens,
                         output_tokens=output_tokens, cost_usd=cost_usd, status=status, duration_ms=duration_ms, note=note)

    def run_total(self, run_id: str) -> observability.RunTotal:
        return observability.run_total(self.db, run_id)

    def record(self, event: str, fields: dict[str, Any], run_id: str) -> measurement.Output:
        return self._run(measurement, event=event, fields=fields, run_id=run_id, agent=AGENT)

    # -- cost (G0's price table; this repo has none of its own) ------------------

    @staticmethod
    def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
        p_in, p_out = dict(evaluation.PRICES_PER_MTOK).get(model, (0.0, 0.0))
        return round(float(input_tokens * p_in / 1e6 + output_tokens * p_out / 1e6), 6)

    @staticmethod
    def cap_usd() -> float:
        return float(observability.cap_usd())


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())[-10:]
