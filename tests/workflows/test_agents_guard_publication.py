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
const github = {paginate: async () => [], rest: {repos: {createCommitStatus: async () => {
  writes++;
  if (input.headFullName !== 'owner/repo') throw Error('fork token cannot write statuses');
}}}};
const context = {repo: {owner: 'owner', repo: 'repo'}, eventName: input.eventName,
  payload: {pull_request: {head: {sha: 'a'.repeat(40)}}}, sha: 'b'.repeat(40),
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
        input=json.dumps({"condition": step["if"], "script": step["with"]["script"], "eventName": event_name, "headFullName": head_full_name, "env": {"ELIGIBLE": eligible}}),
        text=True, capture_output=True, check=True,
    )
    evidence = json.loads(result.stdout)
    assert evidence["writes"] == expected_writes
    assert evidence["conditionPasses"] is (expected_writes == 1 or event_name == "pull_request_target")


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
 listCommitStatusesForRef() {}}}, paginate: async (method, params) => {
 if (params.ref !== 'a'.repeat(40)) throw Error('wrong status lookup head');
 return [{context: 'unrelated', state: 'failure'},
   ...(input.prior ? [{context: 'Health 45 Agents Guard / guard', state: input.prior}] : [])];
}};
const context = {repo: {owner: 'owner', repo: 'repo'},
  eventName: input.event,
  payload: {action: input.action, pull_request: {head: {sha: 'a'.repeat(40)}}},
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
    if eligible == "false" and (event == "pull_request_target" or prior_state is not None):
        # A removed last routing label must preserve the previous evaluated
        # verdict (including failure) rather than replacing it with a no-op.
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
const github = {paginate: async () => {
 if (input.mode === 'lookup_denied') throw Object.assign(Error('denied lookup'), {status: 403});
 if (input.mode === 'lookup_incomplete') return null;
 return [];
}, rest: {repos: {createCommitStatus: async () => {
  writes++;
  throw Object.assign(Error('denied'), {status: 403});
}}}};
const context = {repo: {owner: 'owner', repo: 'repo'}, sha: 'b'.repeat(40),
 payload: {pull_request: {head: {sha: input.mode === 'missing_head' ? '' : 'a'.repeat(40)}}}};
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
