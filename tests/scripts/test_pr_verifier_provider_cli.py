"""Advertised native providers reach existing client selection before any paid call."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.langchain import pr_verifier


@pytest.mark.parametrize(
    "provider,canonical",
    [
        ("openai", "openai"),
        ("github-models", "github-models"),
        ("anthropic", "anthropic"),
        ("claude", "anthropic"),
        ("github", "github-models"),
        ("github_models", "github-models"),
        (" OPENAI ", "openai"),
        (" CLAUDE ", "anthropic"),
        (" GitHub_Models ", "github-models"),
    ],
)
def test_evaluate_cli_passes_supported_provider_to_existing_client_selection(
    monkeypatch, capsys, provider, canonical
):
    calls = []

    def unavailable_client(*, model, provider):
        calls.append((model, provider))
        return None

    monkeypatch.setattr(pr_verifier, "_get_llm_client", unavailable_client)
    monkeypatch.setattr(
        pr_verifier, "_load_text", lambda _: "## PR #4175\nOriginal acceptance criteria retained."
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["pr_verifier.py", "--json", "--provider", provider, "--model", "claude-sonnet-5-5"],
    )
    pr_verifier.main()
    result = json.loads(capsys.readouterr().out)
    assert calls == [("claude-sonnet-5-5", canonical)]
    assert result["used_llm"] is False and result["verdict"] != "PASS"


@pytest.mark.parametrize("provider", ["invented-provider", "", "   ", "auto"])
def test_evaluate_cli_rejects_unknown_provider_before_client_selection(
    monkeypatch, capsys, provider
):
    monkeypatch.setattr(
        pr_verifier, "_get_llm_client", lambda **_kw: pytest.fail("invalid provider reached client")
    )
    monkeypatch.setattr(sys, "argv", ["pr_verifier.py", "--provider", provider, "--json"])
    with pytest.raises(SystemExit) as error:
        pr_verifier.main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert not captured.out and "unsupported LLM provider" in captured.err


def test_authored_evaluate_cli_arguments_reach_native_evaluation_without_paid_calls(
    tmp_path, monkeypatch, capsys
):
    context = tmp_path / "verifier-context.md"
    diff = tmp_path / "verifier-pr-diff.patch"
    context.write_text("## PR #4175\nOriginal request and acceptance criteria.\n")
    diff.write_text("diff --git a/source.py b/source.py\n+exact changed code\n")
    selections = []
    issue_attempts = []

    def unavailable_client(*, model, provider):
        selections.append((model, provider))
        return None

    def inert_issue(result, loaded_context, **kwargs):
        issue_attempts.append((result.used_llm, loaded_context, kwargs["labels"]))
        return None

    monkeypatch.setattr(pr_verifier, "_get_llm_client", unavailable_client)
    monkeypatch.setattr(pr_verifier, "_create_followup_issue", inert_issue)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pr_verifier.py",
            "--context-file",
            str(context),
            "--diff-file",
            str(diff),
            "--json",
            "--model",
            "claude-sonnet-5-5",
            "--provider",
            "anthropic",
            "--create-issue",
            "--issue-label",
            "verify:evaluate",
        ],
    )
    pr_verifier.main()
    result = json.loads(capsys.readouterr().out)
    assert selections == [("claude-sonnet-5-5", "anthropic")]
    assert result["used_llm"] is False and result["verdict"] != "PASS"
    assert issue_attempts == [(False, context.read_text(), ["verify:evaluate"])]


@pytest.mark.parametrize(
    "provider,canonical",
    [("anthropic", "anthropic"), ("claude", "anthropic"), (" GitHub_Models ", "github-models")],
)
def test_authored_command_subprocess_imports_and_routes_provider_offline(
    tmp_path, provider, canonical
):
    root = Path(__file__).resolve().parents[2]
    (tmp_path / ".workflows-lib").symlink_to(root, target_is_directory=True)
    (tmp_path / "verifier-context.md").write_text("## PR #4175\nOriginal request.\n")
    (tmp_path / "verifier-pr-diff.patch").write_text("+exact changed code\n")
    # Execute the actual script as __main__; only external client/network effects
    # are replaced. This proves local import/argv routing, not the missing CI stderr.
    bootstrap = r"""
import json, pathlib, runpy, socket, sys
from scripts.langchain import _llm_client
from scripts import api_client
calls = {"client_selection": [], "network": [], "issue": []}
def unavailable_client(*, model, provider, **kwargs):
    calls["client_selection"].append([model, provider])
    return None
def forbidden_network(*args, **kwargs):
    calls["network"].append("forbidden")
    raise AssertionError("offline test attempted network")
def forbidden_issue(*args, **kwargs):
    calls["issue"].append("forbidden")
    raise AssertionError("offline test attempted issue creation")
_llm_client.get_llm_client = unavailable_client
socket.create_connection = forbidden_network
socket.getaddrinfo = forbidden_network
socket.socket.connect = forbidden_network
api_client.create_issue = forbidden_issue
sys.argv = sys.argv[1:]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
finally:
    pathlib.Path("offline-boundary.json").write_text(json.dumps(calls))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            bootstrap,
            ".workflows-lib/scripts/langchain/pr_verifier.py",
            "--context-file",
            "verifier-context.md",
            "--diff-file",
            "verifier-pr-diff.patch",
            "--json",
            "--model",
            "claude-sonnet-5-5",
            "--provider",
            provider,
            "--create-issue",
            "--issue-label",
            "verify:evaluate",
        ],
        cwd=tmp_path,
        env={"PATH": os.defpath, "PYTHONPATH": ".workflows-lib", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["used_llm"] is False and payload["verdict"] != "PASS"
    assert json.loads((tmp_path / "offline-boundary.json").read_text()) == {
        "client_selection": [["claude-sonnet-5-5", canonical]],
        "network": [],
        "issue": [],
    }


@pytest.mark.parametrize("provider", [None, "", "   ", "invented-provider", "auto"])
def test_provider_argument_never_converts_invalid_explicit_input_into_autofallback(provider):
    with pytest.raises(argparse.ArgumentTypeError, match="unsupported LLM provider"):
        pr_verifier._provider_argument(provider)
