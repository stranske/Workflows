"""Maint 83 verifies every registered consumer's bootstrap settings weekly (read-only).

2026-11-15: four lane repos had never had USE_CONSOLIDATED_WORKFLOWS set, so their PR event hub
had never run. Nothing reported it: Maint 83 ran only on hand dispatch and `--health-check`
reads priority labels, not settings.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/maint-83-bootstrap-consumer.yml")


def _load():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_weekly_schedule_runs_read_only_verify_and_dispatch_keeps_bootstrap():
    workflow = _load()
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["schedule"][0]["cron"]
    assert "workflow_dispatch" in triggers
    jobs = workflow["jobs"]
    assert jobs["bootstrap"]["if"] == "github.event_name == 'workflow_dispatch'"
    assert jobs["verify-fleet"]["if"] == "github.event_name == 'schedule'"
    script = jobs["verify-fleet"]["steps"][-1]["run"]
    assert "--verify" in script and "--execute" not in script
    assert "stranske/Template" in script


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_verify_step_reports_each_failing_consumer_and_fails_the_run(tmp_path):
    script = _load()["jobs"]["verify-fleet"]["steps"][-1]["run"]
    shims = tmp_path / "bin"
    shims.mkdir()
    # A stub `python`: three registered consumers, one of them missing a setting.
    (shims / "python").write_text(
        "#!/usr/bin/env bash\n"
        'case "$1" in\n'
        "  scripts/list_registered_consumer_repos.py)\n"
        "    printf 'stranske/Good\\nstranske/Template\\nstranske/Missing\\n' ;;\n"
        "  scripts/bootstrap_consumer_settings.py)\n"
        '    if [ "$3" = "stranske/Missing" ]; then\n'
        "      echo '[OK] workflow_permissions'; echo '[FAIL] var_use_consolidated_workflows'; exit 1\n"
        "    fi\n"
        "    echo '[OK] workflow_permissions'; exit 0 ;;\n"
        "esac\n"
    )
    (shims / "python").chmod(0o755)
    summary = tmp_path / "summary.md"
    env = {
        **os.environ,
        "PATH": f"{shims}:{os.environ['PATH']}",
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    text = summary.read_text()
    assert result.returncode == 1
    assert "| stranske/Missing | FAIL: var_use_consolidated_workflows |" in text
    assert "| stranske/Good | all OK |" in text
    assert "Template" not in text

    # The same three consumers, none missing anything: the run passes and reports no FAIL.
    (shims / "python").write_text(
        (shims / "python")
        .read_text()
        .replace('"$3" = "stranske/Missing"', '"$3" = "stranske/None"')
    )
    summary.write_text("")
    clean = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "FAIL" not in summary.read_text()
