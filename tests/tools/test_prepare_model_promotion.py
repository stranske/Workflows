"""Tests for tools/prepare_model_promotion.py (#2819 move 3)."""

from __future__ import annotations

import datetime as dt
import json

from tools import prepare_model_promotion as pmp

TODAY = dt.date(2026, 8, 1)


def _registry(model_id="claude-opus-4-6"):
    return {
        "selections": [
            {
                "profile": "verifier-balanced",
                "provider": "anthropic",
                "model_id": model_id,
                "status": "provisional",
                "decided_at": "2026-07-10",
                "review_by": "2026-08-09",
                "evidence_ids": ["catalog-1"],
            }
        ]
    }


def _result(model_id, provider, *, status, cost, latency=100.0):
    return {
        "provider": provider,
        "model_id": model_id,
        "status": status,
        "gate_results": {"paired_success_noninferiority": status == "passed"},
        "metrics": {"cost_per_accepted_review_usd": cost, "p95_latency_ms": latency},
    }


def _report(results, *, baseline="claude-opus-4-6"):
    return {
        "baseline_model_id": baseline,
        "results": results,
        "registry_evidence": [
            {
                "evidence_id": f"bench-2026-08:{r['provider']}:{r['model_id']}",
                "provider": r["provider"],
                "model_id": r["model_id"],
                "kind": "workload-benchmark",
                "status": r["status"],
            }
            for r in results
        ],
    }


def test_model_family_rules():
    assert pmp.model_family("anthropic", "claude-opus-4-8") == "claude-opus"
    assert pmp.model_family("anthropic", "claude-opus-4-6") == "claude-opus"
    assert pmp.model_family("anthropic", "claude-sonnet-5") == "claude-sonnet"
    assert pmp.model_family("openai", "gpt-5.6-terra") == "gpt-5"
    assert pmp.model_family("openai", "gpt-5.4") == "gpt-5"
    # github-models ids are publisher-namespaced: keep the publisher and apply the
    # OpenAI-style rule to the remainder, so a future openai/gpt-5.x is a
    # same-family successor to the reviewed openai/gpt-5 selection.
    assert pmp.model_family("github-models", "openai/gpt-5") == "openai/gpt-5"
    assert pmp.model_family("github-models", "openai/gpt-5-mini") == "openai/gpt-5"
    assert pmp.model_family("github-models", "openai/gpt-5.1") == "openai/gpt-5"
    # A different major line stays a different family.
    assert pmp.model_family("github-models", "openai/gpt-4.1") == "openai/gpt-4"
    # A bare (unpublished) github-models id keeps its exact id, so the superseded
    # codex-mini-latest is never "same family" as openai/gpt-5 by accident.
    assert pmp.model_family("github-models", "codex-mini-latest") == "codex-mini-latest"
    assert pmp.model_family("github-models", "codex-mini-latest") != pmp.model_family(
        "github-models", "openai/gpt-5"
    )
    # Unknown provider -> exact id, so nothing is ever "same family" by accident.
    # (azure-openai is NOT unknown: it normalizes to openai and uses that rule.)
    assert pmp.model_family("mistral", "some-model-7") == "some-model-7"


def test_same_family_cheaper_pass_is_prepared():
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.08),
        ]
    )
    props = pmp.find_promotions(report, _registry())
    assert len(props) == 1
    assert props[0]["to_model_id"] == "claude-opus-4-8"
    assert props[0]["from_model_id"] == "claude-opus-4-6"


def test_cross_family_is_not_prepared():
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-sonnet-5", "anthropic", status="passed", cost=0.02),
        ]
    )
    assert pmp.find_promotions(report, _registry()) == []  # different family -> human only


def test_more_expensive_same_family_is_not_prepared():
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.20),
        ]
    )
    assert pmp.find_promotions(report, _registry()) == []


def test_failed_candidate_is_not_prepared():
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="failed", cost=0.05),
        ]
    )
    assert pmp.find_promotions(report, _registry()) == []


def test_candidate_ignored_if_baseline_is_not_the_registry_incumbent():
    # registry incumbent is opus-4-6 but benchmark baseline is something else
    report = _report(
        [
            _result("claude-opus-9-9", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.05),
        ],
        baseline="claude-opus-9-9",
    )
    assert pmp.find_promotions(report, _registry()) == []


def test_cheapest_same_family_candidate_wins_per_provider():
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.09),
            _result("claude-opus-4-7", "anthropic", status="passed", cost=0.05),
        ]
    )
    props = pmp.find_promotions(report, _registry())
    assert len(props) == 1 and props[0]["to_model_id"] == "claude-opus-4-7"


def test_apply_promotion_records_history_and_updates_selection():
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.08),
        ]
    )
    promotion = pmp.find_promotions(report, _registry())[0]
    new = pmp.apply_promotion(_registry(), promotion, today=TODAY)
    sel = new["selections"][0]
    assert sel["model_id"] == "claude-opus-4-8"
    assert "bench-2026-08:anthropic:claude-opus-4-8" in sel["evidence_ids"]
    assert sel["decided_at"] == "2026-08-01"
    assert sel["review_by"] == "2026-08-31"
    assert new["selection_history"][0]["model_id"] == "claude-opus-4-6"
    assert new["selection_history"][0]["superseded_by"] == "claude-opus-4-8"


def test_promote_then_breach_rolls_back_to_prior():
    # 1) promote 4-6 -> 4-8
    up = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.08),
        ]
    )
    promoted = pmp.apply_promotion(
        _registry(), pmp.find_promotions(up, _registry())[0], today=TODAY
    )
    assert promoted["selections"][0]["model_id"] == "claude-opus-4-8"

    # 2) later benchmark shows the new active model failing -> rollback
    breach = _report(
        [_result("claude-opus-4-8", "anthropic", status="failed", cost=0.08)],
        baseline="claude-opus-4-8",
    )
    rollbacks = pmp.find_rollbacks(breach, promoted)
    assert len(rollbacks) == 1 and rollbacks[0]["to_model_id"] == "claude-opus-4-6"
    reverted = pmp.apply_rollback(promoted, rollbacks[0], today=TODAY)
    assert reverted["selections"][0]["model_id"] == "claude-opus-4-6"
    assert reverted["selection_history"] == []  # history consumed by the rollback


def test_rollback_needs_history():
    breach = _report([_result("claude-opus-4-6", "anthropic", status="failed", cost=0.10)])
    assert pmp.find_rollbacks(breach, _registry()) == []  # nothing to revert to


def test_main_auto_writes_and_signals(tmp_path, capsys):
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.08),
        ]
    )
    bench = tmp_path / "bench.json"
    reg = tmp_path / "registry.json"
    out = tmp_path / "out.json"
    bench.write_text(json.dumps(report))
    reg.write_text(json.dumps(_registry()))
    rc = pmp.main(
        [
            "--benchmark",
            str(bench),
            "--registry",
            str(reg),
            "--write",
            str(out),
            "--today",
            "2026-08-01",
        ]
    )
    assert rc == 10  # a change is prepared
    assert json.loads(out.read_text())["selections"][0]["model_id"] == "claude-opus-4-8"


def test_main_noop_when_nothing_qualifies(tmp_path):
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-sonnet-5", "anthropic", status="passed", cost=0.01),
        ]
    )
    bench = tmp_path / "bench.json"
    reg = tmp_path / "registry.json"
    bench.write_text(json.dumps(report))
    reg.write_text(json.dumps(_registry()))
    assert (
        pmp.main(["--benchmark", str(bench), "--registry", str(reg), "--today", "2026-08-01"]) == 0
    )
