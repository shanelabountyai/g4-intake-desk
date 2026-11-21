"""The G0 adapter (T5, D-8, D-9): health first, g4-namespaced seeds through G0's loader, fail-closed consent."""

from __future__ import annotations

import json

import pytest

from intake_desk.layer import BRAND_POLICY_VERSION, RUBRIC_ID, Layer, LayerDegraded


def test_health_and_g4_seeds_present(layer) -> None:
    h = layer.require_healthy()
    assert h.status == "ok" and RUBRIC_ID in h.rubrics and {"1", BRAND_POLICY_VERSION} <= set(h.policy_versions)


def test_g0_own_seeds_untouched(layer) -> None:
    out = layer.consent("ct-001", "email")
    assert out.ok and out.contact_id == "ct-001"
    assert "post_angle_v1" in layer.health().rubrics
    row = layer.db.conn.execute("SELECT COUNT(*) FROM brand_rules WHERE policy_version = '1'").fetchone()[0]
    assert row == 12


def test_refuses_seeds_not_namespaced_g4(tmp_path) -> None:
    bad = tmp_path / "contacts.json"
    bad.write_text(json.dumps({"contacts": [{"contact_id": "ct-001", "email": "x@example.com", "name": "X", "consent_recorded_at": "z",
                                             "source": "s", "consent": {"sms": True}}]}))
    with pytest.raises(LayerDegraded):
        Layer(db_path=str(tmp_path / "l.sqlite"), contacts_file=bad)


def test_g0_loader_refuses_real_looking_email(tmp_path) -> None:
    bad = tmp_path / "contacts.json"
    bad.write_text(json.dumps({"contacts": [{"contact_id": "g4-c99", "email": "someone@gmail.com", "name": "X", "consent_recorded_at": "z",
                                             "source": "s", "consent": {"sms": True}}]}))
    with pytest.raises(ValueError, match="example.com"):
        Layer(db_path=str(tmp_path / "l.sqlite"), contacts_file=bad)


def test_degraded_when_rubric_missing(layer) -> None:
    with layer.db.conn:
        layer.db.conn.execute("DELETE FROM rubrics WHERE id = ?", (RUBRIC_ID,))
    with pytest.raises(LayerDegraded):
        layer.require_healthy()


def test_consent_fails_closed(layer) -> None:
    assert layer.consent(None, "sms").allowed is False and layer.consent(None, "sms").reason == "unknown_contact"
    assert layer.consent("g4-c19", "email").reason == "do_not_contact"
    assert layer.consent("g4-c40", "sms").reason == "not_consented"
    assert layer.consent("g4-c01", "sms").allowed is True


def test_contact_lookup(layer) -> None:
    assert layer.contact_for("+1-312-555-0101", None) == "g4-c01"
    assert layer.contact_for("(312) 555-0101", None) == "g4-c01"
    assert layer.contact_for(None, "Synthetic.Caller03@example.com") == "g4-c03"
    assert layer.contact_for("+1-312-555-0192", None) is None
    assert layer.contact_for(None, "ada.test01@example.com") is None  # G0's own contacts are not G4 callers


@pytest.mark.parametrize("text,channel,rule", [
    ("A tune-up is $89 this month.", "other", "g4.no_price_figures"),
    ("We guarantee a fix today.", "email", "g4.no_guarantee"),
    ("A tech will be there within 2 hours.", "other", "g4.no_arrival_promise"),
    ("Act now to lock your slot.", "other", "g4.no_pressure_language"),
    (" ".join(["word"] * 61), "other", "g4.sms_max_60_words"),
    ("Excited to share our new hours.", "email", "never_use.excited_to_share"),
])
def test_brand_gate_checks_v1_and_g4_delta(layer, text, channel, rule) -> None:
    ok, problems = layer.brand_gate(text, channel)
    assert not ok and any(p.startswith(rule) for p in problems)


def test_every_template_passes_the_brand_gate(layer) -> None:
    from intake_desk import templates
    for name in templates.FOLLOW_UP:
        for ch in ("other", "email"):
            assert layer.brand_gate(templates.render_follow_up(name), ch)[0], (name, ch)
    assert layer.brand_gate(templates.render_confirmation("Monday January 19 at 8:00 AM"), "other")[0]


def test_observability_logs_and_cost_from_g0_table(layer) -> None:
    out = layer.log_call(run_id="r1", step="route:x", model="claude-sonnet-5-5", input_tokens=1000, output_tokens=100,
                         cost_usd=Layer.cost_usd("claude-sonnet-5-5", 1000, 100))
    assert out.ok and out.run_total.calls == 1 and out.run_total.cost_usd == pytest.approx(0.003) and out.over_cap is False
