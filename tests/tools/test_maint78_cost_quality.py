"""The MAINT-78 decision gate must explain missing evidence before model calls."""

from __future__ import annotations

import json

import pytest
from tools.plan_model_eval import ROOT, build_plan
from tools.run_model_eval_cli_screen import (
    api_list_price_estimate,
    report,
    run_screen,
    select_cases,
    token_usage,
)


def _inputs():
    return tuple(
        json.loads((ROOT / path).read_text())
        for path in (
            "config/model_eval_pilot.json",
            "config/model_registry.json",
            "config/model_selection_policy.json",
        )
    )


def test_current_plan_flags_approval_gap_without_model_calls():
    plan = build_plan(*_inputs())
    assert not plan["approval_ready"]
    assert plan["automatic_api_calls"] == 0
    assert plan["corpus_cases"] == 51
    assert plan["approval_minimum_cases"] == 75
    assert plan["category_shortfalls"]["follow-up-required"] > 0
    assert plan["unpriced_openai_models"] == []


def test_new_catalog_candidate_without_price_blocks_claim_of_best_available():
    corpus, registry, policy = _inputs()
    candidates = {
        "candidates": [{"provider": "openai", "model_id": "gpt-future", "role": "catalog-advisory"}]
    }
    plan = build_plan(corpus, registry, policy, candidates)
    assert "gpt-future" in " ".join(plan["approval_blockers"])
    assert plan["catalog_advisory_models"] == ["gpt-future"]


def test_plan_surfaces_models_missing_from_pinned_cli_catalog():
    corpus, registry, policy = _inputs()
    catalog = {
        "models": [
            {"slug": "gpt-5.6-terra", "visibility": "list", "supported_in_api": True},
        ]
    }
    plan = build_plan(corpus, registry, policy, cli_catalog=catalog)
    assert "gpt-6.1-sol" in plan["pinned_cli_unavailable_models"]
    assert "gpt-5.6-terra" not in plan["pinned_cli_unavailable_models"]
    assert "gpt-6.1-sol" in " ".join(plan["approval_blockers"])


def test_cli_screen_is_bounded_and_reports_comparative_cost():
    corpus, registry, policy = _inputs()
    cases = select_cases(corpus["cases"])
    assert len(cases) == 8
    assert {case["category"] for case in cases} == {case["category"] for case in corpus["cases"]}
    assert sum(case["expected_verdict"] == "NON_PASS" for case in cases) == 4
    assert (
        api_list_price_estimate(
            1000, 500, {"input_per_million_tokens": 2, "output_per_million_tokens": 12}
        )
        == 0.008
    )
    rows = [
        {
            "case_id": case["case_id"],
            "category": case["category"],
            "expected_verdict": case["expected_verdict"],
            "actual_verdict": case["expected_verdict"],
            "schema_valid": True,
            "model_id": "gpt-5.6-terra",
            "modeled_api_cost_usd": 0.008,
        }
        for case in cases
    ]
    result = report(
        build_plan(corpus, registry, policy), cases, ["gpt-5.6-terra"], rows, stopped_early=False
    )
    assert result["api_key_calls"] == 0
    assert result["approval_ready"] is False
    assert result["models"][0]["modeled_cost_per_accepted_review_usd"] == 0.008


def test_missing_cli_usage_fails_closed():
    assert token_usage(
        '{"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}'
    ) == (2, 3)
    with pytest.raises(ValueError, match="token usage"):
        token_usage('{"type":"turn.failed"}')


def test_cli_screen_rejects_unpaired_or_unpriced_selection_before_fetch(monkeypatch):
    corpus, registry, policy = _inputs()
    monkeypatch.setattr(
        "tools.run_model_eval_cli_screen.cli_model_ids", lambda _: {"gpt-5.6-terra", "gpt-6-astra"}
    )
    with pytest.raises(ValueError, match="incumbent"):
        run_screen(corpus, registry, policy, models=["gpt-6-astra", "gpt-5.6-sol"], token="x")
    with pytest.raises(ValueError, match="verified registry prices"):
        run_screen(corpus, registry, policy, models=["gpt-5.6-terra", "gpt-unpriced"], token="x")
