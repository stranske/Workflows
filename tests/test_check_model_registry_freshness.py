"""Tests for tools/check_model_registry_freshness.py."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from tools import check_model_registry_freshness as gate

TODAY = dt.date(2026, 7, 10)


def _registry(**over):
    base = {
        "schema_version": "2.0.0",
        "as_of": "2026-07-10",
        "review_by": "2026-07-24",
        "sources": [
            {
                "source_id": "models-1",
                "checked_at": "2026-07-10",
                "url": "https://example.test/models",
            }
        ],
        "models": [
            {
                "model_id": "model-current",
                "provider": "openai",
                "lifecycle": "current",
                "source_ids": ["models-1"],
                "pricing": {"as_of": "2026-07-10"},
            },
            {
                "model_id": "model-blocked",
                "provider": "openai",
                "lifecycle": "current",
                "blocked": True,
                "source_ids": ["models-1"],
                "pricing": {"as_of": "2026-07-10"},
            },
        ],
        "selections": [
            {
                "profile": "verifier-balanced",
                "provider": "openai",
                "model_id": "model-current",
                "status": "provisional",
                "review_by": "2026-07-24",
                "evidence_ids": ["catalog-1"],
            }
        ],
        "evidence": [
            {
                "evidence_id": "catalog-1",
                "kind": "provider-catalog-review",
                "status": "catalog-only",
                "source_ids": ["models-1"],
            }
        ],
    }
    base.update(over)
    return base


def _slots(model: str | None = None):
    slot = {
        "name": "slot1",
        "provider": "openai",
        "profile": "verifier-balanced",
    }
    if model:
        slot["model"] = model
    return {"slots": [slot]}


def _policy():
    return {"policy_id": "test-policy", "profiles": {"verifier-balanced": {}}}


def _kinds(findings):
    return sorted(finding["kind"] for finding in findings)


def test_fresh_provisional_decision_has_no_findings():
    assert gate.evaluate(_registry(), _slots(), today=TODAY, policy=_policy()) == []


def test_review_overdue_is_reported():
    findings = gate.evaluate(
        _registry(review_by="2026-07-01"), _slots(), today=TODAY, policy=_policy()
    )
    assert "review_overdue" in _kinds(findings)


def test_provisional_selection_must_be_resolved_by_review_date():
    registry = _registry()
    registry["selections"][0]["review_by"] = "2026-07-01"
    findings = gate.evaluate(registry, _slots(), today=TODAY, policy=_policy())
    assert "provisional_overdue" in _kinds(findings)


def test_unknown_and_blocked_selections_are_reported():
    unknown = _registry()
    unknown["selections"][0]["model_id"] = "missing"
    blocked = _registry()
    blocked["selections"][0]["model_id"] = "model-blocked"

    assert "unknown_selection" in _kinds(
        gate.evaluate(unknown, _slots(), today=TODAY, policy=_policy())
    )
    assert "blocked_selection" in _kinds(
        gate.evaluate(blocked, _slots(), today=TODAY, policy=_policy())
    )


def test_approved_selection_requires_passed_workload_benchmark():
    registry = _registry()
    registry["selections"][0]["status"] = "approved"
    findings = gate.evaluate(registry, _slots(), today=TODAY, policy=_policy())
    assert "unproved_approval" in _kinds(findings)

    registry["evidence"].append(
        {
            "evidence_id": "bench-1",
            "schema": "workflows-model-benchmark-evidence/v1",
            "kind": "workload-benchmark",
            "status": "passed",
            "measured_at": "2026-07-10",
            "policy_id": "test-policy",
            "profile": "verifier-balanced",
            "corpus_version": "corpus-v1",
            "prompt_version": "prompt-v1",
            "model_id": "model-current",
            "gate_results": {"all": True},
        }
    )
    registry["selections"][0]["evidence_ids"].append("bench-1")
    findings = gate.evaluate(registry, _slots(), today=TODAY, policy=_policy())
    assert "unproved_approval" not in _kinds(findings)


def test_explicit_old_pin_is_flagged_against_reviewed_selection():
    registry = _registry()
    registry["models"].append(
        {"model_id": "model-old", "provider": "openai", "lifecycle": "compatibility"}
    )
    findings = gate.evaluate(registry, _slots("model-old"), today=TODAY, policy=_policy())
    assert "selection_override" in _kinds(findings)


def test_explicit_pin_without_profile_is_advisory():
    registry = _registry()
    registry["models"].append(
        {"model_id": "model-old", "provider": "openai", "lifecycle": "compatibility"}
    )
    findings = gate.evaluate(
        registry,
        {"slots": [{"name": "slot1", "provider": "openai", "model": "model-old"}]},
        today=TODAY,
        policy=_policy(),
    )
    assert "selection_override" not in _kinds(findings)


def test_unknown_legacy_pin_is_advisory():
    findings = gate.evaluate(
        _registry(),
        {"slots": [{"name": "slot1", "provider": "openai", "model": "absent"}]},
        today=TODAY,
        policy=_policy(),
    )
    assert "unknown_pin" not in _kinds(findings)


def test_legacy_pin_requires_default_selection():
    registry = _registry()
    registry["selections"] = []
    findings = gate.evaluate(
        registry,
        {"slots": [{"name": "slot1", "provider": "openai", "model": "absent"}]},
        today=TODAY,
        policy=_policy(),
    )
    assert _kinds(findings) == ["missing_selection"]


def test_current_unblocked_legacy_pin_is_compatible_with_default_selection():
    registry = _registry()
    registry["models"].append(
        {
            "model_id": "model-frontier",
            "provider": "openai",
            "lifecycle": "current",
            "source_ids": ["models-1"],
            "pricing": {"as_of": "2026-07-10"},
        }
    )
    findings = gate.evaluate(
        registry,
        {"slots": [{"name": "slot1", "provider": "openai", "model": "model-frontier"}]},
        today=TODAY,
        policy=_policy(),
    )
    assert "selection_override" not in _kinds(findings)


def test_slot_requires_profile_selection():
    findings = gate.evaluate(
        _registry(),
        {"slots": [{"name": "slot2", "provider": "anthropic", "profile": "missing"}]},
        today=TODAY,
        policy=_policy(),
    )
    assert "missing_selection" in _kinds(findings)


@pytest.mark.parametrize(
    ("kind", "mutate"),
    [
        ("missing_source", lambda value: value.update(sources=[])),
        (
            "missing_pricing_date",
            lambda value: value["models"][0].pop("pricing"),
        ),
        (
            "invalid_selection_status",
            lambda value: value["selections"][0].update(status="reviewed"),
        ),
        (
            "unknown_profile",
            lambda value: value["selections"][0].update(profile="unknown"),
        ),
        (
            "inactive_selection",
            lambda value: value["models"][0].update(lifecycle="compatibility"),
        ),
        (
            "missing_evidence",
            lambda value: value["selections"][0].update(evidence_ids=[]),
        ),
        (
            "duplicate_selection",
            lambda value: value["selections"].append(dict(value["selections"][0])),
        ),
    ],
)
def test_selection_and_fact_gate_branches(kind, mutate):
    registry = _registry()
    mutate(registry)
    assert kind in _kinds(gate.evaluate(registry, _slots(), today=TODAY, policy=_policy()))


@pytest.mark.parametrize(
    ("kind", "slots"),
    [
        ("unknown_pin", _slots("absent")),
        ("blocked_pin", _slots("model-blocked")),
        ("missing_profile", {"slots": [{"name": "slot1", "provider": "openai"}]}),
    ],
)
def test_slot_pin_and_profile_gate_branches(kind, slots):
    assert kind in _kinds(gate.evaluate(_registry(), slots, today=TODAY, policy=_policy()))


def test_real_repo_files_are_fresh():
    root = Path(__file__).resolve().parent.parent
    registry = json.loads((root / "config" / "model_registry.json").read_text())
    slots = json.loads((root / "config" / "llm_slots.json").read_text())
    policy = json.loads((root / "config" / "model_selection_policy.json").read_text())
    assert gate.evaluate(registry, slots, today=TODAY, policy=policy) == []


def test_main_exit_codes(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    policy_path = tmp_path / "policy.json"
    registry_path.write_text(json.dumps(_registry()), encoding="utf-8")
    slots_path.write_text(json.dumps(_slots()), encoding="utf-8")
    policy_path.write_text(json.dumps(_policy()), encoding="utf-8")
    common = [
        "--registry",
        str(registry_path),
        "--slots",
        str(slots_path),
        "--policy",
        str(policy_path),
        "--today",
        "2026-07-10",
    ]
    assert gate.main(common) == 0
    registry_path.write_text(json.dumps(_registry(review_by="2026-07-01")), encoding="utf-8")
    assert gate.main(common) == 1
    assert gate.main([*common[:-1], "not-a-date"]) == 2
