"""Tests for tools/prepare_model_promotion.py (#2819 move 3)."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest
from tools import evaluate_model_benchmark as benchmark
from tools import harvest_verifier_corpus as harvest
from tools import prepare_model_promotion as pmp
from tools import verifier_corpus_evidence as evidence

TODAY = dt.date(2026, 8, 1)


def _run_preparation_cli(benchmark_path, registry_path, output_path):
    """Exercise the module entry point and exit signal consumed by Maint 86."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.prepare_model_promotion",
            "--benchmark",
            str(benchmark_path),
            "--registry",
            str(registry_path),
            "--write",
            str(output_path),
            "--today",
            TODAY.isoformat(),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _harvested_benchmark(candidate, cost):
    """Join 75 simulated outcomes and retain owner-adjudicated failure categories."""
    policy = json.loads(benchmark.DEFAULT_POLICY_PATH.read_text())
    growth = policy["profiles"]["verifier-balanced"]["corpus_growth"]
    records = []
    for pr in range(1, 76):
        records.append(
            {
                "repo": "example/reviews",
                "pr": pr,
                "head_sha": "a" * 40,
                "merge_sha": "b" * 40,
                "merged": True,
                "merged_at": "2026-06-01T00:00:00Z",
                "reverted": 35 < pr <= 55,
                "verifier_followup": pr > 55,
                "followup_resolved": pr > 55,
                "verifier_decision": {
                    "schema": evidence.MARKER,
                    "repo": "example/reviews",
                    "pr": pr,
                    "head_sha": "a" * 40,
                    "evaluated_sha": "b" * 40,
                    "run_id": str(pr),
                    "run_attempt": "1",
                    "verdict": "PASS",
                    "source_url": f"https://github.com/example/reviews/pull/{pr}#issuecomment-1",
                },
            }
        )
    promoted, staged = harvest.partition(
        records,
        now=dt.datetime(2026, 8, 1, tzinfo=dt.UTC),
        stability_days=growth["stability_days"],
    )
    assert staged == []
    # These categories cannot be inferred by the harvester. Supply explicitly
    # simulated owner labels, including enough NON_PASS cases for the Wilson gate.
    owner_categories = [
        "missing-acceptance-criterion",
        "stale-verifier-claim",
        "review-thread-debt",
    ]
    corpus = {
        "corpus_version": "test-owner-v1",
        "cases": [
            {
                "case_id": f"owner-{index}",
                "repo": "example/owner-reviews",
                "pr": index + 1,
                "category": owner_categories[index % len(owner_categories)],
                "expected_verdict": "NON_PASS",
                "provenance": "owner-adjudicated",
            }
            for index in range(40)
        ],
    }
    grown, added = harvest.grow_corpus(
        corpus,
        promoted,
        max_size=growth["max_corpus_size"],
        category_caps=growth["category_caps"],
    )
    assert len(added) == 75
    assert len({case["case_id"] for case in added}) == 75
    assert all(
        case["expected_verdict"] == ("PASS" if case["pr"] <= 35 else "NON_PASS") for case in added
    )
    payload = {
        "profile": "verifier-balanced",
        "benchmark_id": "harvested-approval-test",
        "baseline_model_id": "claude-opus-4-6",
        "corpus_version": grown["corpus_version"],
        "prompt_version": "test-v1",
        "measured_at": TODAY.isoformat(),
        "candidates": [
            {
                "provider": "anthropic",
                "model_id": model_id,
                "cases": [
                    {
                        **case,
                        "actual_verdict": case["expected_verdict"],
                        "schema_valid": True,
                        "total_cost_usd": review_cost,
                        "latency_ms": 100,
                    }
                    for case in grown["cases"]
                ],
            }
            for model_id, review_cost in [("claude-opus-4-6", 0.10), (candidate, cost)]
        ],
    }
    return payload, policy


@pytest.mark.parametrize(
    "candidate,cost,reasons",
    [
        ("claude-opus-4-8", 0.08, []),
        ("claude-opus-4-8", 0.10, []),
        ("claude-sonnet-5", 0.08, ["cross-family"]),
        ("claude-opus-4-8", 0.20, ["cost-increase"]),
        ("claude-sonnet-5", 0.20, ["cross-family", "cost-increase"]),
    ],
)
def test_harvested_cases_pass_real_gates_and_prepare_registry(tmp_path, candidate, cost, reasons):
    payload, policy = _harvested_benchmark(candidate, cost)
    report = benchmark.evaluate_benchmark(payload, policy)
    assert all(all(result["gate_results"].values()) for result in report["results"])
    (proposal,) = pmp.find_promotions(report, _registry())
    assert proposal["preparation_mode"] == ("approval-required" if reasons else "bounded")
    assert proposal["approval_reasons"] == reasons
    assert proposal["human_approval_required"] is True
    bench, reg, out = (tmp_path / name for name in ("bench.json", "registry.json", "out.json"))
    bench.write_text(json.dumps(report))
    reg.write_text(json.dumps(_registry()))
    completed = _run_preparation_cli(bench, reg, out)
    assert completed.returncode == 10, completed.stdout + completed.stderr
    assert completed.stderr == ""
    assert f"PROMOTE anthropic: claude-opus-4-6 -> {candidate}" in completed.stdout
    if reasons:
        assert f"approval-required ({', '.join(reasons)})" in completed.stdout
    else:
        assert "same-family (claude-opus)" in completed.stdout
        assert "approval-required" not in completed.stdout
    prepared = json.loads(out.read_text())
    assert prepared["selections"][0]["model_id"] == candidate
    assert prepared["selections"][0]["decided_at"] == TODAY.isoformat()
    assert proposal["evidence_id"] in prepared["selections"][0]["evidence_ids"]
    assert prepared["selection_history"][0]["model_id"] == "claude-opus-4-6"
    assert json.loads(reg.read_text()) == _registry()


@pytest.mark.parametrize("failed_gate", ["minimum_adjudicated_cases", "minimum_cases_per_category"])
def test_harvested_cases_cannot_bypass_approval_gates(tmp_path, failed_gate):
    payload, policy = _harvested_benchmark("claude-opus-4-8", 0.08)
    for candidate in payload["candidates"]:
        if failed_gate == "minimum_adjudicated_cases":
            candidate["cases"] = candidate["cases"][:74]
        else:
            candidate["cases"] = [
                case for case in candidate["cases"] if case["provenance"] == "harvested"
            ]
    report = benchmark.evaluate_benchmark(payload, policy)
    assert all(result["gate_results"][failed_gate] is False for result in report["results"])
    assert pmp.find_promotions(report, _registry()) == []
    bench, reg, out = (tmp_path / name for name in ("bench.json", "registry.json", "out.json"))
    bench.write_text(json.dumps(report))
    reg.write_text(json.dumps(_registry()))
    completed = _run_preparation_cli(bench, reg, out)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stderr == ""
    assert "no passing promotion or gate-breach rollback to prepare" in completed.stdout
    assert "PROMOTE" not in completed.stdout
    assert not out.exists()
    assert json.loads(reg.read_text()) == _registry()


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
    assert props[0]["preparation_mode"] == "bounded"
    assert props[0]["human_approval_required"] is True
    assert props[0]["approval_reasons"] == []


def test_cross_family_requires_approval():
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-sonnet-5", "anthropic", status="passed", cost=0.02),
        ]
    )
    proposal = pmp.find_promotions(report, _registry())[0]
    assert proposal["preparation_mode"] == "approval-required"
    assert proposal["human_approval_required"] is True
    assert proposal["approval_reasons"] == ["cross-family"]


def test_more_expensive_same_family_requires_approval():
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.20),
        ]
    )
    proposal = pmp.find_promotions(report, _registry())[0]
    assert proposal["preparation_mode"] == "approval-required"
    assert proposal["human_approval_required"] is True
    assert proposal["approval_reasons"] == ["cost-increase"]


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
            _result("claude-sonnet-5", "anthropic", status="failed", cost=0.01),
        ]
    )
    bench = tmp_path / "bench.json"
    reg = tmp_path / "registry.json"
    bench.write_text(json.dumps(report))
    reg.write_text(json.dumps(_registry()))
    assert (
        pmp.main(["--benchmark", str(bench), "--registry", str(reg), "--today", "2026-08-01"]) == 0
    )


def _promoted_registry():
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.08),
        ]
    )
    return pmp.apply_promotion(
        _registry(), pmp.find_promotions(report, _registry())[0], today=TODAY
    )


def test_rollback_requires_matching_provider_and_failed_gate():
    registry = _promoted_registry()
    result = _result("claude-opus-4-8", "openai", status="failed", cost=0.08)
    assert pmp.find_rollbacks(_report([result]), registry) == []
    result["provider"] = "claude"  # Provider aliases still match.
    rollback = pmp.find_rollbacks(_report([result]), registry)[0]
    assert rollback["trigger"] == "quality_gate_breach"
    assert rollback["breached_gates"] == ["paired_success_noninferiority"]
    result["gate_results"] = {}
    assert pmp.find_rollbacks(_report([result]), registry) == []


def test_rollback_rejects_unrelated_history():
    registry = _promoted_registry()
    registry["selection_history"][0]["superseded_by"] = "claude-opus-4-7"
    breach = _report([_result("claude-opus-4-8", "anthropic", status="failed", cost=0.08)])
    assert pmp.find_rollbacks(breach, registry) == []


@pytest.mark.parametrize(
    "section,key",
    [
        ("selections", "model_id"),
        ("selection_history", "superseded_by"),
        ("selection_history", "model_id"),
    ],
)
def test_apply_rollback_rejects_stale_proposal(section, key):

    registry = _promoted_registry()
    breach = _report([_result("claude-opus-4-8", "anthropic", status="failed", cost=0.08)])
    rollback = pmp.find_rollbacks(breach, registry)[0]
    registry[section][0][key] = "claude-opus-4-9"
    before = json.dumps(registry, sort_keys=True)
    with pytest.raises(ValueError, match="no longer matches"):
        pmp.apply_rollback(registry, rollback, today=TODAY)
    assert json.dumps(registry, sort_keys=True) == before


def test_main_breach_takes_precedence_over_promotion(tmp_path):
    registry = _promoted_registry()
    report = _report(
        [
            _result("claude-opus-4-8", "anthropic", status="failed", cost=0.08),
            _result("claude-opus-4-9", "anthropic", status="passed", cost=0.06),
        ],
        baseline="claude-opus-4-8",
    )
    bench = tmp_path / "bench.json"
    reg = tmp_path / "registry.json"
    out = tmp_path / "out.json"
    bench.write_text(json.dumps(report))
    reg.write_text(json.dumps(registry))
    assert (
        pmp.main(
            [
                "--benchmark",
                str(bench),
                "--registry",
                str(reg),
                "--write",
                str(out),
                "--today",
                TODAY.isoformat(),
            ]
        )
        == 10
    )
    reverted = json.loads(out.read_text())
    assert reverted["selections"][0]["model_id"] == "claude-opus-4-6"
    assert reverted["selections"][0]["evidence_ids"] == ["catalog-1"]
    assert reverted["selection_history"] == []


@pytest.mark.parametrize(
    "candidate,cost,reasons",
    [
        ("claude-opus-4-8", 0.10, []),
        ("claude-sonnet-5", 0.20, ["cross-family", "cost-increase"]),
    ],
)
def test_cli_prepares_candidate_with_approval_context(tmp_path, candidate, cost, reasons):
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result(candidate, "anthropic", status="passed", cost=cost),
        ]
    )
    proposal = pmp.find_promotions(report, _registry())[0]
    assert proposal["approval_reasons"] == reasons
    bench, reg, out = (tmp_path / name for name in ("bench.json", "registry.json", "out.json"))
    bench.write_text(json.dumps(report))
    reg.write_text(json.dumps(_registry()))
    assert pmp.main(["--benchmark", str(bench), "--registry", str(reg), "--write", str(out)]) == 10
    selection = json.loads(out.read_text())["selections"][0]
    assert selection["model_id"] == candidate
    assert "requires human approval" in selection["rationale"]
    for reason in reasons:
        assert reason in selection["rationale"]


def test_bounded_candidate_wins_over_cheaper_cross_family_candidate():
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-sonnet-5", "anthropic", status="passed", cost=0.02),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.08),
        ]
    )
    proposals = pmp.find_promotions(report, _registry())
    assert len(proposals) == 1
    assert proposals[0]["to_model_id"] == "claude-opus-4-8"


@pytest.mark.parametrize("cost", [None, "invalid", float("nan"), float("inf"), -0.01, 10**400])
@pytest.mark.parametrize("invalid_baseline", [False, True])
def test_unusable_cost_cannot_prepare_promotion(cost, invalid_baseline):
    report = _report(
        [
            _result(
                "claude-opus-4-6",
                "anthropic",
                status="passed",
                cost=cost if invalid_baseline else 0.10,
            ),
            _result(
                "claude-opus-4-8",
                "anthropic",
                status="passed",
                cost=0.08 if invalid_baseline else cost,
            ),
        ]
    )
    assert pmp.find_promotions(report, _registry()) == []


@pytest.mark.parametrize("latency,expected", [(0, "claude-opus-4-9"), (None, "claude-opus-4-8")])
def test_equal_cost_candidates_rank_zero_latency_before_positive(latency, expected):
    report = _report(
        [
            _result("claude-opus-4-6", "anthropic", status="passed", cost=0.10),
            _result("claude-opus-4-8", "anthropic", status="passed", cost=0.08, latency=100),
            _result("claude-opus-4-9", "anthropic", status="passed", cost=0.08, latency=latency),
        ]
    )
    assert pmp.find_promotions(report, _registry())[0]["to_model_id"] == expected
