from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "maint-69-sync-integration-repo.yml"
SYNC_MANIFEST = REPO_ROOT / ".github" / "sync-manifest.yml"

REQUIRED_HUBS = (
    "agents-80-pr-event-hub.yml",
    "agents-81-gate-followups.yml",
)


def _workflow() -> dict:
    return yaml.safe_load(SYNC_WORKFLOW.read_text(encoding="utf-8")) or {}


def _step_run(workflow: dict, step_name: str) -> str:
    steps = workflow["jobs"]["sync"]["steps"]
    for step in steps:
        if step.get("name") == step_name:
            return str(step.get("run", ""))
    raise AssertionError(f"Missing workflow step: {step_name}")


def test_integration_repo_sync_delivers_consumer_agent_hubs_to_wit() -> None:
    workflow = _workflow()
    checkout = next(
        step
        for step in workflow["jobs"]["sync"]["steps"]
        if step.get("name") == "Checkout Workflows repo"
    )
    sparse_checkout = str(checkout["with"]["sparse-checkout"])
    apply_script = _step_run(workflow, "Apply template updates")
    commit_script = _step_run(workflow, "Commit and push changes")

    for hub in REQUIRED_HUBS:
        source = f"templates/consumer-repo/.github/workflows/{hub}"

        assert (REPO_ROOT / source).exists()
        assert source in sparse_checkout
        assert "../workflows/templates/consumer-repo/.github/workflows/${workflow}" in apply_script
        assert hub in apply_script
        assert 'cp "${src}" ".github/workflows/${workflow}"' in apply_script
        assert hub in commit_script


def test_integration_repo_sync_aligns_dev_tool_pins() -> None:
    workflow = _workflow()
    checkout = next(
        step
        for step in workflow["jobs"]["sync"]["steps"]
        if step.get("name") == "Checkout Workflows repo"
    )
    sparse_checkout = str(checkout["with"]["sparse-checkout"])
    apply_script = _step_run(workflow, "Apply template updates")
    commit_script = _step_run(workflow, "Commit and push changes")

    assert "scripts/sync_dev_dependencies.py" in sparse_checkout
    assert 'python "../workflows/scripts/sync_dev_dependencies.py"' in apply_script
    assert '--pin-file ".github/workflows/autofix-versions.env"' in apply_script
    assert '--pyproject "pyproject.toml"' in apply_script
    assert "git add .github/workflows/ pyproject.toml requirements.lock scripts/" in commit_script
    assert commit_script.count("if [ -f .pre-commit-config.yaml ]; then") == 1
    assert commit_script.count("git add .pre-commit-config.yaml") == 1


def test_sync_manifest_removes_stale_consumer_local_workflow_syncer() -> None:
    manifest = yaml.safe_load(SYNC_MANIFEST.read_text(encoding="utf-8")) or {}
    removal_targets = {
        item.get("target") for item in manifest.get("removals", []) if isinstance(item, dict)
    }

    assert ".github/workflows/maint-sync-workflows.yml" in removal_targets
