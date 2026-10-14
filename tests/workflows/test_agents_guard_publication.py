"""Execute the actual inline publisher, including ineligible and failed runs."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_guard_publisher_is_manifest_managed_and_template_aligned():
    manifest = yaml.safe_load((ROOT / ".github/sync-manifest.yml").read_text())
    entries = [
        entry
        for section in manifest.values()
        if isinstance(section, list)
        for entry in section
        if isinstance(entry, dict)
    ]
    assert any(entry.get("source") == ".github/workflows/agents-guard.yml" for entry in entries)
    publishers = []
    for prefix in [ROOT, ROOT / "templates/consumer-repo"]:
        workflow = yaml.safe_load((prefix / ".github/workflows/agents-guard.yml").read_text())
        publishers.append(
            next(
                s
                for s in workflow["jobs"]["guard"]["steps"]
                if s.get("name") == "Report agents guard commit status"
            )
        )
    assert publishers[0]["env"] == publishers[1]["env"]
    assert publishers[0]["with"] == publishers[1]["with"]


@pytest.mark.parametrize("template", [False, True])
def test_guard_publisher_skips_untrusted_fork_pull_request_events(template):
    """Fork pull_request tokens cannot publish commit statuses."""
    prefix = ROOT / "templates/consumer-repo" if template else ROOT
    workflow = yaml.safe_load((prefix / ".github/workflows/agents-guard.yml").read_text())
    step = next(
        item
        for item in workflow["jobs"]["guard"]["steps"]
        if item.get("name") == "Report agents guard commit status"
    )

    assert step["if"] == (
        "always() && (github.event_name == 'pull_request_target' || "
        "github.event.pull_request.head.repo.full_name == github.repository)"
    )


@pytest.mark.parametrize("template", [False, True])
@pytest.mark.parametrize(
    "event_name,head_full_name,eligible,expected_writes",
    [
        ("pull_request", "fork-owner/repo", "false", 0),
        ("pull_request", "fork-owner/repo", "true", 0),
        ("pull_request", None, "false", 0),
        ("pull_request", "owner/repo", "false", 1),
        ("pull_request_target", "fork-owner/repo", "false", 0),
    ],
)
def test_guard_publisher_executes_only_with_a_writable_status_token(
    template, event_name, head_full_name, eligible, expected_writes
):
    """Run the actual publisher only when its workflow condition permits it."""
    prefix = ROOT / "templates/consumer-repo" if template else ROOT
    workflow = yaml.safe_load((prefix / ".github/workflows/agents-guard.yml").read_text())
    step = next(
        item
        for item in workflow["jobs"]["guard"]["steps"]
        if item.get("name") == "Report agents guard commit status"
    )
    harness = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
Object.assign(process.env, input.env);
const expression = input.condition
  .replaceAll('github.', 'workflowGithub.');
const workflowGithub = {
  event_name: input.eventName,
  repository: 'owner/repo',
  event: {pull_request: {head: {repo: {full_name: input.headFullName}}}},
};
const conditionPasses = new Function('workflowGithub', 'always', `return (${expression});`)(
  workflowGithub, () => true,
);
let writes = 0;
const github = {paginate: async (method) => method === github.rest.issues.listLabelsOnIssue ? [] : [], rest: {repos: {createCommitStatus: async () => {
  writes++;
  if (input.headFullName !== 'owner/repo') throw Error('fork token cannot write statuses');
}}, issues: {listLabelsOnIssue() {}}}};
const context = {repo: {owner: 'owner', repo: 'repo'}, eventName: input.eventName,
  payload: {pull_request: {number: 4, labels: [], head: {sha: 'a'.repeat(40)}}}, sha: 'b'.repeat(40),
  serverUrl: 'https://github.com', runId: 42};
const core = {info() {}, setFailed(m) {throw Error(m)}};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
(async () => {
  if (conditionPasses) await new AsyncFunction('github', 'context', 'core', input.script)(github, context, core);
  process.stdout.write(JSON.stringify({conditionPasses, writes}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps(
            {
                "condition": step["if"],
                "script": step["with"]["script"],
                "eventName": event_name,
                "headFullName": head_full_name,
                "env": {"ELIGIBLE": eligible},
            }
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    evidence = json.loads(result.stdout)
    assert evidence["writes"] == expected_writes
    assert evidence["conditionPasses"] is (
        expected_writes == 1 or event_name == "pull_request_target"
    )


@pytest.mark.parametrize("template", [False, True])
@pytest.mark.parametrize("prior_state", [None, "failure", "error", "pending", "success"])
@pytest.mark.parametrize(
    "event,action",
    [
        ("pull_request", "synchronize"),
        ("pull_request", "reopened"),
        ("pull_request", "ready_for_review"),
        ("pull_request_target", "labeled"),
        ("pull_request_target", "unlabeled"),
    ],
)
@pytest.mark.parametrize(
    "eligible,outcome,blocked,job,expected",
    [
        ("false", "skipped", "", "success", "success"),
        ("true", "success", "false", "success", "success"),
        ("true", "success", "true", "success", "failure"),
        ("true", "failure", "", "failure", "failure"),
        ("true", "success", "", "success", "failure"),
        ("true", "success", "unknown", "success", "failure"),
        ("", "skipped", "", "failure", "failure"),
        ("true", "cancelled", "", "cancelled", "failure"),
    ],
)
def test_actual_head_publisher(
    template, prior_state, event, action, eligible, outcome, blocked, job, expected
):
    prefix = ROOT / "templates/consumer-repo" if template else ROOT
    workflow = yaml.safe_load((prefix / ".github/workflows/agents-guard.yml").read_text())
    step = next(
        s
        for s in workflow["jobs"]["guard"]["steps"]
        if s.get("name") == "Report agents guard commit status"
    )
    assert step["if"] == (
        "always() && (github.event_name == 'pull_request_target' || "
        "github.event.pull_request.head.repo.full_name == github.repository)"
    )
    assert step["with"]["github-token"] == "${{ github.token }}"
    script = step["with"]["script"]
    assert "require(" not in script
    harness = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
Object.assign(process.env, input.env);
const calls = [];
const github = {rest: {repos: {createCommitStatus: async p => calls.push(p),
 listCommitStatusesForRef() {}}, issues: {listLabelsOnIssue() {}}}, paginate: async (method, params) => {
 if (method === github.rest.issues.listLabelsOnIssue) return input.currentLabels;
 if (params.ref !== 'a'.repeat(40)) throw Error('wrong status lookup head');
 return [{context: 'unrelated', state: 'failure'},
   ...(input.prior ? [{context: 'Health 45 Agents Guard / guard', state: input.prior}] : [])];
}};
const context = {repo: {owner: 'owner', repo: 'repo'},
  eventName: input.event,
  payload: {action: input.action, pull_request: {number: 4, labels: input.snapshotLabels, head: {sha: 'a'.repeat(40)}}},
  sha: 'b'.repeat(40), serverUrl: 'https://github.com', runId: 42};
const core = {info() {}, setFailed(m) {throw Error(m)}};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', input.script)(github, context, core)
  .then(() => process.stdout.write(JSON.stringify(calls)))
  .catch(e => {console.error(e); process.exitCode = 1});
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps(
            {
                "script": script,
                "event": event,
                "action": action,
                "prior": prior_state,
                "snapshotLabels": [],
                "currentLabels": [],
                "env": {
                    "ELIGIBLE": eligible,
                    "EVALUATE_OUTCOME": outcome,
                    "BLOCKED": blocked,
                    "JOB_STATUS": job,
                },
            }
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    calls = json.loads(result.stdout)
    if eligible == "false" and prior_state is not None:
        if event == "pull_request_target" and prior_state == "success":
            # A final routing-label removal must invalidate a prior same-head
            # green verdict. A fresh eligible event supplies recovery.
            assert len(calls) == 1
            assert calls[0]["state"] == "failure"
            assert "routing changed" in calls[0]["description"]
            return
        # An ineligible event cannot clear a non-success terminal verdict.
        assert calls == []
        return
    if eligible == "false" and event == "pull_request_target":
        # An absent required context remains absent until an eligible run creates it.
        assert calls == []
        return
    assert len(calls) == 1
    assert calls[0]["sha"] == "a" * 40
    assert calls[0]["context"] == "Health 45 Agents Guard / guard"
    assert calls[0]["state"] == expected


@pytest.mark.parametrize("template", [False, True])
@pytest.mark.parametrize(
    "mode", ["denied_write", "missing_head", "lookup_denied", "lookup_incomplete"]
)
def test_publisher_cannot_silently_ignore_missing_head_or_denied_write(template, mode):
    prefix = ROOT / "templates/consumer-repo" if template else ROOT
    workflow = yaml.safe_load((prefix / ".github/workflows/agents-guard.yml").read_text())
    script = next(
        s
        for s in workflow["jobs"]["guard"]["steps"]
        if s.get("name") == "Report agents guard commit status"
    )["with"]["script"]
    harness = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
Object.assign(process.env, {ELIGIBLE: 'false', JOB_STATUS: 'success'});
let writes = 0;
const github = {paginate: async (method) => {
 if (method === github.rest.issues.listLabelsOnIssue) return [];
 if (input.mode === 'lookup_denied') throw Object.assign(Error('denied lookup'), {status: 403});
 if (input.mode === 'lookup_incomplete') return null;
 return [];
}, rest: {repos: {createCommitStatus: async () => {
  writes++;
  throw Object.assign(Error('denied'), {status: 403});
}}, issues: {listLabelsOnIssue() {}}}};
const context = {repo: {owner: 'owner', repo: 'repo'}, sha: 'b'.repeat(40),
 payload: {pull_request: {number: 4, labels: [], head: {sha: input.mode === 'missing_head' ? '' : 'a'.repeat(40)}}}};
const core = {info() {}, error() {}, warning() {}, setFailed(m) {throw Error(m)}};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', input.script)(github, context, core)
 .then(() => {process.exitCode = 2})
 .catch(e => process.stdout.write(JSON.stringify({message: e.message, writes})));
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps({"script": script, "mode": mode}),
        text=True,
        capture_output=True,
        check=True,
    )
    evidence = json.loads(result.stdout)
    assert (
        "PR head SHA unavailable" if mode == "missing_head" else "Failed to update"
    ) in evidence["message"]
    assert evidence["writes"] == (1 if mode == "denied_write" else 0)


def test_guard_status_writers_share_non_cancelling_head_serialization():
    direct = yaml.safe_load((ROOT / ".github/workflows/agents-guard.yml").read_text())
    fork = yaml.safe_load((ROOT / ".github/workflows/agents-guard-fork-status.yml").read_text())
    direct_template = yaml.safe_load(
        (ROOT / "templates/consumer-repo/.github/workflows/agents-guard.yml").read_text()
    )
    fork_template = yaml.safe_load(
        (
            ROOT / "templates/consumer-repo/.github/workflows/agents-guard-fork-status.yml"
        ).read_text()
    )
    assert (
        direct["concurrency"]
        == direct_template["concurrency"]
        == {
            "group": "agents-guard-status-${{ github.event.pull_request.head.sha || github.run_id }}",
            "cancel-in-progress": False,
        }
    )
    assert (
        fork["concurrency"]
        == fork_template["concurrency"]
        == {
            "group": "agents-guard-status-${{ github.event.workflow_run.head_sha || github.run_id }}",
            "cancel-in-progress": False,
        }
    )


def test_shared_head_group_closes_label_writer_noop_publisher_race():
    """A label failure and a completed fork no-op must serialize on the same head."""
    sha = "a" * 40
    current_direct = (
        "agents-guard-status-${{ github.event.pull_request.head.sha || github.run_id }}"
    )
    current_publisher = (
        "agents-guard-status-${{ github.event.workflow_run.head_sha || github.run_id }}"
    )
    legacy_direct = "agents-guard-${{ github.event.pull_request.number || github.run_id }}"
    legacy_publisher = (
        "agents-guard-fork-status-${{ github.event.workflow_run.head_sha || github.run_id }}"
    )

    def render(group, *, number="4"):
        return (
            group.replace("${{ github.event.pull_request.head.sha || github.run_id }}", sha)
            .replace("${{ github.event.workflow_run.head_sha || github.run_id }}", sha)
            .replace("${{ github.event.pull_request.number || github.run_id }}", number)
        )

    # Deliberate RED: prior independent groups let either status writer pass
    # the other between its final status read and write.
    assert render(legacy_direct) != render(legacy_publisher)
    # GREEN: serialized writers ensure the no-op observes a completed label
    # verdict before it applies the existing no-op preservation rule.
    assert render(current_direct) == render(current_publisher) == f"agents-guard-status-{sha}"


@pytest.mark.parametrize(
    "prior,snapshot,current,expected_state",
    [
        (
            None,
            [{"name": "agent:codex"}, {"name": "agents:allow-change"}],
            [{"name": "agent:codex"}],
            "failure",
        ),
        (
            "success",
            [{"name": "agent:codex"}, {"name": "agents:allow-change"}],
            [{"name": "agent:codex"}],
            "failure",
        ),
        (
            "success",
            [{"name": "agent:codex"}],
            [{"name": "agent:codex"}, {"name": "sync:delivery-sealed"}],
            "success",
        ),
    ],
)
def test_guard_publisher_fails_closed_only_when_policy_labels_change(
    prior, snapshot, current, expected_state
):
    workflow = yaml.safe_load((ROOT / ".github/workflows/agents-guard.yml").read_text())
    script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["guard"]["steps"]
        if step.get("name") == "Report agents guard commit status"
    )
    harness = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
Object.assign(process.env, input.env);
const writes = [];
const github = {rest: {repos: {createCommitStatus: async p => writes.push(p), listCommitStatusesForRef() {}}, issues: {listLabelsOnIssue() {}}}, paginate: async method => method === github.rest.issues.listLabelsOnIssue ? input.current : [{context: 'Health 45 Agents Guard / guard', state: input.prior}].filter(Boolean)};
const context = {repo: {owner: 'owner', repo: 'repo'}, eventName: 'pull_request_target', payload: {pull_request: {number: 4, labels: input.snapshot, head: {sha: 'a'.repeat(40)}}}, serverUrl: 'https://github.com', runId: 42};
const core = {info() {}, error() {}, setFailed(message) { throw Error(message); }};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', input.script)(github, context, core).then(() => process.stdout.write(JSON.stringify(writes)));
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps(
            {
                "script": script,
                "snapshot": snapshot,
                "current": current,
                "prior": prior,
                "env": {
                    "ELIGIBLE": "true",
                    "EVALUATE_OUTCOME": "success",
                    "BLOCKED": "false",
                    "JOB_STATUS": "success",
                },
            }
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    writes = json.loads(result.stdout)
    assert len(writes) == 1
    assert writes[0]["state"] == expected_state
    assert writes[0]["context"] == "Health 45 Agents Guard / guard"
    if expected_state == "failure":
        assert "labels changed" in writes[0]["description"]
