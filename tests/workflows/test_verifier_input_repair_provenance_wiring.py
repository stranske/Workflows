"""Static contract for the provenance-only dispatch; behavior is covered by the Node suite."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-agents-verifier.yml"
CALLERS = [
    ROOT / ".github/workflows/agents-verifier.yml",
    ROOT / "templates/consumer-repo/.github/workflows/agents-verifier.yml",
]


def load(path):
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader)


def test_provenance_runs_in_its_own_provider_free_job_and_suppresses_the_verifier_job():
    jobs = load(WORKFLOW)["jobs"]
    assert jobs["verifier"]["if"] == "inputs.verification_provenance == ''"
    job = jobs["input-repair-provenance"]
    assert job["if"] == "inputs.verification_provenance != ''"
    assert "models" not in job["permissions"]
    assert job["permissions"]["pull-requests"] == "write"
    text = json.dumps(job)
    for forbidden in (
        "secrets.",
        "OPENAI",
        "CLAUDE",
        "CODEX",
        "verifier-event-state",
        "createComment",
    ):
        assert forbidden not in text


def test_every_caller_declares_and_threads_the_selector_identically():
    reusable = load(WORKFLOW)
    declared = reusable["on"]["workflow_call"]["inputs"]["verification_provenance"]
    for path in CALLERS:
        caller = load(path)
        dispatch = caller["on"]["workflow_dispatch"]["inputs"]["verification_provenance"]
        assert dispatch == declared
        assert (
            caller["jobs"]["verifier"]["with"]["verification_provenance"]
            == "${{ inputs.verification_provenance || '' }}"
        )


def test_consumer_script_copy_matches_source_bytes():
    name = ".github/scripts/verifier_pending_execution.js"
    assert (ROOT / name).read_bytes() == (ROOT / "templates/consumer-repo" / name).read_bytes()
