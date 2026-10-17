"""The consumer verifier's existing dedup path includes canonical plan inputs."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates/consumer-repo/.github/workflows/agents-verifier.yml"
SOURCE_HELPER = ROOT / ".github/scripts/verifier_plan_fingerprint.js"
TEMPLATE_HELPER = ROOT / "templates/consumer-repo/.github/scripts/verifier_plan_fingerprint.js"


def test_consumer_verifier_fingerprints_plan_sources_without_expanding_triggers():
    workflow_text = TEMPLATE.read_text()
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)

    triggers = workflow["on"]
    assert set(triggers) == {"pull_request_target", "workflow_dispatch"}
    assert triggers["pull_request_target"]["types"] == ["labeled"]

    check = workflow["jobs"]["check"]
    assert check["permissions"]["issues"] == "read"
    assert "plan_source_sha256" in check["outputs"]
    checkout = next(
        step
        for step in check["steps"]
        if step.get("name") == "Checkout retry helpers"
    )
    sparse_paths = checkout["with"]["sparse-checkout"]
    for path in (
        ".github/scripts/issue_scope_parser.js",
        ".github/scripts/source_context.js",
        ".github/scripts/verifier_plan_fingerprint.js",
    ):
        assert path in sparse_paths

    fingerprint_step = next(
        step for step in check["steps"] if step.get("name") == "Compute state fingerprint"
    )
    assert "VERIFIER_PLAN_SOURCE_SHA256" in fingerprint_step["env"]
    assert '"plan_source_sha256": plan_source_sha256' in fingerprint_step["run"]
    assert "Failed to fingerprint verifier plan sources" in workflow_text
    assert "core.setFailed" in workflow_text


def test_fingerprint_helper_is_copy_delivered_and_identical_in_template():
    assert SOURCE_HELPER.read_bytes() == TEMPLATE_HELPER.read_bytes()
    manifest = yaml.safe_load((ROOT / ".github/sync-manifest.yml").read_text())
    entries = [
        item
        for item in manifest["scripts"]
        if item.get("source") == ".github/scripts/verifier_plan_fingerprint.js"
    ]
    assert len(entries) == 1
    assert entries[0]["delivery"] == "copy"
