from pathlib import Path

import yaml


def test_maint46_sparse_checkout_includes_post_ci_import_dependencies():
    workflow = yaml.safe_load(
        Path(".github/workflows/maint-46-post-ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["summary"]["steps"]
    checkout = next(step for step in steps if step.get("name") == "Checkout helpers")
    sparse_checkout = checkout["with"]["sparse-checkout"]

    assert "tools/post_ci_summary.py" in sparse_checkout
    assert "tools/__init__.py" in sparse_checkout
    assert "tools/ci_failure_triage.py" in sparse_checkout


def test_maint46_runs_post_ci_summary_as_importable_module():
    workflow = yaml.safe_load(
        Path(".github/workflows/maint-46-post-ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["summary"]["steps"]
    render = next(step for step in steps if step.get("name") == "Build summary body")

    assert "python -m tools.post_ci_summary" in render["run"]
    assert "python tools/post_ci_summary.py" not in render["run"]


def test_maint46_gate_artifact_download_fails_open_to_metadata_summary():
    workflow = yaml.safe_load(
        Path(".github/workflows/maint-46-post-ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["summary"]["steps"]
    download = next(step for step in steps if step.get("name") == "Download Gate artifacts")
    note = next(
        step for step in steps if step.get("name") == "Note Gate artifact download limitation"
    )

    assert download["id"] == "download_gate_artifacts"
    assert download["continue-on-error"] is True
    assert note["if"] == "${{ steps.download_gate_artifacts.outcome == 'failure' }}"
    assert "artifact-only coverage detail" in note["run"]
