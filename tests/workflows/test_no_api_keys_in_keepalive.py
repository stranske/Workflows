"""Account-only keepalive analysis: real wiring and mocked process boundary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from tools import subscription_llm as cli
from tools.llm_provider import get_llm_provider

ROOT = Path(__file__).resolve().parents[2]
RUNNERS = ("codex", "claude", "cursor", "gemini", "muse")
PROVIDER_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_API_STRANSKE")


@pytest.mark.parametrize("agent", RUNNERS)
def test_runner_analysis_has_no_api_key_or_second_invocation(agent):
    file = ROOT / f".github/workflows/reusable-{agent}-run.yml"
    doc = yaml.safe_load(file.read_text())
    jobs = doc["jobs"]
    steps = [step for job in jobs.values() for step in job.get("steps", [])]
    analysis = next(s for s in steps if s.get("id") == "llm_analysis")
    for step in steps:
        lines = step.get("run", "").splitlines()
        if agent == "codex" and step is analysis:
            # Permit the exact presence-only receipt lines, never key values or wiring.
            for key in PROVIDER_KEYS[:2]:
                receipt = (
                    f"    print(f\"{key}-present={{str('{key}' in os.environ).lower()}}\", "
                    "file=sys.stderr)"
                )
                lines = [line for line in lines if line != receipt]
        for forbidden in (*PROVIDER_KEYS, "langchain"):
            assert forbidden not in json.dumps(step.get("env", {})), str(file)
            assert all(forbidden not in line for line in lines), str(file)
    # Analysis no longer accepts provider API secrets on the reusable workflow.
    triggers = doc.get("on", doc.get(True, {}))
    assert "workflow_call" in triggers, str(file)
    workflow_secrets = json.dumps(triggers["workflow_call"].get("secrets", {}))
    for key in PROVIDER_KEYS:
        assert key not in workflow_secrets, str(file)
    assert analysis["env"]["WORKFLOWS_ANALYSIS_CLI"] == ("claude" if agent == "claude" else "codex")
    assert analysis["run"].count("python3 .workflows-lib/scripts/analyze_codex_session.py") == 1
    assert 'print(f"provider=' in analysis["run"]
    assert 'print(f"confidence=' in analysis["run"]


@pytest.fixture(scope="module")
def codex_analysis_receipt_code():
    """Read the actual JSON-to-output code without editing the protected workflow."""
    doc = yaml.safe_load((ROOT / ".github/workflows/reusable-codex-run.yml").read_text())
    analysis = next(s for s in doc["jobs"]["codex"]["steps"] if s.get("id") == "llm_analysis")
    assert analysis["run"].count("<<'PY'\n") == 1
    code, delimiter, _ = analysis["run"].split("<<'PY'\n", 1)[1].partition("\nPY\n")
    assert delimiter, "analysis output extractor must have a closing heredoc delimiter"
    return code


@pytest.mark.parametrize("provider", ["codex", "regex-fallback"])
@pytest.mark.parametrize("openai_value", [None, "", "noncredential-presence-marker"])
@pytest.mark.parametrize("anthropic_value", [None, "", "noncredential-presence-marker"])
def test_analysis_receipt_reports_presence_without_values_and_preserves_json_outputs(
    codex_analysis_receipt_code, tmp_path, provider, openai_value, anthropic_value
):
    """Local receipt regression; fixture data does not establish hosted authentication."""
    data = {
        "provider": provider,
        "model": cli.analysis_model("codex") if provider == "codex" else "none",
        "confidence": 0.91,
        "completed_tasks": ["Preserve JSON outputs = verified", 'Handle "quoted" tasks'],
    }
    analysis_file = tmp_path / "analysis.json"
    analysis_file.write_text(json.dumps(data), encoding="utf-8")
    environment = {
        key: value
        for key, value in zip(PROVIDER_KEYS[:2], (openai_value, anthropic_value), strict=True)
        if value is not None
    }
    result = subprocess.run(
        [sys.executable, "-I", "-", str(analysis_file)],
        input=codex_analysis_receipt_code,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    outputs = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert outputs["provider"] == data["provider"]
    assert outputs["model"] == data["model"]
    assert float(outputs["confidence"]) == data["confidence"]
    assert json.loads(outputs["completed-tasks"]) == data["completed_tasks"]
    assert "subscription-auth" not in outputs  # Receipt belongs in logs, not step outputs.
    if provider == "codex":
        assert result.stderr.splitlines() == [
            "subscription-auth=chatgpt",
            f"OPENAI_API_KEY-present={str(openai_value is not None).lower()}",
            f"ANTHROPIC_API_KEY-present={str(anthropic_value is not None).lower()}",
            "completed-tasks-count=2",
        ]
    else:
        assert result.stderr == ""  # A fallback cannot claim subscription authentication.
    assert "noncredential-presence-marker" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("public_output", "step_output"),
    [
        ("llm-analysis-run", "llm-analysis-run"),
        ("llm-provider", "provider"),
        ("llm-model", "model"),
        ("llm-confidence", "confidence"),
        ("llm-completed-tasks", "completed-tasks"),
    ],
)
def test_codex_analysis_outputs_reach_reusable_workflow_callers(public_output, step_output):
    doc = yaml.safe_load((ROOT / ".github/workflows/reusable-codex-run.yml").read_text())
    assert doc["jobs"]["codex"]["outputs"][public_output] == (
        "${{ steps.llm_analysis.outputs." + step_output + " }}"
    )
    triggers = doc.get("on", doc.get(True, {}))
    assert triggers["workflow_call"]["outputs"][public_output]["value"] == (
        "${{ jobs.codex.outputs." + public_output + " }}"
    )


def test_progress_review_uses_subscription_without_langchain_install():
    file = ROOT / ".github/workflows/agents-keepalive-loop.yml"
    job = yaml.safe_load(file.read_text())["jobs"]["progress-review"]
    text = json.dumps(job)
    # The existing entrypoint's directory name is not a LangChain dependency.
    dependency_text = text.replace("scripts/langchain/progress_reviewer.py", "")
    for forbidden in (*PROVIDER_KEYS, "langchain"):
        assert forbidden not in dependency_text, str(file)
    step = next(s for s in job["steps"] if s.get("id") == "review")
    assert step["env"]["WORKFLOWS_ANALYSIS_CLI"] == "codex"
    assert "CODEX_AUTH_JSON" in text
    checkout = next(s for s in job["steps"] if s.get("name") == "Checkout")
    assert checkout["with"]["persist-credentials"] is False
    prepare = next(s for s in job["steps"] if s.get("name") == "Prepare subscription analysis CLI")
    assert "npm ci --prefix .github/actions/maint78-codex-cli --ignore-scripts" in prepare["run"]
    assert "npm install" not in prepare["run"]
    assert "GITHUB_PATH" not in prepare["run"]
    assert (
        'export PATH="$PWD/.github/actions/maint78-codex-cli/node_modules/.bin:$PATH"'
        in step["run"]
    )
    lock = json.loads((ROOT / ".github/actions/maint78-codex-cli/package-lock.json").read_text())
    assert lock["packages"]["node_modules/@openai/codex"]["version"] == "0.160.0"
    assert lock["packages"]["node_modules/@openai/codex"]["integrity"]


@pytest.mark.parametrize("agent", (*RUNNERS, "progress-review"))
@pytest.mark.parametrize("surface", ("env", "run"))
@pytest.mark.parametrize("forbidden", (*PROVIDER_KEYS, "langchain"))
def test_workflow_gate_rejects_reintroduced_api_dependencies(
    monkeypatch, agent, surface, forbidden
):
    """Exercise the real gate against mutations without editing protected workflows."""
    filename = (
        "agents-keepalive-loop.yml" if agent == "progress-review" else f"reusable-{agent}-run.yml"
    )
    doc = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text())
    if agent == "progress-review":
        steps = doc["jobs"]["progress-review"]["steps"]
        step_id = "review"
    else:
        steps = [step for job in doc["jobs"].values() for step in job.get("steps", [])]
        step_id = "llm_analysis"
    step = next(step for step in steps if step.get("id") == step_id)
    if surface == "env":
        step.setdefault("env", {})[forbidden] = "fixture-only"
    else:
        step["run"] += f"\n{forbidden}=fixture-only\n"
    monkeypatch.setattr(yaml, "safe_load", lambda _: doc)

    with pytest.raises(AssertionError) as failure:
        if agent == "progress-review":
            test_progress_review_uses_subscription_without_langchain_install()
        else:
            test_runner_analysis_has_no_api_key_or_second_invocation(agent)
    assert filename in str(failure.value)


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
    assert "--ignore-user-config" in command
    assert "--ephemeral" in command
    assert 'forced_login_method="chatgpt"' in command
    assert 'web_search="disabled"' in command
    assert [command[i + 1] for i, part in enumerate(command) if part == "--disable"] == [
        "shell_tool",
        "view_image",
        "image_generation",
        "multi_agent",
        "multi_agent_v2",
        "plugins",
        "hooks",
        "code_mode_host",
        "browser_use",
        "in_app_browser",
        "apps",
        "computer_use",
        "skill_search",
    ]
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in kw["env"]
    assert kw["timeout"] == 90
    assert kw["cwd"]  # empty temp workspace, not the job checkout
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


def test_shared_progress_client_uses_callable_cli_adapter(monkeypatch, account):
    from scripts.langchain._llm_client import build_auxiliary_client

    info = build_auxiliary_client()
    assert callable(info.client)
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
    assert summary["env"]["LLM_TICKED_TASKS"] == "${{ steps.reconcile.outputs.llm_ticked_tasks }}"
    assert "Number(process.env.LLM_TICKED_TASKS)" in summary["with"]["script"]
    assert "${{ steps.reconcile.outputs.llm_ticked_tasks }}" not in summary["with"]["script"]
