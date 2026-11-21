"""CLI (demo, eval, route, queue) and live-mode refusal."""

from __future__ import annotations

import json

from intake_desk import cli


def test_cli_live_needs_a_key(tmp_path, capsys) -> None:
    assert cli.main(["eval", "--live", "--out", str(tmp_path), "--report", str(tmp_path / "r.md")]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_eval_prints_summary(tmp_path, capsys) -> None:
    assert cli.main(["eval", "--run-id", "e", "--out", str(tmp_path), "--report", str(tmp_path / "r.md")]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["intakes"] == 40 and s["missed_emergencies"] == 0 and s["cost_usd"] == 0.0 and s["router"] == "recorded"
    assert (tmp_path / "e" / "outbox.jsonl").exists()


def test_env_threshold(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("G4_THRESHOLD", "0.9")
    assert cli.main(["eval", "--run-id", "e9", "--out", str(tmp_path), "--report", str(tmp_path / "r.md")]) == 0
    assert json.loads(capsys.readouterr().out)["threshold"] == 0.9


def test_bad_threshold(capsys) -> None:
    assert cli.main(["eval", "--threshold", "1.5"]) == 2


def test_demo_runs_end_to_end(capsys) -> None:
    assert cli.main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "Nothing is sent" in out and "ESCALATE" in out and "emergency_guard" in out and "missed emergencies 0" in out
    assert "suppressed_duplicate" in out and "blocked_consent" in out and "reject" in out


def test_route_and_queue_round_trip(tmp_path, capsys) -> None:
    base = ["--run-id", "m", "--out", str(tmp_path)]
    assert cli.main(["route", "--case", "i24", *base]) == 0
    capsys.readouterr()
    assert cli.main(["queue", "list", "--status", "pending", *base]) == 0
    [item] = json.loads(capsys.readouterr().out)
    assert cli.main(["queue", "reject", item["queue_id"], "--note", "handled", *base]) == 0
    assert json.loads(capsys.readouterr().out)["queue"]["status"] == "rejected"
    assert cli.main(["queue", "approve", item["queue_id"], *base]) == 2
    assert cli.main(["route", "--case", "nope", *base]) == 2
