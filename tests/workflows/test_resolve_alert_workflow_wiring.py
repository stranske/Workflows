"""Wiring contract for the shared failure-alert resolver (see
.github/scripts/resolve_alert_issue.py). Needs PyYAML, so it lives outside the
github_scripts suite, which runs without it."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _steps_calling_helper(job: dict) -> list[dict]:
    return [s for s in job.get("steps", []) if "resolve_alert_issue.py" in s.get("run", "")]


@pytest.mark.parametrize(
    ("workflow", "job", "label"),
    [
        ("maint-68-sync-consumer-repos.yml", "resolve-alert", "sync-failure"),
        ("health-71-sync-health-check.yml", "check-sync-health", "sync-failure"),
        ("health-67-integration-sync-check.yml", "check-sync", "integration-sync"),
        ("health-codex-auth-check.yml", None, "auth-expiring"),
    ],
)
def test_each_producer_closes_its_alert_on_a_gated_success_step(workflow, job, label):
    doc = _load(workflow)
    jobs = doc["jobs"]
    job_doc = jobs[job] if job else next(iter(jobs.values()))
    steps = _steps_calling_helper(job_doc)
    assert len(steps) == 1, f"{workflow} must call the shared helper exactly once"
    step = steps[0]
    assert step.get("continue-on-error") is True
    assert f"--label {label}" in step["run"]
    gate = str(step.get("if", "")) + str(job_doc.get("if", ""))
    assert any(tok in gate for tok in ("healthy", "== 'ok'", "success()", "'success'")), gate


def test_maint68_resolve_job_never_runs_for_failures_dry_runs_or_previews():
    job = _load("maint-68-sync-consumer-repos.yml")["jobs"]["resolve-alert"]
    cond = job["if"]
    for token in (
        "needs.prepare.result == 'success'",
        "needs.sync.result == 'success'",
        "needs.prepare.outputs.has_plan_items != 'true'",
        "needs.validate.result != 'failure'",
        "inputs.dry_run != true",
        "!= 'preview'",
        "!cancelled()",
    ):
        assert token in cond
    assert set(job["needs"]) == {"prepare", "validate", "sync"}


def test_maint68_refused_dispatch_input_reports_refusal_instead_of_alerting():
    jobs = _load("maint-68-sync-consumer-repos.yml")["jobs"]
    assert "input_refusal == ''" in jobs["notify-failure"]["if"]
    assert "input_refusal != ''" in jobs["report-refusal"]["if"]
    assert "input_refusal" in jobs["prepare"]["outputs"]
    # the refusal path must not call gh issue create/comment
    run_text = " ".join(s.get("run", "") for s in jobs["report-refusal"]["steps"])
    assert "gh issue" not in run_text


def test_maint68_refresh_guard_skip_is_not_recovery_and_refusals_are_allowlisted():
    text = (WORKFLOWS / "maint-68-sync-consumer-repos.yml").read_text(encoding="utf-8")
    cond = _load("maint-68-sync-consumer-repos.yml")["jobs"]["resolve-alert"]["if"]
    # a skipped sync only counts when there was no plan to deliver
    assert "needs.sync.result != 'failure'" not in cond
    assert "has_plan_items != 'true'" in cond
    # config/plan selector errors are not classified as refused dispatch input
    assert "unsupported_canary_config_schema" not in text.split("input_refusal=")[0][-900:]
    assert "canary_selection_contains_non_canary:*" in text
