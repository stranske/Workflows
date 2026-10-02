"""The MAINT-78 decision gate must explain missing evidence before model calls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools.create_model_eval_snapshot import create_case
from tools.model_eval_snapshots import snapshot_digest, verifier_prompt
from tools.plan_model_eval import ROOT, build_plan, markdown
from tools.run_model_eval_api_confirm import MAX_OUTPUT_TOKENS, _invoke_api, _price, confirm
from tools.run_model_eval_cli_screen import (
    CliResult,
    api_list_price_estimate,
    cli_model_ids,
    has_tool_events,
    invoke_cli,
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


def _screen_inputs():
    corpus, registry, policy = _inputs()
    # Exercise the original Terra-to-candidate comparison even after promotion.
    openai_selection = next(item for item in registry["selections"] if item["provider"] == "openai")
    openai_selection["model_id"] = "gpt-5.6-terra"
    openai_selection["evidence_ids"] = ["catalog-review-2026-07-10"]
    corpus["screen_input_status"] = "production_context_adjudicated"
    cases = select_cases(corpus["cases"])
    corpus["screen_cases"] = json.loads(json.dumps(cases))
    cases = corpus["screen_cases"]
    for case in cases:
        if case["category"] in {"review-thread-debt", "stale-verifier-claim"}:
            case["category"] = "clean-pass"
    corpus["screen_case_ids"] = [case["case_id"] for case in cases]
    for case in cases:
        snapshot = {
            "context": f"context for {case['case_id']}",
            "diff_summary": f"diff summary for {case['case_id']}",
            "repository": case["repo"],
            "pr": case["pr"],
            "chain_depth": 0,
            "merge_sha": "a" * 40,
            "source_run_id": "123",
            "adjudication_evidence": "https://example.com/independent-review",
            "adjudicated_by": "test-reviewer",
            "adjudication_rationale": "Compared the merge evidence with acceptance criteria.",
            "input_kind": "production_capture",
        }
        snapshot["sha256"] = snapshot_digest(snapshot)
        case["production_snapshot"] = snapshot
    return corpus, registry, policy


def _prompt_hashes(cases):
    return {
        case["case_id"]: hashlib.sha256(
            verifier_prompt(case["production_snapshot"]).encode()
        ).hexdigest()
        for case in cases
    }


def test_current_plan_allows_fast_screen_without_statistical_approval():
    plan = build_plan(*_inputs())
    assert not plan["approval_ready"]
    assert plan["screen_ready"]
    assert plan["input_alignment_ready"]
    assert plan["screen_blockers"] == []
    assert len(plan["screen_case_kinds"]) == 8
    assert plan["automatic_api_calls"] == 0
    assert plan["corpus_cases"] == 51
    assert plan["approval_minimum_cases"] == 75
    assert plan["expected_non_pass_cases"] == 4
    assert plan["zero_error_false_pass_denominator"] == 73
    assert plan["additional_non_pass_cases_for_best_case_gate"] == 69
    assert plan["best_case_minimum_corpus_cases"] == 120
    assert plan["category_shortfalls"]["follow-up-required"] > 0
    assert plan["unpriced_openai_models"] == []


def test_readiness_summary_leads_with_the_current_decision():
    summary = markdown(build_plan(*_inputs()))
    assert "**Current OpenAI selection:** gpt-6-luna" in summary
    assert "Monitor the first ten live verifier outcomes" in summary
    assert summary.index("**Eight-case subscription screen ready:** yes") < summary.index(
        "### Separate long-term statistical approval"
    )
    assert summary.index("**Next action:**") < summary.index("**Best-case statistical floor:**")


def test_candidate_screen_uses_policy_case_and_failure_counts():
    corpus, registry, policy = _screen_inputs()
    changed = json.loads(json.dumps(policy))
    plan = build_plan(corpus, registry, changed)
    assert plan["screen_ready"]
    assert plan["screen_limit"]["cases"] == 8
    changed["profiles"]["verifier-balanced"]["provisional_stage"]["minimum_non_pass_cases"] = 5
    assert not build_plan(corpus, registry, changed)["screen_ready"]
    changed["profiles"]["verifier-balanced"]["provisional_stage"]["screen_cases"] = 6
    assert not build_plan(corpus, registry, changed)["screen_ready"]


def test_controlled_defect_screen_case_does_not_enter_statistical_denominator():
    corpus, registry, policy = _screen_inputs()
    negative = next(
        case for case in corpus["screen_cases"] if case["expected_verdict"] == "NON_PASS"
    )
    negative["production_snapshot"]["input_kind"] = "controlled_defect"
    negative["production_snapshot"]["mutation_note"] = "Controlled missing acceptance item."
    plan = build_plan(corpus, registry, policy)
    assert plan["screen_ready"]
    assert plan["corpus_cases"] == 51
    assert plan["expected_non_pass_cases"] == 4
    assert plan["screen_case_kinds"][negative["case_id"]] == "controlled_defect"
    assert {case["category"] for case in corpus["screen_cases"]} == {
        "clean-pass",
        "missing-acceptance-criterion",
        "follow-up-required",
    }


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
    corpus, registry, policy = _screen_inputs()
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


def test_cli_screen_advances_only_a_safer_cheaper_paired_candidate():
    corpus, registry, policy = _screen_inputs()
    cases = select_cases(corpus["cases"])
    rows = []
    for model, cost in (("gpt-5.6-terra", 0.008), ("gpt-6-luna", 0.001)):
        for case in cases:
            rows.append(
                {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "expected_verdict": case["expected_verdict"],
                    "actual_verdict": case["expected_verdict"],
                    "schema_valid": True,
                    "model_id": model,
                    "modeled_api_cost_usd": cost,
                }
            )
    plan = build_plan(corpus, registry, policy)
    result = report(plan, cases, ["gpt-5.6-terra", "gpt-6-luna"], rows, stopped_early=False)
    assert result["screen_decision"] == "advance_to_api_confirmation"
    assert result["provisional_shortlist_model_id"] == "gpt-6-luna"
    stricter_plan = {
        **plan,
        "provisional_thresholds": {
            **plan["provisional_thresholds"],
            "minimum_accuracy_delta_vs_incumbent": 1,
        },
    }
    assert (
        report(stricter_plan, cases, ["gpt-5.6-terra", "gpt-6-luna"], rows, stopped_early=False)[
            "provisional_shortlist_model_id"
        ]
        is None
    )
    next(
        row
        for row in rows
        if row["model_id"] == "gpt-6-luna" and row["expected_verdict"] == "NON_PASS"
    )["actual_verdict"] = "PASS"
    result = report(plan, cases, ["gpt-5.6-terra", "gpt-6-luna"], rows, stopped_early=False)
    assert result["provisional_shortlist_model_id"] is None


def test_api_confirmation_is_paired_bounded_and_still_provisional(monkeypatch):
    corpus, registry, policy = _screen_inputs()
    plan = build_plan(corpus, registry, policy)
    cases = corpus["screen_cases"]
    screen = {
        "schema": "workflows-verifier-cli-screen/v1",
        "screen_decision": "advance_to_api_confirmation",
        "input_fingerprint": plan["input_fingerprint"],
        "screen_harness_fingerprint": plan["screen_harness_fingerprint"],
        "provisional_shortlist_model_id": "gpt-6-luna",
        "case_ids": [case["case_id"] for case in cases],
        "prompt_sha256_by_case": _prompt_hashes(cases),
        "stopped_early": False,
    }
    calls = []

    def fake_api(client, model, prompt):
        index = len(calls) // 2
        calls.append(model["model_id"])
        return (
            json.dumps(
                {"verdict": cases[index]["expected_verdict"].replace("NON_PASS", "CONCERNS")}
            ),
            1000,
            100,
        )

    monkeypatch.setattr("tools.run_model_eval_api_confirm._invoke_api", fake_api)
    result = confirm(corpus, registry, policy, screen, github_token="x", client=object())
    assert result["complete"]
    assert result["api_calls_made"] == 16
    assert result["reserved_standard_rate_upper_bound_usd"] <= 5
    assert result["decision"] == "provisional_change_for_human_review"
    assert result["provisional_model_id"] == "gpt-6-luna"
    assert not result["statistical_approval"]

    screen["input_fingerprint"] = "stale"
    with pytest.raises(ValueError, match="current CLI screen"):
        confirm(corpus, registry, policy, screen, github_token="x", client=object())
    assert len(calls) == 16

    screen["input_fingerprint"] = plan["input_fingerprint"]
    screen["screen_harness_fingerprint"] = "stale"
    with pytest.raises(ValueError, match="current CLI screen"):
        confirm(corpus, registry, policy, screen, github_token="x", client=object())
    screen["screen_harness_fingerprint"] = plan["screen_harness_fingerprint"]

    first_id = screen["case_ids"][0]
    original_hash = screen["prompt_sha256_by_case"][first_id]
    screen["prompt_sha256_by_case"][first_id] = "stale"
    with pytest.raises(ValueError, match="prompt changed after screen"):
        confirm(corpus, registry, policy, screen, github_token="x", client=object())
    screen["prompt_sha256_by_case"][first_id] = original_hash
    assert len(calls) == 16

    # A tiny ceiling must stop before a paid call or a partial pair.
    strict_policy = json.loads(json.dumps(policy))
    strict_policy["profiles"]["verifier-balanced"]["provisional_stage"][
        "maximum_api_confirmation_cost_usd"
    ] = 0.0001
    screen["input_fingerprint"] = build_plan(corpus, registry, strict_policy)["input_fingerprint"]
    capped = confirm(corpus, registry, strict_policy, screen, github_token="x", client=object())
    assert capped["api_calls_made"] == 0
    assert not capped["complete"]
    assert len(calls) == 16

    calls.clear()
    strict_policy = json.loads(json.dumps(policy))
    strict_policy["profiles"]["verifier-balanced"]["provisional_stage"][
        "minimum_accuracy_delta_vs_incumbent"
    ] = 1
    screen["input_fingerprint"] = build_plan(corpus, registry, strict_policy)["input_fingerprint"]
    tied = confirm(corpus, registry, strict_policy, screen, github_token="x", client=object())
    assert tied["complete"]
    assert tied["provisional_model_id"] is None


def test_api_confirmation_uses_each_models_production_route_without_retries():
    received = []

    def responses_create(**kwargs):
        received.append(("responses", kwargs))
        return SimpleNamespace(
            output_text='{"verdict":"PASS"}',
            usage=SimpleNamespace(input_tokens=101, output_tokens=102),
        )

    def chat_create(**kwargs):
        received.append(("chat", kwargs))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"verdict":"CONCERNS"}'))],
            usage=SimpleNamespace(prompt_tokens=201, completion_tokens=202),
        )

    client = SimpleNamespace(
        responses=SimpleNamespace(create=responses_create),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
    )
    assert _invoke_api(client, {"model_id": "gpt-6-sol", "api": "responses"}, "prompt") == (
        '{"verdict":"PASS"}',
        101,
        102,
    )
    assert _invoke_api(client, {"model_id": "gpt-5.6-terra", "api": "chat"}, "prompt") == (
        '{"verdict":"CONCERNS"}',
        201,
        202,
    )
    assert received[0][1]["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert received[1][1]["max_completion_tokens"] == MAX_OUTPUT_TOKENS
    assert "temperature" not in received[1][1]
    _invoke_api(client, {"model_id": "gpt-5.4", "api": "chat"}, "prompt")
    assert received[2][1]["temperature"] == 0.1


def test_api_cost_reservation_rejects_invalid_registry_rates():
    for bad in (-1, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="finite, nonnegative"):
            _price(1000, 4096, {"input_per_million_tokens": bad, "output_per_million_tokens": 10})


def test_api_only_exception_requires_explicit_cli_absence_and_same_cases(monkeypatch):
    corpus, registry, policy = _screen_inputs()
    cases = corpus["screen_cases"]
    screen = {
        "schema": "workflows-verifier-cli-screen/v1",
        "screen_decision": "retain_incumbent_on_screen",
        "input_fingerprint": build_plan(corpus, registry, policy)["input_fingerprint"],
        "screen_harness_fingerprint": build_plan(corpus, registry, policy)[
            "screen_harness_fingerprint"
        ],
        "provisional_shortlist_model_id": None,
        "case_ids": [case["case_id"] for case in cases],
        "prompt_sha256_by_case": _prompt_hashes(cases),
        "stopped_early": False,
    }
    catalog = {
        "models": [
            {"slug": "gpt-5.6-terra", "visibility": "list", "supported_in_api": True},
            {"slug": "gpt-6-sol", "visibility": "list", "supported_in_api": True},
        ]
    }
    calls = []

    def fake_api(client, model, prompt):
        expected = cases[len(calls) // 2]["expected_verdict"]
        calls.append(model["model_id"])
        return json.dumps({"verdict": expected.replace("NON_PASS", "CONCERNS")}), 1000, 100

    monkeypatch.setattr("tools.run_model_eval_api_confirm._invoke_api", fake_api)
    result = confirm(
        corpus,
        registry,
        policy,
        screen,
        github_token="x",
        client=object(),
        api_only_candidate="gpt-6.1-sol",
        cli_catalog=catalog,
    )
    assert result["complete"] and result["api_calls_made"] == 16
    assert result["comparison_path"] == "api_only"
    assert result["provisional_model_id"] == "gpt-6.1-sol"
    with pytest.raises(ValueError, match="absent from the pinned CLI"):
        confirm(
            corpus,
            registry,
            policy,
            screen,
            github_token="x",
            client=object(),
            api_only_candidate="gpt-6-sol",
            cli_catalog=catalog,
        )
    assert len(calls) == 16


def test_missing_cli_usage_fails_closed():
    assert token_usage(
        '{"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}'
    ) == (2, 3)
    with pytest.raises(ValueError, match="token usage"):
        token_usage('{"type":"turn.failed"}')


def test_cli_screen_rejects_unpaired_or_unpriced_selection_before_fetch(monkeypatch):
    corpus, registry, policy = _screen_inputs()
    monkeypatch.setattr(
        "tools.run_model_eval_cli_screen.cli_model_ids", lambda _: {"gpt-5.6-terra", "gpt-6-astra"}
    )
    with pytest.raises(ValueError, match="incumbent"):
        run_screen(corpus, registry, policy, models=["gpt-6-astra", "gpt-5.6-sol"], token="x")
    with pytest.raises(ValueError, match="verified registry prices"):
        run_screen(corpus, registry, policy, models=["gpt-5.6-terra", "gpt-unpriced"], token="x")


def test_cli_catalog_is_pinned_and_tool_events_are_rejected(monkeypatch):
    received = {}

    def fake_catalog(command, **kwargs):
        received["command"] = command
        return SimpleNamespace(
            stdout=json.dumps(
                {"models": [{"slug": "gpt-6-sol", "visibility": "list", "supported_in_api": True}]}
            )
        )

    monkeypatch.setattr("tools.run_model_eval_cli_screen.subprocess.run", fake_catalog)
    assert cli_model_ids("codex") == {"gpt-6-sol"}
    assert received["command"][-1] == "--bundled"
    assert not has_tool_events('{"type":"item.completed","item":{"type":"agent_message"}}')
    assert has_tool_events('{"type":"item.completed","item":{"type":"command_execution"}}')
    assert has_tool_events('{"type":"item.completed","item":{"type":"web_search"}}')
    assert not has_tool_events(
        '{"type":"item.completed","item":{"type":"error","message":'
        '"Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; enable features.code_mode_host."}}'
    )


def test_invalid_json_preserves_cli_usage_and_does_not_stop_screen(monkeypatch):
    stream = '{"type":"turn.completed","usage":{"input_tokens":1000,"output_tokens":500}}'
    monkeypatch.setenv("GH_TOKEN", "do-not-pass-to-model-tools")

    def fake_invocation(command, **kwargs):
        assert "GH_TOKEN" not in kwargs["env"]
        assert command[command.index("--disable") + 1] == "shell_tool"
        assert [command[i + 1] for i, part in enumerate(command) if part == "--disable"] == [
            "shell_tool",
            "code_mode_host",
            "browser_use",
            "in_app_browser",
            "apps",
            "computer_use",
            "skill_search",
        ]
        assert command[command.index("--config") + 1] == 'web_search="disabled"'
        final = Path(command[command.index("--output-last-message") + 1])
        final.write_text("not JSON")
        return SimpleNamespace(stdout=stream, returncode=0)

    monkeypatch.setattr("tools.run_model_eval_cli_screen.subprocess.run", fake_invocation)
    outcome = invoke_cli("codex", "gpt-5.6-terra", "test")
    assert outcome.payload is None
    assert outcome.input_tokens == 1000 and outcome.output_tokens == 500
    assert outcome.latency_ms >= 0
    assert outcome.error == "Invalid verifier JSON"
    assert not outcome.stop_screen

    corpus, registry, policy = _screen_inputs()
    calls = []

    def fake_screen_invocation(*args):
        calls.append(args)
        if len(calls) == 1:
            return outcome
        return CliResult({"verdict": "PASS"}, 1000, 500, 1.0)

    monkeypatch.setattr(
        "tools.run_model_eval_cli_screen.cli_model_ids",
        lambda _: {"gpt-5.6-terra", "gpt-6-sol"},
    )
    monkeypatch.setattr("tools.run_model_eval_cli_screen.invoke_cli", fake_screen_invocation)
    result = run_screen(
        corpus,
        registry,
        policy,
        models=["gpt-5.6-terra", "gpt-6-sol"],
        token="x",
    )
    assert len(result["rows"]) == 16
    assert not result["stopped_early"]
    assert result["rows"][0]["schema_valid"] is False
    assert result["rows"][0]["modeled_api_cost_usd"] > 0


def test_all_non_pass_candidate_cannot_advance_from_balanced_screen():
    corpus, registry, policy = _screen_inputs()
    cases = select_cases(corpus["cases"])
    rows = []
    for model in ("gpt-5.6-terra", "gpt-6-luna"):
        for case in cases:
            expected = case["expected_verdict"]
            actual = expected
            if model == "gpt-6-luna" and expected == "PASS":
                actual = "NON_PASS"
            if model == "gpt-5.6-terra" and expected == "NON_PASS":
                actual = "PASS" if len(rows) == 4 else "NON_PASS"
            rows.append(
                {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "expected_verdict": expected,
                    "actual_verdict": actual,
                    "schema_valid": True,
                    "model_id": model,
                    "modeled_api_cost_usd": 0.01 if model == "gpt-5.6-terra" else 0.001,
                }
            )
    result = report(
        build_plan(corpus, registry, policy),
        cases,
        ["gpt-5.6-terra", "gpt-6-luna"],
        rows,
        stopped_early=False,
    )
    assert result["provisional_shortlist_model_id"] is None
    luna = next(row for row in result["models"] if row["model_id"] == "gpt-6-luna")
    assert luna["pass_correct"] == 0


def test_unaligned_confirmation_is_rejected_before_any_api_call():
    corpus, registry, policy = _inputs()
    corpus["screen_input_status"] = "unverified_posthoc_labels"
    with pytest.raises(ValueError, match="adjudicated production-context inputs"):
        confirm(corpus, registry, policy, {}, github_token="x", client=object())


def test_changed_production_snapshot_blocks_screen_before_model_calls(monkeypatch):
    corpus, registry, policy = _screen_inputs()
    first = next(
        case for case in corpus["screen_cases"] if case["case_id"] == corpus["screen_case_ids"][0]
    )
    first["production_snapshot"]["context"] += "\nchanged after adjudication"
    assert not build_plan(corpus, registry, policy)["screen_ready"]

    def unexpected_catalog(_):
        raise AssertionError("model catalog must not be read when the snapshot is invalid")

    monkeypatch.setattr("tools.run_model_eval_cli_screen.cli_model_ids", unexpected_catalog)
    with pytest.raises(ValueError, match="candidate screen is not ready"):
        run_screen(
            corpus,
            registry,
            policy,
            models=["gpt-5.6-terra", "gpt-6-luna"],
            token="",
        )


def test_snapshot_identity_depth_and_defect_label_fail_closed():
    corpus, registry, policy = _screen_inputs()
    first = corpus["screen_cases"][0]
    snapshot = first["production_snapshot"]
    snapshot["repository"] = "stranske/Different-Repo"
    snapshot["sha256"] = snapshot_digest(snapshot)
    assert not build_plan(corpus, registry, policy)["screen_ready"]

    corpus, registry, policy = _screen_inputs()
    first = corpus["screen_cases"][0]
    snapshot = first["production_snapshot"]
    snapshot["chain_depth"] = True
    snapshot["sha256"] = snapshot_digest(snapshot)
    assert not build_plan(corpus, registry, policy)["screen_ready"]

    corpus, registry, policy = _screen_inputs()
    first = next(case for case in corpus["screen_cases"] if case["expected_verdict"] == "PASS")
    first["production_snapshot"]["input_kind"] = "controlled_defect"
    first["production_snapshot"]["mutation_note"] = "Deliberate defect."
    assert not build_plan(corpus, registry, policy)["screen_ready"]


def test_duplicate_prompt_snapshot_cannot_be_counted_twice():
    corpus, registry, policy = _screen_inputs()
    first, second = corpus["screen_cases"][:2]
    second["production_snapshot"] = json.loads(json.dumps(first["production_snapshot"]))
    second["repo"] = first["repo"]
    second["pr"] = first["pr"]
    assert not build_plan(corpus, registry, policy)["screen_ready"]


def test_snapshot_import_checks_capture_hash_and_marks_controlled_defects(tmp_path):
    context = "# Verifier context\nacceptance at merge\n"
    diff_summary = "## PR Diff Summary\n- one missing task\n"
    (tmp_path / "verifier-context.md").write_text(context)
    (tmp_path / "verifier-diff-summary.md").write_text(diff_summary)
    manifest = {
        "schema": "workflows-verifier-input-snapshot/v1",
        "repository": "stranske/Workflows",
        "pr": 10,
        "merge_sha": "a" * 40,
        "source_run_id": "123",
        "chain_depth": 1,
        "context_sha256": hashlib.sha256(context.encode()).hexdigest(),
        "diff_summary_sha256": hashlib.sha256(diff_summary.encode()).hexdigest(),
    }
    (tmp_path / "verifier-input-manifest.json").write_text(json.dumps(manifest))
    kwargs = {
        "case_id": "workflows-10-seeded",
        "expected_verdict": "NON_PASS",
        "category": "missing-acceptance-criterion",
        "adjudication_evidence": "https://example.com/review",
        "adjudicated_by": "reviewer",
        "adjudication_rationale": "One acceptance item is absent from the supplied summary.",
    }
    override = tmp_path / "missing-task.md"
    override.write_text("## PR Diff Summary\n- task deliberately omitted\n")
    context_override = tmp_path / "missing-context.md"
    context_override.write_text("# Verifier context\nacceptance at merge; task omitted from code\n")
    case = create_case(
        tmp_path,
        **kwargs,
        context_override=context_override,
        diff_summary_override=override,
        mutation_note="Removed the implemented task from the diff summary.",
    )
    assert case["production_snapshot"]["input_kind"] == "controlled_defect"
    assert case["production_snapshot"]["source_context_sha256"] == manifest["context_sha256"]
    (tmp_path / "verifier-context.md").write_text(context + "tampered")
    with pytest.raises(ValueError, match="captured manifest"):
        create_case(tmp_path, **kwargs)
    (tmp_path / "verifier-context.md").write_text(context)
    manifest["capture_kind"] = "retrospective"
    (tmp_path / "verifier-input-manifest.json").write_text(json.dumps(manifest))
    retrospective = create_case(tmp_path, **kwargs)
    assert retrospective["production_snapshot"]["input_kind"] == "retrospective_capture"
