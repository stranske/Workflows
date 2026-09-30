from pathlib import Path

import yaml


def test_authority_release_sparse_checkout_includes_state_fingerprint():
    workflow_paths = [
        ".github/workflows/agents-keepalive-loop.yml",
        "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml",
    ]

    for workflow_path in workflow_paths:
        workflow = yaml.safe_load(Path(workflow_path).read_text(encoding="utf-8"))
        preflight = workflow["jobs"]["preflight"]["steps"]
        checkout = next(
            step for step in preflight if step.get("name") == "Checkout authority release helpers"
        )

        assert checkout["with"]["sparse-checkout"].splitlines() == [
            ".github/scripts",
            "scripts/runner_lib",
            "scripts/state_fingerprint.py",
        ]
