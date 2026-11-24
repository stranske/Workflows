"""Maint 77 must preserve the durable lifecycle of its evidence issue."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/maint-77-model-registry-freshness.yml")


def test_model_registry_evidence_issue_is_labeled_durable_on_create_and_refresh() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert source.count('--add-label "automated"') == 1
    assert source.count('--add-label "tracker:durable"') == 1
    assert source.count('--label "automated,tracker:durable"') == 1


@pytest.mark.parametrize(
    ("freshness_rc", "advisory", "discovery_rc", "expected_rc", "expected_message", "writes"),
    [
        (0, False, 0, 0, "findings cleared", False),
        (0, True, 0, 0, "findings persist", True),
        (1, False, 0, 0, "findings persist", True),
        (0, False, 1, 0, "findings persist", True),
        (2, False, 0, 2, "configuration error", False),
        (0, False, 2, 2, "configuration error", False),
    ],
    ids=["clear", "advisory", "structural", "catalog-drift", "freshness-error", "catalog-error"],
)
def test_tracking_issue_uses_rechecked_findings(
    tmp_path: Path,
    freshness_rc: int,
    advisory: bool,
    discovery_rc: int,
    expected_rc: int,
    expected_message: str,
    writes: bool,
) -> None:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["tracking-issue"]["steps"]
    reports = next(step for step in steps if step.get("id") == "reports")
    writer = next(step for step in steps if step["name"].startswith("Open or refresh"))
    fixture = tmp_path / "python3"
    fixture.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  tools/check_model_registry_freshness.py) printf "%s\\n" "$FRESHNESS_JSON"; exit "$FRESHNESS_RC" ;;\n'
        '  tools/discover_model_catalog.py) printf "%s\\n" "$DISCOVERY_JSON" > "$3"; exit "$DISCOVERY_RC" ;;\n'
        '  *) exec "$TEST_PYTHON" "$@" ;;\n'
        "esac\n"
    )
    fixture.chmod(0o755)
    gh = tmp_path / "gh"
    gh.write_text(
        '#!/bin/sh\nprintf "%s %s\\n" "$1" "$2" >> "$GH_LOG"\n'
        'if [ "$2" = list ]; then printf "2905\\n"; fi\n'
    )
    gh.chmod(0o755)
    gh_log = tmp_path / "gh.log"
    outputs = tmp_path / "output"
    summary = tmp_path / "summary"
    outputs.touch()
    env = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "TEST_PYTHON": sys.executable,
        "GITHUB_OUTPUT": str(outputs),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GH_LOG": str(gh_log),
        "FRESHNESS_JSON": json.dumps({"advisory": ["review overdue"] if advisory else []}),
        "FRESHNESS_RC": str(freshness_rc),
        "DISCOVERY_JSON": json.dumps({"drift": discovery_rc == 1}),
        "DISCOVERY_RC": str(discovery_rc),
    }
    result = subprocess.run(
        ["bash", "-e", "-c", reports["run"]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    decision = dict(line.split("=", 1) for line in outputs.read_text().splitlines())
    condition = writer.get("if")
    if condition is not None:
        assert condition == "steps.reports.outputs.has_findings == 'true'"
    if result.returncode == 0 and (condition is None or decision.get("has_findings") == "true"):
        shell = (
            writer["run"]
            .replace("${{ github.server_url }}", "https://github.com")
            .replace("${{ github.repository }}", "stranske/Workflows")
            .replace("${{ github.run_id }}", "37269067774")
        )
        subprocess.run(["bash", "-e", "-c", shell], cwd=tmp_path, env=env, check=True)
    calls = gh_log.read_text().splitlines() if gh_log.exists() else []
    assert result.returncode == expected_rc
    assert calls == (["issue list", "issue edit", "issue comment"] if writes else [])
    assert expected_message in result.stdout
    if expected_rc == 0:
        assert expected_message in summary.read_text()
