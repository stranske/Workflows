import json
import os
import shutil
import subprocess
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
    assert "scripts/sync_integration_coverage_omit.py" in sparse_checkout
    assert 'python "../workflows/scripts/sync_dev_dependencies.py"' in apply_script
    assert '--pin-file ".github/workflows/autofix-versions.env"' in apply_script
    assert '--pyproject "pyproject.toml"' in apply_script
    assert 'python "../workflows/scripts/sync_integration_coverage_omit.py"' in apply_script
    assert '--template "../workflows/templates/integration-repo/pyproject.toml"' in apply_script
    assert "git add .github/workflows/ pyproject.toml requirements.lock scripts/" in commit_script
    assert commit_script.count("if [ -f .pre-commit-config.yaml ]; then") == 1
    assert commit_script.count("git add .pre-commit-config.yaml") == 1


def test_sync_manifest_removes_stale_consumer_local_workflow_syncer() -> None:
    manifest = yaml.safe_load(SYNC_MANIFEST.read_text(encoding="utf-8")) or {}
    removal_targets = {
        item.get("target") for item in manifest.get("removals", []) if isinstance(item, dict)
    }

    assert ".github/workflows/maint-sync-workflows.yml" in removal_targets


def test_integration_sync_failure_is_a_transient_alert() -> None:
    source = SYNC_WORKFLOW.read_text(encoding="utf-8")

    assert "> **Transient alert**" in source
    assert "durable: false" in source
    assert "preserveDurableHeader: false" in source
    assert "Do not close this durable tracker after recovery." not in source


def test_integration_sync_checks_out_the_retry_helpers_runtime_dependencies() -> None:
    workflow = _workflow()
    checkout = next(
        step
        for step in workflow["jobs"]["sync"]["steps"]
        if step.get("name") == "Checkout Workflows repo"
    )
    sparse_checkout = str(checkout["with"]["sparse-checkout"])

    for helper in (
        ".github/scripts/error_classifier.js",
        ".github/scripts/github-api-with-retry.js",
        ".github/scripts/github-rate-limited-wrapper.js",
        ".github/scripts/token_load_balancer.js",
    ):
        assert helper in sparse_checkout


def test_integration_sync_success_closes_even_a_marker_free_legacy_alert() -> None:
    source = SYNC_WORKFLOW.read_text(encoding="utf-8")

    assert "if (!alert)" in source
    assert "if (!alert || !parseStuckWindow" not in source
    assert "title: '✅ Integration-Tests Sync Recovered'" in source
    assert "name: 'tracker:durable'" in source
    assert "state: 'closed'" in source
    assert "state_reason: 'completed'" in source


def test_integration_sync_api_setup_preserves_vendored_dependencies(tmp_path: Path) -> None:
    workspace = tmp_path / "runner workspace"
    install_dir = workspace / "workflows/.github/scripts"
    install_dir.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / ".github/scripts/package.json", install_dir / "package.json")
    shutil.copytree(REPO_ROOT / ".github/scripts/node_modules", install_dir / "node_modules")
    original_package = (install_dir / "package.json").read_bytes()
    setup = next(
        step
        for step in _workflow()["jobs"]["sync"]["steps"]
        if step.get("name") == "Setup API client"
    )
    configured_dir = setup["with"]["install_dir"].replace("${{ github.workspace }}", str(workspace))
    action_dir = REPO_ROOT / ".github/actions/setup-api-client"
    action = yaml.safe_load((action_dir / "action.yml").read_text())
    script = action["runs"]["steps"][0]["run"].replace("${{ inputs.install_dir }}", configured_dir)
    # Exercise the authored shell and alias helper; only the external installer is inert.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        'node -e \'const fs = require("fs"); '
        'const p = JSON.parse(fs.readFileSync("minimatch/package.json")); '
        'if (p.name !== "minimatch") process.exit(1);\'\n'
        'touch "$GITHUB_WORKSPACE/npm-invoked"\n'
    )
    npm.chmod(0o755)
    sleep = bin_dir / "sleep"
    sleep.write_text("#!/bin/bash\nexit 0\n")
    sleep.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", "-c", script],
        cwd=workspace,
        env=os.environ
        | {
            "GITHUB_WORKSPACE": str(workspace),
            "GITHUB_ACTION_PATH": str(action_dir),
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (workspace / "npm-invoked").is_file()
    assert not (install_dir / "minimatch").exists()
    assert (install_dir / "node_modules/minimatch/package.json").is_file()
    assert (install_dir / "package.json").read_bytes() == original_package
    assert json.loads(original_package)["dependencies"]["minimatch"].startswith("file:")
