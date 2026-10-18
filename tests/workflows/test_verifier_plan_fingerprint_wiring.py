"""The consumer verifier's existing dedup path includes canonical plan inputs."""

import json
import subprocess
from pathlib import Path

import yaml
from scripts import state_fingerprint

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


def test_plan_change_runs_once_through_existing_state_fingerprint_store(tmp_path):
    """Exercise the producer hash through the actual compare/store helper."""
    node_program = "\n".join(
        [
            "const fs = require('fs');",
            "const { verifierPlanSourceFingerprint } = require('./.github/scripts/verifier_plan_fingerprint.js');",
            "const input = JSON.parse(fs.readFileSync(0, 'utf8'));",
            "const github = { graphql: async () => ({ repository: { pullRequest: { repository: { nameWithOwner: 'stranske/Orchestrator' }, closingIssuesReferences: { totalCount: 0, pageInfo: { hasNextPage: false }, nodes: [] } } } }), rest: { issues: { get: async () => { throw new Error('unexpected issue lookup'); } } } };",
            "verifierPlanSourceFingerprint({ github, owner: 'stranske', repo: 'Orchestrator', pull: input.pull }).then((digest) => process.stdout.write(digest)).catch((error) => { process.stderr.write(error.message); process.exitCode = 1; });",
        ]
    )

    def plan_digest(body):
        result = subprocess.run(
            ["node", "-e", node_program],
            input=json.dumps(
                {
                    "pull": {
                        "number": 711,
                        "title": "Stable title",
                        "body": body,
                        "labels": [],
                    }
                }
            ),
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
        )
        return result.stdout

    class MemoryStorage:
        value = None

        def read_fingerprint(self, _workflow_name):
            return self.value

        def write_fingerprint(self, _workflow_name, fingerprint_hash):
            self.value = fingerprint_hash

    storage = MemoryStorage()
    common_inputs = {
        "pr_number": 711,
        "head_sha": "same-head",
        "diff_hash": "same-diff",
        "mode": "compare",
        "model": "",
        "model2": "",
        "provider": "",
        "evidence_profile": "standard",
        "evidence_contract": "bounded-native-capacity-v2",
        "verifier_trigger_labels": ["verify:compare"],
    }

    def compare_and_record(body):
        inputs = {**common_inputs, "plan_source_sha256": plan_digest(body)}
        decision = state_fingerprint.compare_fingerprint("Agents Verifier", inputs, storage)
        if decision.should_run:
            state_fingerprint.store_fingerprint("Agents Verifier", decision.current_hash, storage)
        return decision

    initial = """<!-- workflow-source: local_request -->
## Tasks
- [ ] Collect current evidence.
## Acceptance Criteria
- [ ] Preserve the existing verifier behavior.
## Latest status
CI refreshed at 10:00.
"""
    changed_criteria = initial.replace(
        "Preserve the existing verifier behavior.",
        "Preserve verifier behavior and bind current linked-source criteria.",
    )
    refreshed_status = changed_criteria.replace("CI refreshed at 10:00.", "CI refreshed at 10:01.")

    first_run = compare_and_record(initial)
    criteria_edit = compare_and_record(changed_criteria)
    unchanged_repeat = compare_and_record(changed_criteria)
    volatile_status = compare_and_record(refreshed_status)

    assert (first_run.should_run, first_run.reason) == (True, "no-prior-fingerprint")
    assert (criteria_edit.should_run, criteria_edit.reason) == (True, "fingerprint-changed")
    assert (unchanged_repeat.should_run, unchanged_repeat.reason) == (False, "fingerprint-match")
    assert (volatile_status.should_run, volatile_status.reason) == (False, "fingerprint-match")
