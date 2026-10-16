"""Muse must be wired everywhere Cursor is: runner, registry, keepalive/autofix/followup routing.

Guards Workflows#3918/#3919: a runner nobody dispatches (or a label nobody routes) is inert.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github/workflows"
TEMPLATE_WF = ROOT / "templates/consumer-repo/.github/workflows"
ROUTED = [
    WF / "agents-keepalive-loop.yml",
    TEMPLATE_WF / "agents-81-gate-followups.yml",
]


def _jobs(path: Path) -> dict:
    return yaml.safe_load(path.read_text())["jobs"]


def test_runner_is_a_callable_workflow_with_the_subscription_secret():
    doc = yaml.safe_load((WF / "reusable-muse-run.yml").read_text())
    on = doc.get("on") or doc[True]
    assert "META_API_KEY" in on["workflow_call"]["secrets"]
    text = (WF / "reusable-muse-run.yml").read_text()
    assert "--yolo" not in text.replace("never --yolo", "").replace("(this is never --yolo", "")
    assert "GITHUB_ENV" not in re.sub(
        r"#.*", "", text.split("Preflight auth")[1].split("Ensure Muse CLI")[0]
    )


def test_registry_entries_match_in_root_and_template():
    for reg in (
        ROOT / ".github/agents/registry.yml",
        ROOT / "templates/consumer-repo/.github/agents/registry.yml",
    ):
        muse = yaml.safe_load(reg.read_text())["agents"]["muse"]
        assert muse["runner_workflow"].endswith("reusable-muse-run.yml")
        assert muse["branch_prefix"] == "muse/issue-"
        assert "META_API_KEY" in muse["required_secrets"]


def test_every_cursor_job_in_routed_workflows_has_a_muse_twin():
    for path in ROUTED:
        jobs = _jobs(path)
        assert "run-cursor" in jobs and "run-muse" in jobs, path.name
        assert "reusable-muse-run.yml" in jobs["run-muse"]["uses"]
        for job in jobs.values():
            needs = job.get("needs") or []
            needs = [needs] if isinstance(needs, str) else needs
            if "run-cursor" in needs:
                assert "run-muse" in needs, (path.name, "needs list lacks run-muse")


def test_cursor_and_muse_reference_counts_stay_in_step():
    for path in ROUTED:
        text = path.read_text()
        # one extra run-cursor reference is the job's own header
        assert text.count("run-muse") >= text.count("run-cursor") - 1, path.name


def test_autofix_loop_has_a_muse_job_and_accepts_the_agent():
    path = WF / "agents-autofix-loop.yml"
    jobs = _jobs(path)
    assert "reusable-muse-run.yml" in jobs["autofix-muse"]["uses"]
    assert jobs["autofix-muse"]["name"] == "Run Muse autofix"
    assert "'muse'" in re.search(r"const supportedAgents = \[(.*?)\];", path.read_text()).group(1)
    assert "autofix-muse" in jobs["record-autofix-completion"]["needs"]


def test_consumer_template_autofix_has_a_muse_job_feeding_metrics():
    jobs = _jobs(TEMPLATE_WF / "agents-81-gate-followups.yml")
    assert "reusable-muse-run.yml" in jobs["autofix-muse"]["uses"]
    assert "autofix-muse" in jobs["metrics"]["needs"]


def test_run_step_refuses_to_exec_after_a_failed_sandbox_or_prompt_guard():
    text = (WF / "reusable-muse-run.yml").read_text()
    assert "MUSE_CLI_OUTCOME: ${{ steps.ensure_muse.outcome }}" in text
    assert "Muse CLI or sandbox setup failed; muse exec was not run" in text
    # The CLI step must have SUCCEEDED (a skipped step is not a probed sandbox) and the guard
    # must not have failed, checked before the `muse exec` invocation.
    guard = (
        'if [ "${GUARD_OUTCOME:-}" = "failure" ] || [ "${MUSE_CLI_OUTCOME:-}" != "success" ]; then'
    )
    assert guard in text
    assert text.index(guard) < text.index('"$MUSE_BIN" exec')
    assert "grep -cvE '^.. agents/.*\\.md$' || true" in text


def test_run_step_sets_a_muse_git_identity():
    steps = _jobs(WF / "reusable-muse-run.yml")["muse"]["steps"]
    by_name = {s["name"]: s for s in steps}
    env = by_name["Run Muse"]["env"]
    for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        assert "muse" in env[var], var
        assert "claude" not in env[var].lower() and "anthropic" not in env[var].lower(), var
    names = [s["name"] for s in steps]
    assert names.index("Attribute Muse commits to Muse") < names.index("Commit and push changes")
    assert by_name["Attribute Muse commits to Muse"]["continue-on-error"] is True
