"""Regression tests for #3299: non-consolidated consumer keepalive sweep fallback."""

from pathlib import Path

import yaml

SWEEP_PATH = Path(
    "templates/consumer-repo/.github/workflows/agents-keepalive-sweep.yml"
)


def _load_sweep() -> dict:
    return yaml.safe_load(SWEEP_PATH.read_text(encoding="utf-8"))


def _job_if(job: dict) -> str:
    return str(job.get("if", ""))


def _job_script(job: dict) -> str:
    for step in job.get("steps") or []:
        if step.get("name") == "Dispatch keepalive loop for open agent PRs":
            return str((step.get("with") or {}).get("script", ""))
    return ""


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


def test_bare_consolidated_only_gate_would_fail_deliberate_break():
    text = SWEEP_PATH.read_text(encoding="utf-8")
    has_nonconsolidated_job = "sweep_nonconsolidated:" in text
    has_fallback_if = "USE_CONSOLIDATED_WORKFLOWS != 'true'" in text
    assert has_nonconsolidated_job and has_fallback_if, (
        "deliberate-break shape: only consolidated gate with no fallback"
    )
