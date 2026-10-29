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


def _step_inputs(workflow: dict):
    for job_name, job in (workflow.get("jobs") or {}).items():
        for index, step in enumerate(job.get("steps") or []):
            for key, value in (step.get("with") or {}).items():
                yield f"jobs.{job_name}.steps[{index}].with.{key}", str(value)


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda path: path.name)
def test_integration_template_steps_do_not_pass_every_secret(path: Path) -> None:
    # GitHub held every run of these files as "may be malicious" (action_required, zero jobs)
    # while a step handed toJSON(secrets) to an action checked out from another repository.
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    offenders = [
        where
        for where, value in _step_inputs(workflow)
        if "tojson(secrets)" in value.replace(" ", "").lower()
    ]
    assert not offenders, f"{path.name}: step passes the whole secrets context at {offenders}"


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda path: path.name)
def test_integration_template_passes_only_actions_bot_pat(path: Path) -> None:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    values = [
        value for where, value in _step_inputs(workflow) if where.endswith(".with.actions_bot_pat")
    ]
    assert values == [
        "${{ secrets.ACTIONS_BOT_PAT }}"
    ], f"{path.name}: actions_bot_pat inputs {values}"
