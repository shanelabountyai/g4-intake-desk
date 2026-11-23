"""The synthetic labeled set (T3): 40 intakes, HVAC-weighted, every edge case the PRD asks for, synthetic only."""

from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

from intake_desk import fixtures
from intake_desk.router import RecordedRouter

REPO = Path(__file__).resolve().parents[1]


def test_forty_intakes_each_labeled_and_recorded() -> None:
    intakes, labels = fixtures.load()
    assert len(intakes) == 40 and len({i.id for i in intakes}) == 40
    assert set(labels) == {i.id for i in intakes}
    rec = RecordedRouter()
    assert all(rec.has(i) for i in intakes)


def test_hvac_weighted_with_every_edge_case() -> None:
    intakes, labels = fixtures.load()
    tags = Counter(t for lab in labels.values() for t in lab.tags)
    wrong_trade = [k for k, lab in labels.items() if "wrong_trade" in lab.tags]
    assert len(wrong_trade) == 4 and len(intakes) - len(wrong_trade) == 36
    assert any(lab.emergency and "after_hours" in lab.tags for lab in labels.values())
    assert tags["vague"] >= 2 and tags["duplicate"] >= 3 and tags["price_shopping"] >= 3
    assert {lab.route for lab in labels.values()} == {"book", "follow_up", "escalate"}
    for k, lab in labels.items():
        if lab.emergency:
            assert lab.route == "escalate", k
        if lab.duplicate_of:
            assert lab.duplicate_of in labels, k


def test_synthetic_only() -> None:
    intakes, _ = fixtures.load()
    for i in intakes:
        assert i.phone and re.fullmatch(r"\+1-312-555-01\d\d", i.phone), i.phone
        assert i.email is None or i.email.endswith("@example.com")
    contacts = json.loads((REPO / "contacts" / "g4_contacts.json").read_text())["contacts"]
    for c in contacts:
        assert c["email"].endswith("@example.com") and re.fullmatch(r"Synthetic Caller \d\d", c["name"])
        assert c["contact_id"].startswith("g4-c") and re.fullmatch(r"\+1-312-555-01\d\d", c["phone"])


def test_generator_reproduces_committed_files(tmp_path, monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location("make_fixtures", REPO / "fixtures" / "make_fixtures.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "contacts").mkdir()
    monkeypatch.setattr(mod, "HERE", tmp_path / "fixtures")
    monkeypatch.setattr(mod, "REPO", tmp_path)
    mod.main()
    for rel in ("fixtures/intakes.json", "fixtures/recorded.json", "contacts/g4_contacts.json"):
        assert (tmp_path / rel).read_text() == (REPO / rel).read_text(), rel
