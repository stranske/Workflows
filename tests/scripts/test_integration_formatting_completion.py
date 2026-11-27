import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FORMATTER = Path(__file__).resolve().parents[2] / "scripts/fix-integration-tests-formatting.sh"


@pytest.mark.parametrize(
    ("black_status", "ruff_status", "diagnostics", "expected"),
    [
        pytest.param(0, 0, "[]", 0, id="clean"),
        pytest.param(0, 1, '[{"code": "F821"}]', 0, id="ordinary-lint"),
        pytest.param(123, 1, '[{"code": "F821"}]', 123, id="black-failure"),
        pytest.param(0, 2, "", 2, id="ruff-config-failure"),
        pytest.param(0, 1, '[{"code": "invalid-syntax"}]', 1, id="ruff-syntax-failure"),
        pytest.param(0, 1, '[{"code": "E902"}]', 1, id="ruff-file-io-failure"),
        pytest.param(0, 1, "[]", 1, id="missing-diagnostics"),
        pytest.param(0, 1, "not json", 1, id="broken-diagnostics"),
    ],
)
def test_formatting_requires_working_tools(
    tmp_path, black_status, ruff_status, diagnostics, expected
):
    integration = tmp_path / "integration-tests"
    subprocess.run(["git", "init", "-q", str(integration)], check=True)
    for relative_path in (
        ".github/workflows/notify-workflows.yml",
        "pyproject.toml",
        "scripts/validate_dependency_test_setup.py",
        "tests/test_dependency_version_alignment.py",
    ):
        path = integration / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").symlink_to(sys.executable)

    commands = {
        "black": r"""#!/bin/sh
printf '%s\n' "$@" > black-arguments.txt
printf '%s\n' formatted > changed.py
exit "$BLACK_STATUS"
""",
        "ruff": r"""#!/bin/sh
touch ruff-ran
printf '%s\n' "$RUFF_DIAGNOSTICS"
exit "$RUFF_STATUS"
""",
    }
    for name, command in commands.items():
        executable = bin_dir / name
        executable.write_text(command, encoding="utf-8")
        executable.chmod(0o755)

    result = subprocess.run(
        ["bash", str(FORMATTER), "--reviewed", str(integration)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "BLACK_STATUS": str(black_status),
            "RUFF_STATUS": str(ruff_status),
            "RUFF_DIAGNOSTICS": diagnostics,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert (integration / "changed.py").is_file()
    assert (integration / "black-arguments.txt").read_text().splitlines() == [
        "--extend-exclude",
        r"\.workflows-lib",
        ".",
    ]
    assert result.returncode == expected, result.stdout + result.stderr
    assert (integration / "ruff-ran").is_file() == (black_status == 0)
    assert ("Review the changes before committing" in result.stdout) == (expected == 0)
    if expected == 0 and ruff_status == 1:
        assert json.loads(diagnostics)[0]["code"] in result.stdout
        assert "remaining lint diagnostics" in result.stdout
