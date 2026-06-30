"""Tests for the model-registry freshness gate (tools/check_model_registry_freshness.py)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from tools import check_model_registry_freshness as gate

TODAY = dt.date(2026, 6, 28)


def _registry(**over):
    base = {
        "version": "1.0.0",
        "review_by": "2026-12-31",
        "models": [
            {"model_id": "gpt-5.4", "provider": "openai", "quality": {"T5": 0.97}},
            {"model_id": "gpt-5.1", "provider": "openai", "quality": {"T5": 0.93}},
            {"model_id": "claude-sonnet-4-6", "provider": "anthropic", "quality": {"T5": 0.95}},
            {
                "model_id": "old-blocked",
                "provider": "openai",
                "quality": {"T5": 0.30},
                "blocked": True,
            },
        ],
    }
    base.update(over)
    return base


def _slots(*pairs):
    return {
        "slots": [
            {"name": f"slot{i+1}", "provider": p, "model": m} for i, (p, m) in enumerate(pairs)
        ]
    }


def _kinds(findings):
    return sorted(f["kind"] for f in findings)


def test_fresh_registry_has_no_findings():
    findings = gate.evaluate(_registry(), _slots(("openai", "gpt-5.4")), today=TODAY)
    assert findings == []


def test_review_overdue_explicit_review_by():
    reg = _registry(review_by="2026-05-01")
    findings = gate.evaluate(reg, _slots(("openai", "gpt-5.4")), today=TODAY)
    assert _kinds(findings) == ["review_overdue"]
    assert "overdue" in findings[0]["detail"]


def test_review_overdue_derived_from_last_updated():
    reg = _registry()
    reg.pop("review_by")
    reg["last_updated"] = "2026-04-14"  # +60d -> 2026-06-13 < today
    findings = gate.evaluate(reg, _slots(("openai", "gpt-5.4")), today=TODAY, max_age_days=60)
    assert "review_overdue" in _kinds(findings)


def test_review_not_overdue_within_window():
    reg = _registry()
    reg.pop("review_by")
    reg["last_updated"] = "2026-06-20"  # +60d in the future
    findings = gate.evaluate(reg, _slots(("openai", "gpt-5.4")), today=TODAY, max_age_days=60)
    assert "review_overdue" not in _kinds(findings)


def test_blocked_pin():
    findings = gate.evaluate(_registry(), _slots(("openai", "old-blocked")), today=TODAY)
    assert _kinds(findings) == ["blocked_pin"]


def test_unknown_pin():
    findings = gate.evaluate(_registry(), _slots(("openai", "gpt-9-imaginary")), today=TODAY)
    assert _kinds(findings) == ["unknown_pin"]


def test_dominated_pin_flags_better_same_provider_model():
    # Pin sonnet-4-6 (0.95) while registry also has a higher claude model.
    reg = _registry()
    reg["models"].append(
        {"model_id": "claude-opus-4-6", "provider": "anthropic", "quality": {"T5": 0.98}}
    )
    findings = gate.evaluate(reg, _slots(("anthropic", "claude-sonnet-4-6")), today=TODAY)
    assert _kinds(findings) == ["dominated_pin"]
    assert "claude-opus-4-6" in findings[0]["detail"]


def test_dominated_pin_uses_slot_quality_tier():
    reg = _registry()
    reg["models"] = [
        {
            "model_id": "primary-for-t4",
            "provider": "openai",
            "quality": {"T4": 0.95, "T5": 0.80},
        },
        {
            "model_id": "better-t5-only",
            "provider": "openai",
            "quality": {"T4": 0.90, "T5": 0.99},
        },
    ]
    slots = {
        "slots": [
            {
                "name": "slot1",
                "provider": "openai",
                "model": "primary-for-t4",
                "quality_tier": "T4",
            }
        ]
    }
    findings = gate.evaluate(reg, slots, today=TODAY)
    assert findings == []


def test_dominated_pin_normalizes_slot_quality_tier():
    reg = _registry()
    reg["models"] = [
        {
            "model_id": "old-t3",
            "provider": "openai",
            "quality": {"T3": 0.50, "T5": 0.99},
        },
        {
            "model_id": "new-t3",
            "provider": "openai",
            "quality": {"T3": 0.80, "T5": 0.10},
        },
    ]
    slots = {
        "slots": [
            {
                "name": "slot1",
                "provider": "openai",
                "model": "old-t3",
                "quality_tier": "t3",
            }
        ]
    }

    findings = gate.evaluate(reg, slots, today=TODAY)

    assert _kinds(findings) == ["dominated_pin"]
    assert "new-t3" in findings[0]["detail"]


def test_tier_derived_slot_without_model_is_not_flagged():
    # A slot with no pinned model derives from the registry at runtime -> non-ossifying.
    slots = {"slots": [{"name": "slot1", "provider": "anthropic", "quality_tier": "T5"}]}
    findings = gate.evaluate(_registry(), slots, today=TODAY)
    assert findings == []


def test_real_repo_files_parse_and_run(tmp_path):
    # The shipped config must at least load and evaluate without raising.
    root = Path(__file__).resolve().parent.parent
    reg = json.loads((root / "config" / "model_registry.json").read_text())
    slots = json.loads((root / "config" / "llm_slots.json").read_text())
    findings = gate.evaluate(reg, slots, today=TODAY)
    assert isinstance(findings, list)


def test_consumer_template_registry_defaults_are_fresh():
    root = Path(__file__).resolve().parent.parent
    reg = json.loads(
        (root / "templates" / "consumer-repo" / "config" / "model_registry.json").read_text()
    )
    slots = json.loads(
        (root / "templates" / "consumer-repo" / "config" / "llm_slots.json").read_text()
    )
    findings = gate.evaluate(reg, slots, today=dt.date(2026, 6, 30))
    assert findings == []


def test_main_exit_codes(tmp_path):
    reg = tmp_path / "reg.json"
    slots = tmp_path / "slots.json"
    reg.write_text(json.dumps(_registry(review_by="2026-05-01")))
    slots.write_text(json.dumps(_slots(("openai", "gpt-5.4"))))
    rc = gate.main(
        ["--registry", str(reg), "--slots", str(slots), "--today", "2026-06-28", "--json"]
    )
    assert rc == 1  # overdue
    reg.write_text(json.dumps(_registry(review_by="2026-12-31")))
    rc = gate.main(["--registry", str(reg), "--slots", str(slots), "--today", "2026-06-28"])
    assert rc == 0
    rc = gate.main(["--registry", str(reg), "--slots", str(slots), "--today", "not-a-date"])
    assert rc == 2
