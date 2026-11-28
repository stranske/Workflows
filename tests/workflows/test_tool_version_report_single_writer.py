"""The PyPI freshness report runs once, inside the job that acts on it.

Until 2026-11-28 Maint 50 ran the same pin-against-PyPI comparison five hours after
maint-auto-update-pypi-versions.yml, as a separate read-only workflow (cohesion review
item B8). These tests pin the fold: one workflow runs the comparison, the step runs on
every run, and the real step writes one row per pinned tool without leaving files in the
checkout that the source PR could pick up.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml
from scripts import maint_tool_version_check as check

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
PROPOSER = WORKFLOWS / "maint-auto-update-pypi-versions.yml"


def _steps() -> list[dict]:
    data = yaml.safe_load(PROPOSER.read_text(encoding="utf-8"))
    return data["jobs"]["check-and-update"]["steps"]


def _report_step() -> dict:
    matches = [step for step in _steps() if step.get("name") == "Tool version report"]
    assert len(matches) == 1
    return matches[0]


def test_exactly_one_workflow_runs_the_freshness_comparison() -> None:
    users = sorted(
        path.name
        for path in WORKFLOWS.glob("*.y*ml")
        if "maint_tool_version_check.py" in path.read_text(encoding="utf-8")
    )
    assert users == [PROPOSER.name]
    assert not (WORKFLOWS / "maint-50-tool-version-check.yml").exists()


def test_report_step_runs_on_every_run_before_any_gated_step() -> None:
    steps = _steps()
    report = _report_step()
    assert "if" not in report
    first_gated = next(index for index, step in enumerate(steps) if "if" in step)
    assert steps.index(report) < first_gated


def test_report_step_writes_one_row_per_pinned_tool(tmp_path: Path) -> None:
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    summary = tmp_path / "summary.md"
    output = tmp_path / "output.txt"
    env = dict(os.environ)
    env.update(
        {
            "GITHUB_WORKSPACE": str(ROOT),
            "RUNNER_TEMP": str(runner_temp),
            "GITHUB_STEP_SUMMARY": str(summary),
            "GITHUB_OUTPUT": str(output),
            "WORKFLOW_URL": "https://example.test/workflow",
        }
    )
    # Latest = current pin for every tool, so the step never reaches PyPI.
    for spec in check.TOOLS:
        env[spec.latest_env] = check.CURRENT_BY_PACKAGE[spec.name]
    before = set(ROOT.glob("tool-version-*.md"))

    subprocess.run(["bash", "-c", _report_step()["run"]], env=env, check=True, cwd=ROOT)

    text = summary.read_text(encoding="utf-8")
    assert "## Tool Version Status" in text
    rows = [line for line in text.splitlines() if line.startswith("| ") and "---" not in line]
    tools = {row.split("|")[1].strip() for row in rows[1:]}
    assert tools == set(check.PINNED_TOOLS.values())
    assert all(row.rstrip().endswith("| Current |") for row in rows[1:])
    assert set(ROOT.glob("tool-version-*.md")) == before
    assert (runner_temp / "tool-version-report.md").exists()
