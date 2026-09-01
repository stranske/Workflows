"""Regression tests for #3299: non-consolidated consumer keepalive sweep fallback."""

from pathlib import Path

import yaml

SWEEP_PATH = Path("templates/consumer-repo/.github/workflows/agents-keepalive-sweep.yml")

# Exact named skip reason from issue #3299 — must appear so a structurally-off
# consolidated path is distinguishable from a healthy quiet re-evaluation.
NAMED_SKIP_REASON = "vars.USE_CONSOLIDATED_WORKFLOWS unset — no periodic re-evaluation in this repo"


def _load_sweep() -> dict:
    return yaml.safe_load(SWEEP_PATH.read_text(encoding="utf-8"))


def _job_if(job: dict) -> str:
    return str(job.get("if", ""))


def _job_script(job: dict) -> str:
    for step in job.get("steps") or []:
        if step.get("name") == "Dispatch keepalive loop for open agent PRs":
            return str((step.get("with") or {}).get("script", ""))
    return ""


def _job_run_text(job: dict) -> str:
    parts: list[str] = []
    for step in job.get("steps") or []:
        run = step.get("run")
        if isinstance(run, str):
            parts.append(run)
    return "\n".join(parts)


def test_nonconsolidated_fallback_job_dispatches_agents_81():
    jobs = _load_sweep()["jobs"]
    fallback = jobs.get("sweep_nonconsolidated")
    assert fallback is not None, "missing sweep_nonconsolidated job"
    assert "!= 'true'" in _job_if(fallback)
    script = _job_script(fallback)
    assert "agents-81-gate-followups.yml" in script
    assert "consumer-keepalive-sweep-nonconsolidated" in script


def test_consolidated_job_still_gated_on_consolidated_flag():
    jobs = _load_sweep()["jobs"]
    consolidated = jobs.get("sweep_consolidated")
    assert consolidated is not None, "missing sweep_consolidated job"
    assert "== 'true'" in _job_if(consolidated)
    assert "agents-81-gate-followups.yml" in _job_script(consolidated)


def test_every_repo_mode_has_named_re_evaluation_path():
    jobs = _load_sweep()["jobs"]
    consolidated_if = _job_if(jobs["sweep_consolidated"])
    nonconsolidated_if = _job_if(jobs["sweep_nonconsolidated"])
    assert "USE_CONSOLIDATED_WORKFLOWS" in consolidated_if
    assert "USE_CONSOLIDATED_WORKFLOWS" in nonconsolidated_if
    consolidated_summary = _job_script(jobs["sweep_consolidated"])
    nonconsolidated_summary = _job_script(jobs["sweep_nonconsolidated"])
    assert "consolidated mode" in consolidated_summary
    assert "non-consolidated mode" in nonconsolidated_summary


def test_skip_branch_emits_named_reason():
    """name_mode always runs and names the skipped path (issue #3299 AC)."""
    jobs = _load_sweep()["jobs"]
    name_mode = jobs.get("name_mode")
    assert name_mode is not None, "missing name_mode job for named skip reason"
    # Must not be gated — otherwise the skip reason itself can be skipped.
    assert not _job_if(name_mode) or _job_if(name_mode) in {"true", "${{ true }}"}
    run_text = _job_run_text(name_mode)
    assert NAMED_SKIP_REASON in run_text
    assert "sweep_nonconsolidated" in run_text
    assert "GITHUB_STEP_SUMMARY" in run_text


def test_bare_consolidated_only_gate_would_fail_deliberate_break():
    text = SWEEP_PATH.read_text(encoding="utf-8")
    has_nonconsolidated_job = "sweep_nonconsolidated:" in text
    has_fallback_if = "USE_CONSOLIDATED_WORKFLOWS != 'true'" in text
    has_named_skip = NAMED_SKIP_REASON in text
    assert (
        has_nonconsolidated_job and has_fallback_if and has_named_skip
    ), "deliberate-break shape: only consolidated gate with no fallback and no named skip"
