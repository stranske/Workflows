from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_dev_check(
    tmp_path: Path,
    *,
    allowlist: list[str],
    files: list[str],
    output: str,
    exit_code: int,
) -> subprocess.CompletedProcess[str]:
    actionlint = tmp_path / "actionlint"
    actionlint.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                'printf "%s\\n" "$FAKE_ACTIONLINT_OUTPUT"',
                'exit "${FAKE_ACTIONLINT_EXIT:-0}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    actionlint.chmod(0o755)

    allowlist_file = tmp_path / "allowlist.txt"
    allowlist_file.write_text("\n".join(allowlist) + ("\n" if allowlist else ""), encoding="utf-8")

    file_list = tmp_path / "files.txt"
    file_list.write_text("\n".join(files) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env.get('PATH', '')}"
    env["DEV_CHECK_ACTIONLINT_ONLY"] = "true"
    env["DEV_CHECK_ACTIONLINT_FILE_LIST"] = str(file_list)
    env["DEV_CHECK_SECRETS_ALLOWLIST"] = str(allowlist_file)
    env["FAKE_ACTIONLINT_OUTPUT"] = output
    env["FAKE_ACTIONLINT_EXIT"] = str(exit_code)

    return subprocess.run(
        ["bash", "scripts/dev_check.sh"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_dev_check_reports_unexpected_secrets_key_outside_allowlist(tmp_path: Path) -> None:
    file_path = "templates/consumer-repo/.github/workflows/bad.yml"
    output = f'{file_path}:10:1: unexpected key "secrets" for "step"'

    result = _run_dev_check(
        tmp_path,
        allowlist=[],
        files=[file_path],
        output=output,
        exit_code=1,
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert 'unexpected key "secrets" for "step"' in combined


def test_dev_check_allows_allowlisted_secrets_key(tmp_path: Path) -> None:
    file_path = "templates/consumer-repo/.github/workflows/allowlisted.yml"
    output = f'{file_path}:20:2: unexpected key "secrets" for "step"'

    result = _run_dev_check(
        tmp_path,
        allowlist=[file_path],
        files=[file_path],
        output=output,
        exit_code=1,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert 'unexpected key "secrets" for "step"' not in combined


def test_dev_check_reports_unexpected_secrets_even_when_actionlint_succeeds(
    tmp_path: Path,
) -> None:
    file_path = "templates/consumer-repo/.github/workflows/bad.yml"
    output = f'{file_path}:10:1: unexpected key "secrets" for "step"'

    result = _run_dev_check(
        tmp_path,
        allowlist=[],
        files=[file_path],
        output=output,
        exit_code=0,
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert 'unexpected key "secrets" for "step"' in combined
