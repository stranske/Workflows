"""Capture obligation recording failures must yield structured FAIL without LLM calls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.langchain import pr_verifier


@pytest.fixture
def merge_patch_4509():
    root = Path(__file__).resolve().parents[2]
    fixture = json.loads(
        (root / ".github/scripts/__tests__/fixtures/verifier-4509-merge.json").read_text(
            encoding="utf-8"
        )
    )
    patch = fixture["patch"].encode("utf-8")
    assert hashlib.sha256(patch).hexdigest() == (
        "fe6672ef4ff28986e3fe79f91575f60092dbc45ec9e2d3fd9f322adb4885bc8a"
    )
    assert fixture["patch_sha256"] == hashlib.sha256(patch).hexdigest()
    return patch.decode("utf-8")


@pytest.mark.parametrize("failure_kind", ["provenance", "extraction_byte", "character"])
def test_4509_capture_gaps_withhold_review_of_both_changed_files(failure_kind, merge_patch_4509):
    """Replay the original failure classes against the exact merged two-file diff.

    This is an admission regression, not the original input bundle or a provider
    assessment. Complete changed code cannot cure unavailable required proof.
    """
    patch = merge_patch_4509
    coverage = {
        "schema": "verifier-context-source-coverage/v1",
        "stage": "generated-context",
        "acceptance_sources": [
            {
                "source": "Pull request #4509",
                "status": "included",
                "included_chars": 1,
                "total_chars": 1,
            }
        ],
        "acceptance_source_discovery": {"required": False, "status": "included"},
        "changed_code_sources": [
            {"source": name, "status": "included", "included_chars": 1, "total_chars": 1}
            for name in ["scripts/ci_history.py", "tests/scripts/test_ci_history.py"]
        ],
        "full_diff_artifact": {
            "source": "verifier-pr-diff.patch",
            "status": "included",
            "chars": len(patch),
        },
        "acceptance_evidence_sources": [
            {
                "channel": "artifacts",
                "source": "artifacts",
                "status": "unavailable",
                "failure_kinds": [failure_kind, "extraction_incomplete"],
            }
        ],
    }
    context = (
        "# Verifier context\n\n## Context source coverage\n\n```json\n"
        + json.dumps(coverage)
        + "\n```\n\n## CI Information\n\n| CI | success |\n\n"
        + "## Plan sources (scope, tasks, acceptance)\n\n### Acceptance criteria\n"
        + "- [ ] Attach consumer validation artifacts.\n\n"
        + "## Acceptance evidence\n\n- Overall retrieval status: **unavailable**\n"
        + "- Referenced workflow artifacts: **unavailable**\n\n"
        + "## PR Diff (full)\n\n```diff\n"
        + patch
        + "```\n"
    )
    # An accidental provider invocation fails: this object has no client methods.
    result = pr_verifier._evaluate_chunked(
        object(), context, patch, "fixture", None, evaluate_minimum=False
    )
    assert result is not None
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.used_llm is False
    assert result.files_not_reviewed == [
        "scripts/ci_history.py",
        "tests/scripts/test_ci_history.py",
    ]
    assert result.input_coverage["files_complete"] == 0


@pytest.mark.parametrize("mode", ["evaluate", "compare"])
@pytest.mark.parametrize(
    "omitted",
    [
        [],
        ["scripts/ci_history.py"],
        ["tests/scripts/test_ci_history.py"],
        ["scripts/ci_history.py", "tests/scripts/test_ci_history.py"],
    ],
)
def test_4509_provider_pass_requires_review_of_both_changed_files(
    monkeypatch, merge_patch_4509, mode, omitted
):
    """Synthetic provider replies test review accounting, not live acceptance.

    A provider returning PASS while declining either assigned file must still
    yield a non-PASS report, even when the exact merged diff is supplied in full.
    """
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "16000")
    context = "Review both changed files for the duplicate-annotation fix and its regression."
    calls = []

    def invoke(client, prompt, **kwargs):
        calls.append(kwargs)
        assert merge_patch_4509.strip() in prompt
        return (
            SimpleNamespace(
                content=json.dumps(
                    {
                        "verdict": "PASS",
                        "summary": "Synthetic review.",
                        "files_not_reviewed": omitted,
                    }
                )
            ),
            None,
            None,
        )

    monkeypatch.setattr(pr_verifier, "_invoke_llm", invoke)
    client = object()
    if mode == "compare":
        coverage = pr_verifier.prompt_coverage(context, merge_patch_4509)
        runner = pr_verifier.ComparisonRunner(
            context,
            merge_patch_4509,
            pr_verifier._prepare_prompt(context, merge_patch_4509),
            [],
            coverage,
        )
        result = runner.run_single(client, "fixture", "fixture")
    else:
        monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: (client, "fixture"))
        result = pr_verifier.evaluate_pr(context, merge_patch_4509)

    assert len(calls) == 1
    assert result.used_llm is True
    assert result.files_not_reviewed == omitted
    assert result.input_coverage["files_total"] == 2
    assert result.input_coverage["files_complete"] == 2 - len(omitted)
    assert result.verdict == ("UNVERIFIABLE_INPUT" if omitted else "PASS")
    report = pr_verifier.format_comparison_report([result])
    assert f"files reviewed {2 - len(omitted)} of 2" in report
    for name in omitted:
        assert name in report


def _argv(monkeypatch, tmp_path, context: object, *args: str) -> None:
    monkeypatch.setattr(
        pr_verifier.sys,
        "argv",
        ["pr_verifier.py", "--context-file", str(context), *args],
    )


def test_invalid_utf8_context_emits_fail_without_evaluation(tmp_path, monkeypatch, capsys) -> None:
    context = tmp_path / "context.md"
    context.write_bytes(b"\xff\xfe")
    monkeypatch.setattr(
        pr_verifier,
        "evaluate_pr",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("evaluate_pr must not run")),
    )
    _argv(monkeypatch, tmp_path, context)
    pr_verifier.main()
    captured = capsys.readouterr()
    assert "Verdict: FAIL" in captured.out
    assert "Capture validation failed" in captured.out


def test_corrupt_snapshot_emits_fail_without_evaluation(tmp_path, monkeypatch, capsys) -> None:
    context = tmp_path / "context.md"
    context.write_text("Pull request: [#7](https://x/pull/7)\n", encoding="utf-8")
    (tmp_path / "verifier-input-manifest.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(
        pr_verifier,
        "evaluate_pr",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("evaluate_pr must not run")),
    )
    _argv(monkeypatch, tmp_path, context)
    pr_verifier.main()
    captured = capsys.readouterr()
    assert "Verdict: FAIL" in captured.out


@pytest.mark.parametrize("extra_args", [[], ["--compare"]])
def test_capture_failure_compare_mode_skips_provider_evaluation(
    tmp_path, monkeypatch, capsys, extra_args: list[str]
) -> None:
    context = tmp_path / "context.md"
    context.write_bytes(b"\xff\xfe")
    monkeypatch.setattr(
        pr_verifier,
        "evaluate_pr",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("evaluate_pr must not run")),
    )
    monkeypatch.setattr(
        pr_verifier,
        "evaluate_pr_multiple",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("evaluate_pr_multiple must not run")),
    )
    _argv(monkeypatch, tmp_path, context, *extra_args)
    pr_verifier.main()
    captured = capsys.readouterr()
    if "--compare" in extra_args:
        assert "FAIL" in captured.out
        assert "Provider Summary" in captured.out
    else:
        assert "Verdict: FAIL" in captured.out


def test_capture_failure_json_payload(tmp_path, monkeypatch, capsys) -> None:
    context = tmp_path / "context.md"
    context.write_bytes(b"\xff\xfe")
    monkeypatch.setattr(
        pr_verifier,
        "evaluate_pr",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("evaluate_pr must not run")),
    )
    _argv(monkeypatch, tmp_path, context, "--json")
    pr_verifier.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "FAIL"
    assert payload["used_llm"] is False


@pytest.mark.parametrize("extra_args", [[], ["--compare"]])
def test_conflicting_byte_inventory_emits_fail_without_provider_calls(
    tmp_path, monkeypatch, capsys, extra_args
):
    import hashlib

    context = tmp_path / "context.md"
    context.write_bytes(b"Pull request: [#7](https://x/pull/7)\r\n")
    snapshot = tmp_path / "verifier-input-manifest.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema": "workflows-verifier-input-snapshot/v1",
                "context_sha256": hashlib.sha256(context.read_bytes()).hexdigest(),
                "capture_byte_inventory": {"schema": "unknown", "inputs": []},
            }
        )
    )
    before = snapshot.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("provider evaluation must not run")

    monkeypatch.setattr(pr_verifier, "evaluate_pr", forbidden)
    monkeypatch.setattr(pr_verifier, "evaluate_pr_multiple", forbidden)
    _argv(monkeypatch, tmp_path, context, *extra_args, "--json")
    pr_verifier.main()
    payload = json.loads(capsys.readouterr().out)
    if extra_args:
        assert payload["results"][0]["verdict"] == "FAIL"
        assert payload["results"][0]["used_llm"] is False
    else:
        assert payload["verdict"] == "FAIL"
        assert payload["used_llm"] is False
    assert snapshot.read_bytes() == before


@pytest.mark.parametrize("extra_args", [[], ["--compare"]])
def test_conflicting_reassembly_contract_blocks_cli_before_provider_calls(
    tmp_path, monkeypatch, capsys, extra_args
):
    import hashlib

    context = tmp_path / "context.md"
    context.write_text("Pull request: [#7](https://x/pull/7)\n")
    snapshot = tmp_path / "verifier-input-manifest.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema": "workflows-verifier-input-snapshot/v1",
                "context_sha256": hashlib.sha256(context.read_bytes()).hexdigest(),
                "capture_reassembly_contract": {"schema": "unknown", "gaps": []},
            }
        )
    )
    before = snapshot.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("provider evaluation must not run")

    monkeypatch.setattr(pr_verifier, "evaluate_pr", forbidden)
    monkeypatch.setattr(pr_verifier, "evaluate_pr_multiple", forbidden)
    _argv(monkeypatch, tmp_path, context, *extra_args, "--json")
    pr_verifier.main()
    payload = json.loads(capsys.readouterr().out)
    result = payload["results"][0] if extra_args else payload
    assert result["verdict"] == "FAIL"
    assert result["used_llm"] is False
    assert snapshot.read_bytes() == before
    assert not (tmp_path / "verifier-capture-reassembly-contract.json").exists()
