import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github/workflows/maint-70-fix-integration-formatting.yml"
)


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
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    steps = {step["name"]: step for step in workflow["jobs"]["fix-formatting"]["steps"]}
    integration = tmp_path / "integration-tests"
    integration.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").symlink_to(sys.executable)

    commands = {
        "black": "#!/bin/sh\nprintf '%s\\n' formatted > changed.py\nexit \"$BLACK_STATUS\"\n",
        "ruff": '#!/bin/sh\nprintf \'%s\\n\' "$RUFF_DIAGNOSTICS"\nexit "$RUFF_STATUS"\n',
    }
    for name, command in commands.items():
        executable = bin_dir / name
        executable.write_text(command, encoding="utf-8")
        executable.chmod(0o755)

    step = steps["Apply formatting fixes"]
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", step["run"]],
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
    assert result.returncode == expected, result.stdout + result.stderr
    if expected == 0 and ruff_status == 1:
        assert json.loads(diagnostics)[0]["code"] in result.stdout
        assert "remaining lint diagnostics" in result.stdout

    assert steps["Commit and push changes"]["if"] == "steps.changes.outputs.has_changes == 'true'"
    summary = steps["Summarize incomplete formatting"]
    assert summary["if"] == "failure() && steps.formatting.outcome == 'failure'"
    assert "No changes were pushed" in summary["run"]
