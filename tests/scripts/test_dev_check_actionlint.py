from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_dev_check(
    tmp_path: Path,
    *,
    files: list[str],
    output: str,
    exit_code: int,
    actionlint_timeout: bool = False,
    kill_after_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    actionlint = tmp_path / "actionlint"
    actionlint.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                '[ -z "$FAKE_ACTIONLINT_OUTPUT" ] || printf "%s\\n" "$FAKE_ACTIONLINT_OUTPUT"',
                '[ "$FAKE_ACTIONLINT_WAIT" != true ] || sleep 5',
                '[ "$FAKE_ACTIONLINT_KILL" != true ] || kill -KILL "$$"',
                'exit "${FAKE_ACTIONLINT_EXIT:-0}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    actionlint.chmod(0o755)

    file_list = tmp_path / "files.txt"
    file_list.write_text("\n".join(files) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env.get('PATH', '')}"
    env["DEV_CHECK_ACTIONLINT_ONLY"] = "true"
    env["DEV_CHECK_ACTIONLINT_FILE_LIST"] = str(file_list)
    env["FAKE_ACTIONLINT_OUTPUT"] = output
    env["FAKE_ACTIONLINT_EXIT"] = str(exit_code)
    env["FAKE_ACTIONLINT_WAIT"] = str(actionlint_timeout).lower()
    env["FAKE_ACTIONLINT_KILL"] = str(kill_after_output).lower()
    env["DEV_CHECK_TIMEOUT"] = "1" if actionlint_timeout else "10"

    return subprocess.run(
        ["bash", "scripts/dev_check.sh"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def test_dev_check_reports_unexpected_step_secrets_in_template(tmp_path: Path) -> None:
    file_path = "templates/consumer-repo/.github/workflows/bad.yml"
    output = f'{file_path}:10:1: unexpected key "secrets" for "step"'

    result = _run_dev_check(
        tmp_path,
        files=[file_path],
        output=output,
        exit_code=1,
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert 'unexpected key "secrets" for "step"' in combined


def test_dev_check_reports_unexpected_secrets_even_when_actionlint_succeeds(
    tmp_path: Path,
) -> None:
    file_path = "templates/consumer-repo/.github/workflows/bad.yml"
    output = f'{file_path}:10:1: unexpected key "secrets" for "step"'

    result = _run_dev_check(
        tmp_path,
        files=[file_path],
        output=output,
        exit_code=0,
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert 'unexpected key "secrets" for "step"' in combined


def test_dev_check_passes_for_clean_actionlint_output(tmp_path: Path) -> None:
    result = _run_dev_check(
        tmp_path,
        files=[".github/workflows/health-42-actionlint.yml"],
        output="",
        exit_code=0,
    )

    assert result.returncode == 0
    assert "✓ Workflow YAML validation" in result.stdout


@pytest.mark.parametrize(("exit_code", "diagnostic"), [(7, "exit status 7"), (124, "timed out")])
def test_dev_check_reports_silent_actionlint_failure(
    tmp_path: Path, exit_code: int, diagnostic: str
) -> None:
    result = _run_dev_check(
        tmp_path,
        files=[".github/workflows/health-42-actionlint.yml"],
        output="",
        exit_code=exit_code,
    )

    assert result.returncode == 1
    assert diagnostic in result.stdout
    assert "✗ Workflow YAML validation" in result.stdout
    assert "✓ Workflow YAML validation" not in result.stdout


def test_dev_check_reports_both_diagnostics_and_context(tmp_path: Path) -> None:
    template = "templates/consumer-repo/.github/workflows/bad.yml"
    invalid = ".github/workflows/health-42-actionlint.yml"
    diagnostic = f"{invalid}:19:5: workflow is missing jobs"
    result = _run_dev_check(
        tmp_path,
        files=[template, invalid],
        output=f'{template}:20:2: unexpected key "secrets" for "step"\n  template snippet\n'
        f"{diagnostic}\n  invalid snippet",
        exit_code=1,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert diagnostic in combined
    assert "invalid snippet" in combined
    assert "template snippet" in combined
    assert 'unexpected key "secrets"' in combined


@pytest.mark.skipif(shutil.which("timeout") is None, reason="requires the command timeout")
def test_dev_check_reports_actual_actionlint_timeout_after_diagnostic(
    tmp_path: Path,
) -> None:
    file_path = "templates/consumer-repo/.github/workflows/bad.yml"
    result = _run_dev_check(
        tmp_path,
        files=[file_path],
        output=f'{file_path}:20:2: unexpected key "secrets" for "step"\n  template snippet',
        exit_code=0,
        actionlint_timeout=True,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "timed out after 1s" in combined
    assert "increase DEV_CHECK_TIMEOUT" in combined
    assert 'unexpected key "secrets"' in combined
    assert "template snippet" in combined


def test_dev_check_reports_killed_actionlint_after_diagnostic(tmp_path: Path) -> None:
    file_path = "templates/consumer-repo/.github/workflows/bad.yml"
    result = _run_dev_check(
        tmp_path,
        files=[file_path],
        output=f'{file_path}:20:2: unexpected key "secrets" for "step"\n  template snippet',
        exit_code=0,
        kill_after_output=True,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "actionlint exit status 137" in combined
    assert 'unexpected key "secrets"' in combined
    assert "template snippet" in combined
