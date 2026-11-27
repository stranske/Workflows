import os
import shutil
import subprocess
from pathlib import Path

import yaml
from scripts import publish_integration_sync as publication

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
    assert "scripts/publish_integration_sync.py" in sparse_checkout
    assert "scripts/publish_integration_sync.py" in commit_script
    assert 'bash "$RUNNER_TEMP/apply-integration-templates.sh"' in apply_script
    assert '--apply-script "$RUNNER_TEMP/apply-integration-templates.sh"' in commit_script
    assert {".github/workflows", "pyproject.toml", "requirements.lock", "scripts"} <= set(
        publication.DELIVERY_PATHS
    )
    assert publication.OPTIONAL_DELIVERY_PATH == ".pre-commit-config.yaml"


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


def test_integration_sync_sparse_tree_includes_recovery_helpers(tmp_path: Path) -> None:
    checkout = next(
        step
        for step in _workflow()["jobs"]["sync"]["steps"]
        if step.get("name") == "Checkout Workflows repo"
    )["with"]
    source_paths = (
        ".github/scripts/error_classifier.js",
        ".github/scripts/github-api-with-retry.js",
        ".github/scripts/github-rate-limited-wrapper.js",
        ".github/scripts/sync_tracker_state.js",
        ".github/scripts/token_load_balancer.js",
        ".github/scripts/package.json",
    )
    vendor_path = ".github/scripts/node_modules/minimatch/package.json"
    for path in (*source_paths, vendor_path):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path, encoding="utf-8")

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-f", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "seed",
        ],
        cwd=tmp_path,
        check=True,
    )
    assert checkout["sparse-checkout-cone-mode"] is False
    subprocess.run(
        ["git", "sparse-checkout", "set", "--no-cone", "--stdin"],
        cwd=tmp_path,
        input=checkout["sparse-checkout"],
        text=True,
        check=True,
    )
    assert all((tmp_path / path).is_file() for path in source_paths)
    assert not (tmp_path / vendor_path).exists()


def test_integration_sync_success_closes_even_a_marker_free_legacy_alert() -> None:
    source = SYNC_WORKFLOW.read_text(encoding="utf-8")

    assert "if (!alert)" in source
    assert "if (!alert || !parseStuckWindow" not in source
    assert "title: '✅ Integration-Tests Sync Recovered'" in source
    assert "name: 'tracker:durable'" in source
    assert "state: 'closed'" in source
    assert "state_reason: 'completed'" in source


def test_integration_sync_api_setup_isolated_from_source_package(tmp_path: Path) -> None:
    workspace = tmp_path / "runner workspace"
    install_dir = workspace / "workflows/.github"
    scripts_dir = install_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    source_package = REPO_ROOT / ".github/scripts/package.json"
    shutil.copyfile(source_package, scripts_dir / "package.json")
    setup = next(
        step
        for step in _workflow()["jobs"]["sync"]["steps"]
        if step.get("name") == "Setup API client"
    )
    configured_dir = setup["with"]["install_dir"].replace("${{ github.workspace }}", str(workspace))
    action_dir = REPO_ROOT / ".github/actions/setup-api-client"
    action = yaml.safe_load((action_dir / "action.yml").read_text())
    assert not (scripts_dir / "node_modules").exists()

    # Exercise the authored setup and Node's lookup from the recovery source directory.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text(
        """#!/bin/bash
set -euo pipefail
test "$PWD" = "$GITHUB_WORKSPACE/workflows/.github"
test "$(cat package.json)" = '{"private":true}'
mkdir -p node_modules/test-api-client
printf '%s\n' '{"exports":{"require":"./index.cjs","import":"./index.mjs"}}' > node_modules/test-api-client/package.json
printf '%s\n' 'module.exports = true;' > node_modules/test-api-client/index.cjs
printf '%s\n' 'export default true;' > node_modules/test-api-client/index.mjs
""",
        encoding="utf-8",
    )
    npm.chmod(0o755)
    env_file = workspace / "env"
    env = os.environ | {
        "GITHUB_ENV": str(env_file),
        "GITHUB_WORKSPACE": str(workspace),
        "GITHUB_ACTION_PATH": str(action_dir),
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
    }
    for step in action["runs"]["steps"][:2]:
        script = step["run"].replace("${{ inputs.install_dir }}", configured_dir)
        result = subprocess.run(
            ["/bin/bash", "-c", script],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    assert (
        env_file.read_text(encoding="utf-8")
        .splitlines()[0]
        .startswith(f"NODE_PATH={install_dir / 'node_modules'}")
    )
    assert not (scripts_dir / "node_modules").exists()
    assert (scripts_dir / "package.json").read_bytes() == source_package.read_bytes()
    probe = scripts_dir / "probe.cjs"
    probe.write_text(
        """const assert = require('node:assert/strict');
assert.equal(require('test-api-client'), true);
import('test-api-client').then((module) => assert.equal(module.default, true));
""",
        encoding="utf-8",
    )
    subprocess.run(["node", str(probe)], cwd=workspace, check=True, timeout=10)


def test_integration_sync_summary_passes_the_publication_result_as_data() -> None:
    step = next(step for step in _workflow()["jobs"]["sync"]["steps"] if step["name"] == "Summary")
    assert step["env"]["PUBLISHED"] == "${{ steps.publish.outputs.published }}"
    assert 'elif [ "$PUBLISHED" = "false" ]' in step["run"]
    assert "steps.publish.outputs" not in step["run"]
