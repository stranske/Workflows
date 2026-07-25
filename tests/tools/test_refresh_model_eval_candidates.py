"""Tests for tools/refresh_model_eval_candidates.py (registry-derived pilot candidates)."""

from __future__ import annotations

import json

from tools import refresh_model_eval_candidates as rc


def _registry():
    return {
        "selections": [
            {"provider": "openai", "profile": "verifier-balanced", "model_id": "gpt-5.4"},
            {
                "provider": "anthropic",
                "profile": "verifier-balanced",
                "model_id": "claude-opus-4-6",
            },
            {"provider": "openai", "profile": "some-other-profile", "model_id": "gpt-x"},
        ],
        "models": [
            {
                "provider": "openai",
                "model_id": "gpt-5.4",
                "lifecycle": "current",
                "positioning": "incumbent-verifier",
            },
            {
                "provider": "openai",
                "model_id": "gpt-5.6-terra",
                "lifecycle": "current",
                "positioning": "balanced",
            },
            {
                "provider": "openai",
                "model_id": "gpt-5.6-luna",
                "lifecycle": "current",
                "positioning": "efficient",
            },  # excluded
            {
                "provider": "openai",
                "model_id": "gpt-5.5",
                "lifecycle": "compatibility",
                "positioning": "frontier",
            },  # excluded (not current)
            {
                "provider": "openai",
                "model_id": "gpt-blocked",
                "lifecycle": "current",
                "positioning": "frontier",
                "blocked": True,
            },  # excluded (blocked)
            {
                "provider": "anthropic",
                "model_id": "claude-opus-4-6",
                "lifecycle": "current",
                "positioning": "incumbent-verifier",
            },
            {
                "provider": "anthropic",
                "model_id": "claude-opus-4-8",
                "lifecycle": "current",
                "positioning": "high-capability",
            },
        ],
    }


def test_derive_picks_incumbent_and_verifier_candidates():
    out = rc.derive_candidates(_registry())["candidates"]
    keys = [(c["provider"], c["model_id"], c["role"]) for c in out]
    assert ("openai", "gpt-5.4", "incumbent") in keys
    assert ("openai", "gpt-5.6-terra", "candidate") in keys
    assert ("anthropic", "claude-opus-4-6", "incumbent") in keys
    assert ("anthropic", "claude-opus-4-8", "candidate") in keys


def test_derive_excludes_efficient_noncurrent_and_blocked():
    models = {c["model_id"] for c in rc.derive_candidates(_registry())["candidates"]}
    assert "gpt-5.6-luna" not in models  # efficient
    assert "gpt-5.5" not in models  # not current
    assert "gpt-blocked" not in models  # blocked


def test_derive_only_uses_the_target_profile():
    # the some-other-profile openai selection must not become an incumbent
    incumbents = {
        c["model_id"]
        for c in rc.derive_candidates(_registry())["candidates"]
        if c["role"] == "incumbent"
    }
    assert "gpt-x" not in incumbents
    assert incumbents == {"gpt-5.4", "claude-opus-4-6"}


def test_derive_is_deterministic_and_sorted():
    a = rc.derive_candidates(_registry())
    b = rc.derive_candidates(_registry())
    assert a == b
    # candidates within a provider are sorted by model_id
    anth = [c["model_id"] for c in a["candidates"] if c["provider"] == "anthropic"]
    assert anth == sorted(
        anth, key=lambda m: (m != "claude-opus-4-6", m)
    )  # incumbent first, then sorted


def test_check_detects_drift(tmp_path, capsys):
    reg = tmp_path / "reg.json"
    cand = tmp_path / "cand.json"
    reg.write_text(json.dumps(_registry()))
    cand.write_text(
        json.dumps(
            {"candidates": [{"provider": "openai", "model_id": "stale", "role": "incumbent"}]}
        )
    )
    rc_code = rc.main(["--registry", str(reg), "--candidates", str(cand), "--check"])
    assert rc_code == 1  # drifted


def test_write_then_check_roundtrips(tmp_path):
    reg = tmp_path / "reg.json"
    cand = tmp_path / "cand.json"
    reg.write_text(json.dumps(_registry()))
    assert rc.main(["--registry", str(reg), "--candidates", str(cand), "--write"]) == 0
    assert rc.main(["--registry", str(reg), "--candidates", str(cand), "--check"]) == 0


def test_committed_candidates_match_registry_derivation():
    """Drift gate: the shipped config/model_eval_candidates.json must equal the derivation."""
    registry = json.loads(rc.DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
    committed = json.loads(rc.DEFAULT_CANDIDATES_PATH.read_text(encoding="utf-8"))
    assert committed == rc.derive_candidates(registry), (
        "config/model_eval_candidates.json is out of sync with config/model_registry.json; "
        "run `python -m tools.refresh_model_eval_candidates --write`"
    )
