"""The synthetic labeled set (`fixtures/intakes.json`, written by `fixtures/make_fixtures.py`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from intake_desk.models import REPO_DIR, Intake, Route

INTAKES_FILE = REPO_DIR / "fixtures" / "intakes.json"


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: Route
    emergency: bool
    tags: list[str]
    duplicate_of: str | None = None


def load(path: Path | None = None) -> tuple[list[Intake], dict[str, Label]]:
    doc: dict[str, Any] = json.loads((path or INTAKES_FILE).read_text(encoding="utf-8"))
    intakes = [Intake.model_validate(i) for i in doc["intakes"]]
    labels = {k: Label.model_validate(v) for k, v in doc["labels"].items()}
    return intakes, labels


def by_time(intakes: list[Intake]) -> list[Intake]:
    """Process order for an eval run: arrival time, so duplicates meet their originals (D-15)."""
    return sorted(intakes, key=lambda i: (i.received_at, i.id))
