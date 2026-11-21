"""Exercise the Health 42 shell step's exit status and diagnostic delivery."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC = '.github/workflows/input.yml:6:15: invalid action reference "$/.github/actions/setup-api-client"'


@pytest.mark.parametrize(
    ("event", "fork", "caller", "variable", "expected"),
    [
        ("pull_request", "true", "github-pr-review", "", "github-annotations"),
        ("pull_request", "true", "", "", "github-annotations"),
        ("pull_request", "true", "local", "github-pr-review", "local"),
        ("pull_request", "false", "github-pr-review", "", "github-pr-review"),
        ("schedule", "false", "github-check", "", "github-check"),
        ("workflow_dispatch", "false", "", "", "github-check"),
        ("workflow_dispatch", "false", "", "local", "local"),
    ],
)
def test_health_actionlint_selects_reporter(tmp_path, event, fork, caller, variable, expected):
    workflow = yaml.load(
        (ROOT / ".github/workflows/health-42-actionlint.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    step = next(
        item for item in workflow["jobs"]["lint"]["steps"] if item.get("id") == "set-reporter"
    )
    output = tmp_path / "outputs"

    subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        env={
            **os.environ,
            "GITHUB_OUTPUT": str(output),
            "EVENT_NAME": event,
            "FORK_PULL_REQUEST": fork,
            "REPORTER_FROM_CALL": caller,
            "REPORTER_FROM_VAR": variable,
        },
        check=True,
        timeout=10,
    )

    assert output.read_text() == f"reporter={expected}\n"


@pytest.mark.parametrize(
    ("lint_status", "reporter_status", "expected_status"),
    [(0, 0, 0), (0, 7, 7), (1, 0, 1), (1, 7, 1)],
    ids=["clean", "reporter-failure", "lint-failure", "both-fail"],
)
def test_health_actionlint_reports_failures(
    tmp_path, lint_status, reporter_status, expected_status
):
    workflow = yaml.load(
        (ROOT / ".github/workflows/health-42-actionlint.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    step = next(
        item for item in workflow["jobs"]["lint"]["steps"] if item.get("id") == "actionlint"
    )
    linter = tmp_path / "actionlint"
    linter.write_text(
        "#!/bin/sh\n"
        'if [ "$LINT_STATUS" -ne 0 ]; then\n'
        '  printf "%s\\n" "$DIAGNOSTIC"\n'
        "fi\n"
        'exit "$LINT_STATUS"\n'
    )
    linter.chmod(0o755)
    reporter = tmp_path / "reviewdog"
    reporter.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" > reporter-args.txt\n'
        "cat > report.txt\n"
        'exit "$REPORTER_STATUS"\n'
    )
    reporter.chmod(0o755)

    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "ALLOWLIST_FILE": "",
            "REPORTER": "github-pr-review",
            "LINT_STATUS": str(lint_status),
            "REPORTER_STATUS": str(reporter_status),
            "DIAGNOSTIC": DIAGNOSTIC,
        },
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert (tmp_path / "report.txt").read_text() == (f"{DIAGNOSTIC}\n" if lint_status else "")
    assert "-efm=%f:%l:%c: %m" in (tmp_path / "reporter-args.txt").read_text().splitlines()
    assert (DIAGNOSTIC in result.stdout) == bool(lint_status)
    assert result.returncode == expected_status
