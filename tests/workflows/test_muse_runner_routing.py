"""Muse must be wired everywhere Cursor is: runner, registry, keepalive/autofix/followup routing.

Guards Workflows#3918/#3919: a runner nobody dispatches (or a label nobody routes) is inert.
"""

import os
import re
import subprocess
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


def _muse_git_identity() -> dict[str, str]:
    steps = _jobs(WF / "reusable-muse-run.yml")["muse"]["steps"]
    return next(step["env"] for step in steps if step.get("id") == "run_muse")


def test_run_step_sets_a_muse_git_identity():
    env = _muse_git_identity()
    assert env["GIT_AUTHOR_NAME"] == env["GIT_COMMITTER_NAME"] == "muse"
    assert (
        env["GIT_AUTHOR_EMAIL"] == env["GIT_COMMITTER_EMAIL"] == ("muse@users.noreply.github.com")
    )


def test_run_step_identity_overrides_a_cli_default_git_identity(tmp_path):
    # Exercise real Git without launching Muse or accessing any credential store.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        {key: value for key, value in _muse_git_identity().items() if key.startswith("GIT_")}
    )
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, env=env, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "--initial-branch=main")
    git("config", "user.name", "Claude")
    git("config", "user.email", "noreply@anthropic.com")
    git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "identity probe")
    assert git("show", "-s", "--format=%an|%ae|%cn|%ce", "HEAD") == (
        "muse|muse@users.noreply.github.com|muse|muse@users.noreply.github.com"
    )
