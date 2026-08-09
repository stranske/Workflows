"""Contract tests for the core-label sync workflow.

maint-69 writes labels into OTHER repositories. Two defects made it report success
while syncing nothing (see issue #3007):

* it passed the default ``GITHUB_TOKEN``, which is scoped to this repository and
  cannot create labels elsewhere; and
* every failed write was swallowed by a ``try``/``catch`` that only appended to the
  run summary, so the job concluded ``success`` with zero labels created.

These tests pin both fixes plus the ``issues: write`` permission.
"""

from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/maint-69-sync-labels.yml")
SYNC_JOB = "sync-labels"
SYNC_STEP = "Sync labels to repos"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _job() -> dict:
    return _workflow()["jobs"][SYNC_JOB]


def _step(name: str) -> dict:
    return next(step for step in _job()["steps"] if step.get("name") == name)


def test_label_sync_declares_issues_write_permission() -> None:
    permissions = _workflow()["permissions"]

    assert permissions.get("issues") == "write", (
        "label creation requires issues: write; without it the sync cannot write labels "
        "even in this repository"
    )


def test_label_sync_uses_cross_repo_token_not_default_github_token() -> None:
    job = _job()
    step = _step(SYNC_STEP)
    token = step["with"]["github-token"]

    assert "REPO_TOKEN" in job.get("env", {}), (
        "the job must alias a cross-repo PAT, mirroring maint-68-sync-consumer-repos.yml"
    )
    assert "github.token" not in token, (
        "the default GITHUB_TOKEN cannot create labels in other repositories; "
        f"got {token!r}"
    )
    assert "env.REPO_TOKEN" in token, f"expected the cross-repo token alias, got {token!r}"


def test_label_sync_refuses_to_run_without_a_cross_repo_token() -> None:
    guard = _step("Assert cross-repo token is present")

    assert "REPO_TOKEN" in guard["run"]
    assert "exit 1" in guard["run"], (
        "a missing PAT must fail loudly rather than silently syncing nothing"
    )


def test_label_sync_fails_the_job_when_any_label_write_errors() -> None:
    script = _step(SYNC_STEP)["with"]["script"]

    assert "core.setFailed" in script, (
        "label write errors must fail the job; otherwise a run that creates zero labels "
        "still concludes success (issue #3007)"
    )
    assert "totalErrors" in script, "per-repo error counts must be aggregated across repos"
    # The failure must be driven by the aggregate, not by a single repo's counter.
    assert "if (totalErrors > 0)" in script
