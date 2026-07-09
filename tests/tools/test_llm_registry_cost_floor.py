"""Cost-floor selection tests for tools/llm_registry.py.

`cost_score` is cost-EFFICIENCY (higher = cheaper). A minimum floor excludes the
most expensive models so tier selection does not always grab the priciest one.
"""

from __future__ import annotations

import json

from tools import llm_registry as R


def _entry(provider, model, q, cost=None, blocked=False):
    return R.ModelRegistryEntry(
        provider=provider, model=model, blocked=blocked, quality={"T5": q}, cost_score=cost
    )


def _anthropic_registry():
    return [
        _entry("anthropic", "claude-opus-4-6", 0.98, cost=0.08),  # priciest
        _entry("anthropic", "claude-sonnet-4-6", 0.95, cost=0.35),
        _entry("anthropic", "claude-haiku-4-5", 0.62, cost=0.75),
    ]


def test_cost_score_parsed_from_registry(tmp_path, monkeypatch):
    path = tmp_path / "reg.json"
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "m",
                        "quality": {"T5": 0.9},
                        "cost_score": 0.25,
                    },
                    {"provider": "openai", "model_id": "n", "quality": {"T5": 0.8}},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(R.ENV_MODEL_REGISTRY_CONFIG, str(path))
    entries = {e.model: e for e in R.load_model_registry()}
    assert entries["m"].cost_score == 0.25
    assert entries["n"].cost_score is None  # missing -> None, never excluded


def test_default_floor_excludes_priciest_model():
    # Default floor (0.12) drops opus (0.08); best remaining is sonnet.
    assert (
        R.select_model_for_tier(provider="anthropic", tier="T5", registry=_anthropic_registry())
        == "claude-sonnet-4-6"
    )


def test_floor_zero_is_pure_max_quality():
    assert (
        R.select_model_for_tier(
            provider="anthropic", tier="T5", registry=_anthropic_registry(), min_cost_score=0.0
        )
        == "claude-opus-4-6"
    )


def test_missing_cost_score_is_never_excluded():
    reg = [_entry("openai", "no-cost", 0.99, cost=None), _entry("openai", "cheap", 0.80, cost=0.9)]
    assert R.select_model_for_tier(provider="openai", tier="T5", registry=reg) == "no-cost"


def test_floor_relaxes_when_it_would_exclude_everything():
    # All models are pricier than the floor -> relax rather than return None.
    reg = [
        _entry("anthropic", "opus", 0.98, cost=0.05),
        _entry("anthropic", "opus2", 0.90, cost=0.07),
    ]
    assert (
        R.select_model_for_tier(provider="anthropic", tier="T5", registry=reg, min_cost_score=0.5)
        == "opus"
    )


def test_env_override_respected(monkeypatch):
    monkeypatch.setenv(R.ENV_MIN_COST_SCORE, "0.0")
    assert (
        R.select_model_for_tier(provider="anthropic", tier="T5", registry=_anthropic_registry())
        == "claude-opus-4-6"
    )


def test_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(R.ENV_MIN_COST_SCORE, "not-a-number")
    assert R.resolve_min_cost_score() == R.DEFAULT_MIN_COST_SCORE


def test_negative_floor_clamped_to_zero():
    assert R.resolve_min_cost_score(-1.0) == 0.0


def test_blocked_models_still_excluded_under_floor():
    reg = [
        _entry("anthropic", "sonnet", 0.95, cost=0.35, blocked=True),
        _entry("anthropic", "haiku", 0.62, cost=0.75),
    ]
    assert R.select_model_for_tier(provider="anthropic", tier="T5", registry=reg) == "haiku"


def test_shipped_config_resolves_cost_conscious_picks(tmp_path, monkeypatch):
    # Against the real shipped registry, the default floor yields the cost-conscious
    # picks (sonnet, not opus) while keeping openai/github unchanged.
    reg = R.load_model_registry()
    assert R.select_model_for_tier(provider="openai", tier="T5", registry=reg) == "gpt-5.4"
    assert (
        R.select_model_for_tier(provider="anthropic", tier="T5", registry=reg)
        == "claude-sonnet-4-6"
    )


def test_shipped_slots_are_tier_based_not_model_pinned():
    slots = json.loads(R.DEFAULT_SLOT_CONFIG_PATH.read_text(encoding="utf-8"))
    for slot in slots["slots"]:
        assert not slot.get("model"), f"slot {slot['name']} should be tier-based, not model-pinned"
        assert slot.get("quality_tier"), f"slot {slot['name']} missing quality_tier"
