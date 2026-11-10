"""Capture obligation recording failures must yield structured FAIL without LLM calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.langchain import pr_verifier


@pytest.mark.parametrize("failure_kind", ["provenance", "extraction_byte", "character"])
def test_4509_capture_gaps_withhold_review_of_both_changed_files(failure_kind):
    """Replay the original failure classes against the exact merged two-file diff.

    This is an admission regression, not the original input bundle or a provider
    assessment. Complete changed code cannot cure unavailable required proof.
    """
    root = Path(__file__).resolve().parents[2]
    patch = (root / ".github/scripts/__tests__/fixtures/verifier-4509-merge.patch").read_text()
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
