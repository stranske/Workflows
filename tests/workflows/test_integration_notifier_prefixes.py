"""Replay the deployed notifier's validation step without notifications."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

TEMPLATE = Path(__file__).resolve().parents[2] / "templates/integration-repo/.github/workflows"
REUSE = "stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main"

pytestmark = pytest.mark.skipif(
    not (shutil.which("yq") and shutil.which("jq")),
    reason="The notifier uses the runner's yq and jq",
)


@pytest.mark.parametrize(
    ("case", "missing"),
    [
        ("original", ""),
        ("unrelated-job", ""),
        ("missing", "basic"),
        ("bare-blank", "basic"),
        ("quoted-blank", "basic"),
        ("whitespace", "basic"),
        ("comment-only", "basic"),
        ("non-string", "basic"),
        ("none-configured", "basic, full-coverage, typecheck-only"),
        ("wrong-job", "basic"),
        ("single-reusable-job", ""),
        ("no-reusable-jobs", ""),
    ],
)
def test_notifier_validates_prefixes_only_on_relevant_jobs(tmp_path, case, missing):
    receiver = (
        TEMPLATE.joinpath("ci.yml").read_text(encoding="utf-8").replace("__WORKFLOW_REF__", REUSE)
    )
    prefix = "      artifact-prefix: basic-"
    changes = {
        "missing": "",
        "bare-blank": "      artifact-prefix:",
        "quoted-blank": '      artifact-prefix: ""',
        "whitespace": '      artifact-prefix: " \\t "',
        "comment-only": "      # artifact-prefix: basic-",
        "non-string": "      artifact-prefix: false",
        "wrong-job": "",
    }
    if case == "none-configured":
        receiver = re.sub(r"^      artifact-prefix: .*\n", "", receiver, flags=re.M)
    elif case in changes:
        replacement = changes[case]
        receiver = receiver.replace(prefix + "\n", replacement + "\n" if replacement else "")
    elif case == "single-reusable-job":
        receiver = f"jobs:\n  basic:\n    uses: {REUSE}\n"
    elif case == "no-reusable-jobs":
        receiver = "jobs:\n  local:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
    if case in {"unrelated-job", "wrong-job"}:
        receiver += (
            "\n  other-ci:\n"
            "    uses: stranske/Workflows/.github/workflows/reusable-11-ci-node.yml@main\n"
            "    with:\n"
            "      artifact-prefix: other-\n"
        )

    target = tmp_path / "integration-tests/.github/workflows/ci.yml"
    target.parent.mkdir(parents=True)
    target.write_text(receiver, encoding="utf-8")
    summary = tmp_path / "summary"
    notifier = yaml.safe_load((TEMPLATE / "notify-workflows.yml").read_text(encoding="utf-8"))
    steps = notifier["jobs"]["validate-against-template"]["steps"]
    step = next(step for step in steps if step["name"] == "Validate artifact-prefix on all jobs")
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_STEP_SUMMARY": str(summary)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.stderr == ""
    if missing:
        assert result.returncode == 1
        diagnostic = f"Missing or blank artifact-prefix: {missing}"
        assert diagnostic in result.stdout
        assert diagnostic in summary.read_text(encoding="utf-8")
    else:
        assert result.returncode == 0
        assert "Artifact prefixes configured correctly" in summary.read_text(encoding="utf-8")
