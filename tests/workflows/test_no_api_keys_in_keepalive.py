"""Account-only keepalive analysis: real wiring and mocked process boundary."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from tools import subscription_llm as cli
from tools.llm_provider import get_llm_provider

ROOT = Path(__file__).resolve().parents[2]
RUNNERS = ("codex", "claude", "cursor", "gemini", "muse")


@pytest.mark.parametrize("agent", RUNNERS)
def test_runner_analysis_has_no_api_key_or_second_invocation(agent):
    file = ROOT / f".github/workflows/reusable-{agent}-run.yml"
    jobs = yaml.safe_load(file.read_text())["jobs"]
    steps = [step for job in jobs.values() for step in job.get("steps", [])]
    analysis = next(s for s in steps if s.get("id") == "llm_analysis")
    for step in steps:
        for forbidden in ("OPENAI_API_KEY", "CLAUDE_API_STRANSKE"):
            assert forbidden not in json.dumps(step.get("env", {})), str(file)
            assert forbidden not in step.get("run", ""), str(file)
    assert analysis["env"]["WORKFLOWS_ANALYSIS_CLI"] == ("claude" if agent == "claude" else "codex")
    assert analysis["run"].count("python3 .workflows-lib/scripts/analyze_codex_session.py") == 1
    assert 'print(f"provider=' in analysis["run"]
    assert 'print(f"confidence=' in analysis["run"]


def test_progress_review_uses_subscription_without_langchain_install():
    file = ROOT / ".github/workflows/agents-keepalive-loop.yml"
    job = yaml.safe_load(file.read_text())["jobs"]["progress-review"]
    text = json.dumps(job)
    for forbidden in (
        "OPENAI_API_KEY",
        "CLAUDE_API_STRANSKE",
        "langchain-openai",
        "langchain-anthropic",
    ):
        assert forbidden not in text, str(file)
    step = next(s for s in job["steps"] if s.get("id") == "review")
    assert step["env"]["WORKFLOWS_ANALYSIS_CLI"] == "codex"
    assert "CODEX_AUTH_JSON" in text


@pytest.fixture
def account(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    monkeypatch.setenv(cli.MODE_ENV, "codex")
    auth = tmp_path / ".codex" / "auth.json"
    auth.parent.mkdir()
    auth.write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "fixture-only"}})
    )
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/fixture/bin/cli")
    return auth


def test_cli_final_message_only_and_no_api_or_job_secrets(monkeypatch, account):
    for key in (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "ANTHROPIC_API_KEY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "LANGSMITH_API_KEY",
    ):
        monkeypatch.setenv(key, "must-not-be-forwarded")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "other-provider-account")
    observed = []

    def run(command, **kw):
        observed.append((command, kw))
        return SimpleNamespace(
            returncode=0,
            stdout="\n".join(
                [
                    json.dumps(
                        {"type": "item.completed", "item": {"type": "reasoning", "text": "ignore"}}
                    ),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "agent_message",
                                "text": '{"completed":["Task"],"confidence":0.9}',
                            },
                        }
                    ),
                ]
            ),
        )

    monkeypatch.setattr(cli.subprocess, "run", run)
    provider = get_llm_provider()
    result = provider.analyze_completion("Implemented Task with validation", ["Task"])
    assert result.completed_tasks == ["Task"]
    assert result.provider_used == "codex"
    assert result.model_name == cli.analysis_model("codex")
    command, kw = observed[0]
    assert command[:2] == ["codex", "exec"]
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert 'forced_login_method="chatgpt"' in command
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in kw["env"]
    assert kw["timeout"] == 90
    assert not any(v == "must-not-be-forwarded" for v in kw["env"].values())
    assert "Task" in kw["input"]


@pytest.mark.parametrize(
    "failure", ["missing-auth", "api-auth", "exit", "timeout", "malformed", "empty"]
)
def test_failure_never_selects_api_fallback(monkeypatch, account, failure):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-use")
    if failure == "missing-auth":
        account.unlink()
    elif failure == "api-auth":
        account.write_text(
            json.dumps({"auth_mode": "apikey", "tokens": {"access_token": "fixture"}})
        )

    def run(command, **kw):
        assert command[0] == "codex"
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 90)
        return SimpleNamespace(
            returncode=1 if failure == "exit" else 0,
            stdout="invalid" if failure == "malformed" else "",
        )

    monkeypatch.setattr(cli.subprocess, "run", run)
    with pytest.raises((RuntimeError, ValueError, subprocess.TimeoutExpired)):
        get_llm_provider().analyze_completion("session", ["Task"])


def test_claude_uses_oauth_and_tool_free_json(monkeypatch, account):
    monkeypatch.setenv(cli.MODE_ENV, "claude")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fixture-subscription")
    calls = []

    def run(command, **kw):
        calls.append((command, kw))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "progress-json"}))

    monkeypatch.setattr(cli.subprocess, "run", run)
    info = cli.build_subscription_client()
    assert info.client.invoke("prompt").content == "progress-json"
    command, kw = calls[0]
    assert command[0:2] == ["claude", "-p"]
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--model") + 1] == cli.analysis_model("claude")
    assert kw["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "fixture-subscription"


def test_shared_progress_client_stays_on_cli_even_with_force_openai(monkeypatch, account):
    from scripts.langchain._llm_client import build_client

    info = build_client(force_openai=True)
    assert info.provider == "codex"
    assert info.model == cli.analysis_model("codex")


@pytest.mark.parametrize(
    "relative",
    [
        ".github/workflows/agents-keepalive-loop.yml",
        "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml",
    ],
)
def test_counter_is_forwarded_from_real_reconciliation_step(relative):
    steps = yaml.safe_load((ROOT / relative).read_text())["jobs"]["finish"]["steps"]
    reconcile = next(s for s in steps if s.get("id") == "reconcile")
    assert "result.llmTasksChecked" in reconcile["with"]["script"]
    summary = next(s for s in steps if s.get("id") == "update-summary")
    assert "steps.reconcile.outputs.llm_ticked_tasks" in summary["with"]["script"]
