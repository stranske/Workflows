from pathlib import Path

import yaml


def test_authority_release_sparse_checkout_includes_state_fingerprint():
    workflow = yaml.safe_load(
        Path(
            "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
        ).read_text(encoding="utf-8")
    )
    preflight = workflow["jobs"]["preflight"]["steps"]
    checkout = next(
        step
        for step in preflight
        if step.get("name") == "Checkout authority release helpers"
    )
    sparse = checkout["with"]["sparse-checkout"]
    assert "scripts/runner_lib" in sparse
    assert "scripts/state_fingerprint.py" in sparse
