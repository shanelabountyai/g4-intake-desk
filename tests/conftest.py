from __future__ import annotations

import pytest

from intake_desk import fixtures
from intake_desk.desk import Desk, DeskConfig
from intake_desk.layer import Layer
from intake_desk.router import RecordedRouter
from intake_desk.store import Store


@pytest.fixture(autouse=True)
def _no_key(monkeypatch, tmp_path):
    # No test may reach a live model or the owner's real layer file.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("G4_THRESHOLD", raising=False)
    monkeypatch.setenv("G0_DB_PATH", str(tmp_path / "default-layer.sqlite"))


@pytest.fixture()
def layer(tmp_path):
    lay = Layer(db_path=str(tmp_path / "layer.sqlite"))
    yield lay
    lay.close()


@pytest.fixture()
def labeled():
    return fixtures.load()


@pytest.fixture()
def make_desk(layer, tmp_path):
    stores: list[Store] = []

    def _make(threshold: float | None = None, router=None, jsonl: bool = False) -> Desk:
        store = Store(":memory:", jsonl=(tmp_path / f"outbox{len(stores)}.jsonl") if jsonl else None)
        stores.append(store)
        return Desk(layer, store, router or RecordedRouter(), DeskConfig.load(threshold=threshold), run_id=f"test-{len(stores)}")

    yield _make
    for s in stores:
        s.close()


@pytest.fixture()
def desk(make_desk):
    return make_desk()


@pytest.fixture()
def by_id(labeled):
    intakes, _ = labeled
    return {i.id: i for i in intakes}
