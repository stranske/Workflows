"""Muse must be wired everywhere Cursor is: runner, registry, keepalive/autofix/followup routing.

Guards Workflows#3918/#3919: a runner nobody dispatches (or a label nobody routes) is inert.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest
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


def _muse_git_identity(step_id: str = "run_muse") -> dict[str, str]:
    steps = _jobs(WF / "reusable-muse-run.yml")["muse"]["steps"]
    return next(step["env"] for step in steps if step.get("id") == step_id)


def test_run_step_sets_a_muse_git_identity():
    env = _muse_git_identity()
    expected = {
        "GIT_AUTHOR_NAME": "muse",
        "GIT_AUTHOR_EMAIL": "muse@users.noreply.github.com",
        "GIT_COMMITTER_NAME": "muse",
        "GIT_COMMITTER_EMAIL": "muse@users.noreply.github.com",
    }
    for variable, value in expected.items():
        assert variable in env, f"Run Muse env is missing {variable}"
        assert "claude" not in env[variable].casefold(), variable
        assert env[variable] == value, variable


def test_commit_step_preserves_the_run_step_git_identity():
    run_env = _muse_git_identity("run_muse")
    commit_env = _muse_git_identity("commit")
    for variable in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        assert variable in commit_env, f"Commit and push changes env is missing {variable}"
        assert commit_env[variable] == run_env[variable], variable


@pytest.mark.parametrize(
    "variable",
    ["GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"],
)
@pytest.mark.parametrize("mutation", ["missing", "claude"])
def test_run_step_git_identity_deliberate_break_and_restore(monkeypatch, variable, mutation):
    jobs = _jobs(WF / "reusable-muse-run.yml")
    step = next(step for step in jobs["muse"]["steps"] if step.get("id") == "run_muse")
    if mutation == "missing":
        del step["env"][variable]
    else:
        step["env"][variable] = "Claude" if variable.endswith("_NAME") else "Claude@example.com"

    # Mutate the parsed step only; the protected workflow stays untouched on disk.
    with monkeypatch.context() as broken:
        broken.setattr(f"{__name__}._jobs", lambda path: jobs)
        with pytest.raises(AssertionError, match=variable):
            test_run_step_sets_a_muse_git_identity()

    # Re-read the real workflow and prove the same named test is green after restoration.
    test_run_step_sets_a_muse_git_identity()


def test_run_step_identity_overrides_a_cli_default_git_identity(tmp_path, monkeypatch):
    # Exercise real Git without launching Muse or accessing any credential store.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args, step_id=None):
        step_env = env.copy()
        if step_id is not None:
            step_env.update(
                {
                    key: value
                    for key, value in _muse_git_identity(step_id).items()
                    if key.startswith("GIT_")
                }
            )
        return subprocess.run(
            ["git", *args], cwd=tmp_path, env=step_env, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "--initial-branch=main")
    git("config", "user.name", "Claude")
    git("config", "user.email", "noreply@anthropic.com")
    git("config", "commit.gpgsign", "false")
    git("commit", "--allow-empty", "-m", "base")
    git("checkout", "-b", "muse-feature")
    (tmp_path / "feature.txt").write_text("Muse feature\n")
    git("add", "feature.txt")
    git("commit", "-m", "identity probe", step_id="run_muse")
    expected_identity = "muse|muse@users.noreply.github.com|muse|muse@users.noreply.github.com"
    assert git("show", "-s", "--format=%an|%ae|%cn|%ce", "HEAD") == expected_identity
    feature_sha = git("rev-parse", "HEAD")

    # Advance a distinct main file so Git must replay the feature commit without conflicts.
    git("checkout", "main")
    (tmp_path / "main.txt").write_text("Concurrent main update\n")
    git("add", "main.txt")
    git("commit", "-m", "advance main")
    git("checkout", "muse-feature")
    # GitHub step environments are isolated: Run Muse's overrides cannot leak into this rebase.
    git("rebase", "main", step_id="commit")
    assert git("rev-parse", "HEAD") != feature_sha
    git("merge-base", "--is-ancestor", "main", "HEAD")
    assert (tmp_path / "main.txt").read_text() == "Concurrent main update\n"
    assert (tmp_path / "feature.txt").read_text() == "Muse feature\n"
    assert (
        git("show", "-s", "--format=%an|%ae|%cn|%ce", "HEAD") == expected_identity
    ), "Commit and push changes must preserve Muse author AND committer after rebase"

    # Replay the original feature commit again, deleting only the commit step's committer
    # name. Git must preserve the author and committer email but fall back to Claude's name.
    jobs = _jobs(WF / "reusable-muse-run.yml")
    commit_step = next(step for step in jobs["muse"]["steps"] if step.get("id") == "commit")
    del commit_step["env"]["GIT_COMMITTER_NAME"]
    git("reset", "--hard", feature_sha)
    with monkeypatch.context() as broken:
        broken.setattr(f"{__name__}._jobs", lambda path: jobs)
        git("rebase", "main", step_id="commit")
        delivered_identity = git("show", "-s", "--format=%an|%ae|%cn|%ce", "HEAD")
        with pytest.raises(AssertionError, match="delivered Muse identity"):
            assert delivered_identity == expected_identity, "delivered Muse identity changed"
        assert delivered_identity == (
            "muse|muse@users.noreply.github.com|Claude|muse@users.noreply.github.com"
        )

    # Restore by reading the actual workflow again, then force a fresh replay to prove recovery.
    git("reset", "--hard", feature_sha)
    git("rebase", "main", step_id="commit")
    assert git("rev-parse", "HEAD") != feature_sha
    git("merge-base", "--is-ancestor", "main", "HEAD")
    assert git("show", "-s", "--format=%an|%ae|%cn|%ce", "HEAD") == expected_identity
