"""Prove the receipt regressions never call a provider or hosted verification.

The authored evaluate shell is executed here with no provider credentials, no
hosted-runner tokens, and a PATH limited to an inert evaluator plus cat, grep,
and cut. python3 may run only the inline receipt scripts. A command log records
every interpreter invocation.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

from tests.workflows.test_verifier_evaluation_transport import _bash, _local_command_path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-agents-verifier.yml"
PRE_CORRECTION_SHELL = (
    ROOT / "tests/fixtures/verifier_evaluation_transport/pre_correction_llm_evaluate.sh"
)
HARNESSES = (
    ROOT / "tests/workflows/test_verifier_evaluation_transport.py",
    ROOT / "tests/workflows/test_verifier_evaluation_pre_correction.py",
)
PROVIDER_ENV = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_STRANSKE",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "LANGSMITH_API_KEY",
    "LANGCHAIN_API_KEY",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
)
HOSTED_CALLS = (
    "gh workflow run",
    "gh api",
    "workflow_dispatch",
    "openai.OpenAI",
    "anthropic.Anthropic",
    "urllib.request",
    "httpx.",
    "requests.",
)
SHELL_COMMANDS = ("\ngh ", "\ncurl ", "\nwget ", "\ncodex ", "\npip ", "\nnpx ", "workflow run")
VALUES = {
    "inputs.model": "claude-sonnet-5-5",
    "inputs.provider": "anthropic",
    "inputs.mode": "evaluate",
    "steps.agent.outputs.agent_label || ''": "agent:codex",
    "steps.agent.outputs.from_label || ''": "from:codex",
    "steps.context.outputs.context_path": "verifier-context.md",
    "steps.context.outputs.diff_path": "verifier-pr-diff.patch",
    "steps.context.outputs.chain_depth": "0",
    "steps.context.outputs.chain_depth || '0'": "0",
    "steps.context.outputs.target_sha": "b" * 40,
    "steps.context.outputs.pr_number": "4175",
    "inputs.ci_workflows": '["ci.yml"]',
    "inputs.evidence_profile": "expanded",
}


def _render(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in VALUES:
            raise AssertionError(f"unexpected workflow expression: {key}")
        return VALUES[key]

    return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", replace, text)


def _steps() -> list[dict]:
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    return workflow["jobs"]["verifier"]["steps"]


def _install_closed_tools(
    bin_path: Path, log_path: Path, stdout: Path, stderr: Path, exit_code: int
) -> str:
    bin_path.mkdir()
    python = bin_path / "python"
    python.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "import os, sys",
                "from pathlib import Path",
                f"log = Path({str(log_path)!r})",
                f"present = sorted(name for name in {PROVIDER_ENV!r} if os.environ.get(name))",
                "with log.open('a', encoding='utf-8') as handle:",
                "    handle.write('python\\t' + '\\t'.join(sys.argv[1:]) + '\\n')",
                "    handle.write('credentials\\t' + ','.join(present) + '\\n')",
                "if not any(arg.endswith('pr_verifier.py') for arg in sys.argv[1:]):",
                "    sys.stderr.write('inert evaluator expected pr_verifier.py\\n')",
                "    sys.exit(97)",
                f"sys.stdout.buffer.write(Path({str(stdout)!r}).read_bytes())",
                f"sys.stderr.buffer.write(Path({str(stderr)!r}).read_bytes())",
                f"raise SystemExit({int(exit_code)})",
                "",
            ]
        )
    )
    python.chmod(0o755)
    python3 = bin_path / "python3"
    python3.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "import os, sys",
                "from pathlib import Path",
                f"log = Path({str(log_path)!r})",
                "with log.open('a', encoding='utf-8') as handle:",
                "    handle.write('python3\\t' + '\\t'.join(sys.argv[1:]) + '\\n')",
                "if sys.argv[1:] != ['-']:",
                "    sys.stderr.write('refusing non-stdin python3: %s\\n' % sys.argv[1:])",
                "    sys.exit(98)",
                f"os.execv({sys.executable!r}, [{sys.executable!r}, '-'])",
                "",
            ]
        )
    )
    python3.chmod(0o755)
    return _local_command_path(bin_path)


def _run_authored(
    tmp_path: Path, *, raw: str, exit_code: int
) -> tuple[subprocess.CompletedProcess[str], Path]:
    steps = _steps()
    identity = next(
        step
        for step in steps
        if step.get("name") == "Record verifier input identity for model evaluation"
    )
    evaluate = next(step for step in steps if step.get("id") == "llm_evaluate")
    (tmp_path / ".workflows-lib").symlink_to(ROOT, target_is_directory=True)
    (tmp_path / "verifier-context.md").write_text(
        "# PR 4175\nOriginal request.\n", encoding="utf-8"
    )
    (tmp_path / "verifier-pr-diff.patch").write_text("+exact changed code\n", encoding="utf-8")
    (tmp_path / "verifier-diff-summary.md").write_text("source.py | 1 +\n", encoding="utf-8")
    stdout = tmp_path / "provider-stdout"
    stderr = tmp_path / "provider-stderr"
    stdout.write_text(raw, encoding="utf-8")
    stderr.write_text("inert evaluator diagnostic\n", encoding="utf-8")
    log_path = tmp_path / "command-log.txt"
    bin_path = tmp_path / "bin"
    path = _install_closed_tools(bin_path, log_path, stdout, stderr, exit_code)
    assert os.path.dirname(_bash()) not in path.split(os.pathsep)
    env = {
        "PATH": path,
        "PYTHONPATH": ".workflows-lib",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "1234",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "VERIFIER_EVIDENCE_PROFILE": "expanded",
        "HOME": str(tmp_path),
    }
    assert not any(name in env for name in PROVIDER_ENV)
    identity_env = {**env, **{key: _render(value) for key, value in identity["env"].items()}}
    identity_result = subprocess.run(
        [_bash(), "-c", identity["run"]],
        cwd=tmp_path,
        env=identity_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert identity_result.returncode == 0, identity_result.stderr
    result = subprocess.run(
        [_bash(), "-c", _render(evaluate["run"])],
        cwd=tmp_path,
        env={
            **env,
            **{
                key: _render(value)
                for key, value in evaluate["env"].items()
                if key not in PROVIDER_ENV
            },
        },
        text=True,
        capture_output=True,
        check=False,
    )
    return result, log_path


def _command_rows(log_path: Path) -> list[list[str]]:
    return [line.split("\t") for line in log_path.read_text(encoding="utf-8").splitlines()]


def test_receipt_harnesses_have_no_provider_or_hosted_dispatch() -> None:
    evaluate = next(step for step in _steps() if step.get("id") == "llm_evaluate")["run"]
    frozen = PRE_CORRECTION_SHELL.read_text(encoding="utf-8")
    for script in (evaluate, frozen):
        for command in SHELL_COMMANDS:
            assert command not in script, command

    for harness in HARNESSES:
        text = harness.read_text(encoding="utf-8")
        assert "os.defpath" not in text, harness
        for call in HOSTED_CALLS:
            assert call not in text, f"{harness} contains {call}"
    transport, pre_correction = (path.read_text(encoding="utf-8") for path in HARNESSES)
    assert "refusing non-stdin python3" in pre_correction
    assert "os.execv" not in pre_correction
    refusal = transport.index("refusing provider entrypoint")
    forward = transport.index("os.execv(sys.executable, [sys.executable, *sys.argv[1:]])")
    guarded = transport[transport.index("if sys.argv[1:] != ['-']") : forward]
    assert "pr_verifier.py" in guarded and refusal < forward


def test_authored_shell_logs_only_the_inert_evaluator(tmp_path: Path) -> None:
    raw = json.dumps(
        {
            "verdict": "PASS",
            "used_llm": True,
            "provider_used": "anthropic/claude-sonnet-5-5",
            "model": "claude-sonnet-5-5",
            "summary": "Exact source reviewed.",
        }
    )
    result, log_path = _run_authored(tmp_path, raw=raw, exit_code=0)
    assert result.returncode == 0, result.stderr
    rows = _command_rows(log_path)
    assert {row[0] for row in rows} <= {"python", "python3", "credentials"}
    evaluators = [row for row in rows if row[0] == "python"]
    assert len(evaluators) == 1
    assert evaluators[0][1].endswith("pr_verifier.py")
    assert "--provider" in evaluators[0] and "anthropic" in evaluators[0]
    assert all(row == ["python3", "-"] for row in rows if row[0] == "python3")
    assert [row for row in rows if row[0] == "credentials"] == [["credentials", ""]]
    receipt = json.loads((tmp_path / "evaluation-execution.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "completed"
    assert receipt["provider_requested"] == "anthropic"


def test_failed_authored_shell_stays_inert_without_credentials(tmp_path: Path) -> None:
    result, log_path = _run_authored(tmp_path, raw="", exit_code=2)
    assert result.returncode == 0, result.stderr
    rows = _command_rows(log_path)
    evaluators = [row for row in rows if row[0] == "python"]
    assert len(evaluators) == 1 and evaluators[0][1].endswith("pr_verifier.py")
    assert all(row == ["python3", "-"] for row in rows if row[0] == "python3")
    assert [row for row in rows if row[0] == "credentials"] == [["credentials", ""]]
    receipt = json.loads((tmp_path / "evaluation-execution.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "process_failed"
    assert receipt["verdict"] == "UNVERIFIABLE_INPUT"
    assert receipt["model_execution"] == receipt["remote_effects"] == "unconfirmed"
    outputs = (tmp_path / "outputs").read_text(encoding="utf-8")
    assert "verdict=UNVERIFIABLE_INPUT" in outputs


def test_comment_publication_cannot_reach_a_hosted_workflow(tmp_path: Path) -> None:
    step = next(step for step in _steps() if step.get("name") == "Post LLM evaluation comment")
    assert "gh pr comment" in step["run"]
    assert "gh workflow" not in step["run"]
    assert "workflow run" not in step["run"]
    assert "workflow_dispatch" not in step["run"]
    for command in ("curl ", "codex ", "pip ", "wget "):
        assert command not in step["run"]
    (tmp_path / "evaluation-comment.md").write_text(
        "**Verdict:** UNVERIFIABLE_INPUT\n", encoding="utf-8"
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    invocations = tmp_path / "gh-invocations"
    (binary / "gh").write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> " + shlex.quote(str(invocations)) + "\nexit 42\n",
        encoding="utf-8",
    )
    (binary / "gh").chmod(0o755)
    result = subprocess.run(
        [_bash(), "-c", step["run"].replace("${{ steps.context.outputs.pr_number }}", "4175")],
        cwd=tmp_path,
        env={"PATH": str(binary), "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    invoked = invocations.read_text(encoding="utf-8")
    assert invoked.strip() == "pr comment 4175 --body-file evaluation-comment.md"
    assert "workflow" not in invoked
