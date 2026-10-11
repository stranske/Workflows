"""Capture obligation recording failures must yield structured FAIL without LLM calls."""

from __future__ import annotations

import json

import pytest
from scripts.langchain import pr_verifier


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
