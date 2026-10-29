"""Integration template workflows must not read `secrets` in an `if:` condition.

GitHub rejects the whole workflow file when a job or step `if:` references the
secrets context, so every run fails at startup with zero jobs. Workflows-Integration-Tests
CI failed that way on every run from 2026-04-28 until this was fixed.
"""

from pathlib import Path

import pytest
import yaml

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates/integration-repo/.github/workflows"
TEMPLATES = sorted(TEMPLATE_DIR.glob("*.yml"))


def _conditions(workflow: dict):
    for job_name, job in (workflow.get("jobs") or {}).items():
        if "if" in job:
            yield f"jobs.{job_name}.if", str(job["if"])
        for index, step in enumerate(job.get("steps") or []):
            if "if" in step:
                yield f"jobs.{job_name}.steps[{index}].if", str(step["if"])


def test_integration_templates_exist() -> None:
    assert {path.name for path in TEMPLATES} >= {"ci.yml", "notify-workflows.yml"}


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda path: path.name)
def test_integration_template_conditions_do_not_read_secrets(path: Path) -> None:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    offenders = [where for where, condition in _conditions(workflow) if "secrets." in condition]
    assert not offenders, f"{path.name}: `if:` reads the secrets context at {offenders}"
