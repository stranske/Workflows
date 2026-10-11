"""Capture obligations must reach snapshots and expanded native invocation gates."""

from __future__ import annotations

import hashlib
import json
import sys
from unittest import mock

import pytest
from scripts.langchain import pr_verifier
from tools.verifier_capture_obligation_manifest import build_capture_obligation_manifest

from tests.scripts.verifier_capacity_fakes import complete_capture_context, with_capacity


def _captured_snapshot(tmp_path):
    context = tmp_path / "verifier-context.md"
    context.write_text(complete_capture_context())
    snapshot = tmp_path / "verifier-input-manifest.json"
    metadata = {
        "schema": "workflows-verifier-input-snapshot/v1",
        "repository": "owner/repo",
        "merge_sha": "a" * 40,
        "context_sha256": hashlib.sha256(context.read_bytes()).hexdigest(),
        "diff_sha256": "b" * 64,
        "evidence_profile": "expanded",
    }
    snapshot.write_text(json.dumps(metadata))
    return context, snapshot, metadata


@pytest.mark.parametrize("compare", [False, True])
def test_cli_records_obligations_in_snapshot_before_evaluation(tmp_path, monkeypatch, compare):
    context, snapshot, metadata = _captured_snapshot(tmp_path)
    original = context.read_bytes()

    def evaluate(*args, **kwargs):
        recorded = json.loads(snapshot.read_text())
        assert {key: recorded[key] for key in metadata} == metadata
        assert recorded["capture_obligations"] == build_capture_obligation_manifest(
            context.read_text()
        )
        result = pr_verifier.EvaluationResult(verdict="CONCERNS")
        return [result] if compare else result

    monkeypatch.setattr(pr_verifier, "evaluate_pr_multiple" if compare else "evaluate_pr", evaluate)
    monkeypatch.setattr(
        sys,
        "argv",
        ["verifier", "--context-file", str(context), "--json"] + (["--compare"] if compare else []),
    )
    pr_verifier.main()
    assert context.read_bytes() == original


@pytest.mark.parametrize(
    "defect", ["missing", "truncated", "unavailable", "malformed", "discovery"]
)
@pytest.mark.parametrize("compare", [False, True])
def test_expanded_manifest_gaps_block_before_count_and_generation(monkeypatch, defect, compare):
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    context = complete_capture_context()
    if defect == "missing":
        context = "missing coverage"
    elif defect == "truncated":
        context = context.replace('"status": "included"', '"status": "truncated"', 1)
    elif defect == "unavailable":
        context = context.replace(
            '"acceptance_evidence_sources": []',
            '"acceptance_evidence_sources": [{"source": "artifacts", "status": "unavailable", "reason": "archive_bytes_exhausted"}]',
        )
    elif defect == "malformed":
        context = context.replace('"stage": "generated-context"', '"stage": "unknown"')
    else:
        context = context.replace(
            '"required": false, "status": "included"', '"required": true, "status": "unavailable"'
        )
    client = with_capacity(mock.Mock())
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: (client, "unit"))
    if compare:
        runner = pr_verifier.ComparisonRunner(
            context, None, pr_verifier._prepare_prompt(context, None), []
        )
        result = runner.run_single(client, "unit", "unit-test-model")
    else:
        result = pr_verifier.evaluate_pr(context)
    assert result.verdict == "CONCERNS"
    assert "capture" in result.error.lower()
    assert not result.used_llm
    client.root_client.responses.input_tokens.count.assert_not_called()
    client.invoke.assert_not_called()


def test_expanded_prompt_clipping_blocks_complete_capture(monkeypatch):
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "1")
    client = with_capacity(mock.Mock())
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: (client, "unit"))
    result = pr_verifier.evaluate_pr(complete_capture_context())
    assert result.verdict == "CONCERNS"
    assert "prompt" in result.error.lower()
    client.invoke.assert_not_called()


@pytest.mark.parametrize("overflow", [False, True])
def test_native_receipt_retains_manifest_and_exact_capacity_outcome(
    tmp_path, monkeypatch, overflow
):
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    report = tmp_path / "capacity.jsonl"
    monkeypatch.setenv("VERIFIER_CAPACITY_REPORT_PATH", str(report))
    client = with_capacity(mock.Mock())
    if overflow:
        client.root_client.responses.input_tokens.count.return_value.input_tokens = 1_000_001
    context = complete_capture_context()
    prompt = pr_verifier._prepare_prompt(context, None)
    if overflow:
        with pytest.raises(pr_verifier.InputCapacityError, match="overflow"):
            pr_verifier._invoke_llm(client, prompt, operation="test", context=context)
        client.invoke.assert_not_called()
    else:
        pr_verifier._invoke_llm(client, prompt, operation="test", context=context)
        client.invoke.assert_called_once()
    receipt = json.loads(report.read_text())
    assert receipt["capture_obligations"] == build_capture_obligation_manifest(context)
    assert receipt["status"] == ("overflow" if overflow else "PASS")
    assert receipt["prompt_chars"] == len(prompt)


def test_snapshot_identity_mismatch_blocks_without_overwriting(tmp_path, monkeypatch):
    context, snapshot, _ = _captured_snapshot(tmp_path)
    context.write_text(context.read_text() + "changed after capture\n")
    original = snapshot.read_bytes()
    evaluate = mock.Mock()
    monkeypatch.setattr(pr_verifier, "evaluate_pr", evaluate)
    monkeypatch.setattr(sys, "argv", ["verifier", "--context-file", str(context)])
    with pytest.raises(ValueError, match="context.*snapshot"):
        pr_verifier.main()
    evaluate.assert_not_called()
    assert snapshot.read_bytes() == original


def test_clipped_prompt_cannot_reuse_complete_capture(monkeypatch):
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    context = complete_capture_context()
    client = with_capacity(mock.Mock())
    prompt = pr_verifier._prepare_prompt(context, None)
    with pytest.raises(pr_verifier.InputCapacityError, match="prompt does not match"):
        pr_verifier._invoke_llm(client, prompt[:-10], operation="test", context=context)
    client.root_client.responses.input_tokens.count.assert_not_called()
    client.invoke.assert_not_called()


def test_capture_receipt_retains_all_gaps_and_actionable_reasons(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    report = tmp_path / "capacity.jsonl"
    monkeypatch.setenv("VERIFIER_CAPACITY_REPORT_PATH", str(report))
    context = complete_capture_context().replace(
        '"acceptance_evidence_sources": []',
        '"acceptance_evidence_sources": ['
        '{"source": "comments", "status": "truncated", "reason": "comment_chars_exhausted"},'
        '{"source": "artifact:9", "status": "unavailable", "reason": "archive_bytes_exhausted"}]',
    )
    client = with_capacity(mock.Mock())
    with pytest.raises(pr_verifier.InputCapacityError, match="capture obligation gaps"):
        pr_verifier._invoke_llm(
            client, pr_verifier._prepare_prompt(context, None), operation="test", context=context
        )
    receipt = json.loads(report.read_text())
    manifest = receipt["capture_obligations"]
    assert manifest["gaps"] == [
        "acceptance_evidence:comments:truncated",
        "acceptance_evidence:artifact:9:unavailable",
    ]
    reasons = {item.get("reason") for item in manifest["obligations"]}
    assert {"comment_chars_exhausted", "archive_bytes_exhausted"} <= reasons
    assert receipt["status"] == "unavailable"
    client.invoke.assert_not_called()


@pytest.mark.parametrize("defect", ["wrong-schema", "duplicate-key", "conflicting-obligations"])
def test_ambiguous_snapshot_blocks_without_repair(tmp_path, monkeypatch, defect):
    context, snapshot, metadata = _captured_snapshot(tmp_path)
    if defect == "wrong-schema":
        metadata["schema"] = "unknown/v2"
        snapshot.write_text(json.dumps(metadata))
    elif defect == "conflicting-obligations":
        metadata["capture_obligations"] = {"sufficient": True}
        snapshot.write_text(json.dumps(metadata))
    else:
        snapshot.write_text(snapshot.read_text()[:-1] + ', "schema": "unknown/v2"}')
    original = snapshot.read_bytes()
    evaluate = mock.Mock()
    monkeypatch.setattr(pr_verifier, "evaluate_pr", evaluate)
    monkeypatch.setattr(sys, "argv", ["verifier", "--context-file", str(context)])
    with pytest.raises(ValueError):
        pr_verifier.main()
    evaluate.assert_not_called()
    assert snapshot.read_bytes() == original


def test_cli_without_snapshot_emits_standalone_inventory(tmp_path, monkeypatch):
    context = tmp_path / "verifier-context.md"
    context.write_text(complete_capture_context())
    monkeypatch.setattr(
        pr_verifier,
        "evaluate_pr",
        lambda *args, **kwargs: pr_verifier.EvaluationResult(verdict="CONCERNS"),
    )
    monkeypatch.setattr(sys, "argv", ["verifier", "--context-file", str(context)])
    pr_verifier.main()
    manifest = json.loads((tmp_path / "verifier-capture-obligation-manifest.json").read_text())
    assert manifest == build_capture_obligation_manifest(context.read_text())
    assert manifest["sufficient"]
