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


# --- Cohesion review A5b: Cursor and Muse share the alert step -----------------

COMPOSITE = WORKFLOWS.parent / "actions" / "auth-alert-issue" / "action.yml"


def test_auth_alert_composite_raises_and_resolves_through_the_shared_helper():
    action = yaml.safe_load(COMPOSITE.read_text(encoding="utf-8"))
    (step,) = action["runs"]["steps"]
    run = step["run"]
    assert run.count("python3 .github/scripts/resolve_alert_issue.py") == 2
    assert "--mode resolve" in run and "--mode raise" in run
    assert '[ "$ALERT_STATUS" = "ok" ]' in run
    assert action["inputs"]["labels"]["default"] == "auth-expiring,ci"


@pytest.mark.parametrize(
    ("workflow", "status_expr", "title_word"),
    [
        (
            "health-cursor-auth-check.yml",
            "steps.key.outputs.status == 'present' && 'ok' || 'failed'",
            "CURSOR_API_KEY",
        ),
        ("health-muse-auth-check.yml", "steps.verdict.outputs.status || 'failed'", "Muse"),
    ],
)
def test_cursor_and_muse_call_the_alert_composite_once_on_every_run(
    workflow, status_expr, title_word
):
    doc = _load(workflow)
    assert doc["permissions"]["issues"] == "write"
    (job,) = doc["jobs"].values()
    uses = [s for s in job["steps"] if s.get("uses") == "./.github/actions/auth-alert-issue"]
    assert len(uses) == 1, f"{workflow} must call the alert composite exactly once"
    step = uses[0]
    assert step["if"] == "always()"
    assert step.get("continue-on-error") is True
    assert step["with"]["status"] == "${{ " + status_expr + " }}"
    assert title_word in step["with"]["title"]
    # the composite is checked out, and the verdict still fails the run after alerting
    checkout = job["steps"][0]
    assert ".github/actions/auth-alert-issue" in checkout["with"]["sparse-checkout"]
    assert ".github/scripts/resolve_alert_issue.py" in checkout["with"]["sparse-checkout"]
    names = [s.get("name") for s in job["steps"]]
    assert names.index(step["name"]) < names.index("Verdict")
    assert "exit 1" in job["steps"][names.index("Verdict")]["run"]


def test_auth_alert_titles_are_distinct_so_no_check_closes_another():
    titles = []
    for workflow in ("health-cursor-auth-check.yml", "health-muse-auth-check.yml"):
        (job,) = _load(workflow)["jobs"].values()
        titles += [
            s["with"]["title"]
            for s in job["steps"]
            if s.get("uses") == "./.github/actions/auth-alert-issue"
        ]
    assert len(set(titles)) == 2
    assert not any("CODEX_AUTH_JSON" in title for title in titles)
    codex = (WORKFLOWS / "health-codex-auth-check.yml").read_text(encoding="utf-8")
    # Codex's duplicate check must ignore the Cursor/Muse alerts that share its label.
    assert "includes('CODEX_AUTH_JSON')" in codex


def _run_composite(tmp_path, status, open_issues):
    import json
    import os
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - host dependent
        pytest.skip("bash is required")
    repo_root = WORKFLOWS.parents[1]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh.log"
    (tmp_path / "issues.json").write_text(json.dumps(open_issues), encoding="utf-8")
    fake = bin_dir / "gh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        'if [ "$1 $2" = "issue list" ]; then cat "' + str(tmp_path / "issues.json") + '"; fi\n'
        'if [ "$1 $2" = "issue create" ]; then echo https://github.com/o/r/issues/77; fi\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    run = yaml.safe_load(COMPOSITE.read_text(encoding="utf-8"))["runs"]["steps"][0]["run"]
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GH_TOKEN": "x",
        "ALERT_STATUS": status,
        "ALERT_TITLE": "🚨 CURSOR_API_KEY is missing - Cursor runs cannot authenticate",
        "ALERT_DETAIL": "key missing",
        "ALERT_WORKFLOW": "Health 77 Cursor Auth Check",
        "ALERT_LABELS": "auth-expiring,ci",
        "REPO": "o/r",
        "RUN_URL": "https://example.invalid/run/1",
    }
    subprocess.run([bash, "-c", run], cwd=repo_root, env=env, check=True)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    # multi-line --comment/--body values span lines; count gh invocations only
    return [c for c in calls if c.startswith("issue ") and not c.startswith("issue list")]


def test_forced_failure_produces_exactly_one_issue_write(tmp_path):
    writes = _run_composite(tmp_path, "failed", [])
    assert len(writes) == 1 and writes[0].startswith("issue create"), writes
    assert "--label auth-expiring --label ci" in writes[0]


def test_repeated_failure_edits_the_open_alert(tmp_path):
    title = "🚨 CURSOR_API_KEY is missing - Cursor runs cannot authenticate"
    writes = _run_composite(tmp_path, "failed", [{"number": 5, "title": title}])
    assert len(writes) == 1 and writes[0].startswith("issue edit 5"), writes


def test_pass_closes_only_its_own_alert(tmp_path):
    title = "🚨 CURSOR_API_KEY is missing - Cursor runs cannot authenticate"
    writes = _run_composite(
        tmp_path,
        "ok",
        [
            {"number": 5, "title": title},
            {"number": 6, "title": "⚠️ CODEX_AUTH_JSON expires in 3 hours"},
        ],
    )
    assert len(writes) == 1 and writes[0].startswith("issue close 5"), writes
