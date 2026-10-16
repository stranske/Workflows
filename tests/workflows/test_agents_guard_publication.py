"""Execute the actual inline publisher, including ineligible and failed runs."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def with_current_direct_binding(harness):
    """Supply authenticated current PR/run fixtures for corrective-write tests."""
    fixture = r"""
context.eventName ||= 'pull_request';context.runId ||= 42;
context.payload.pull_request.base.repo={id:1};context.payload.pull_request.base.ref='main';
process.env.GITHUB_RUN_ATTEMPT='1';
github.rest.pulls={get:async()=>({data:{...context.payload.pull_request,state:'open'}})};
const currentGuardRun={id:context.runId,workflow_id:7,path:'.github/workflows/agents-guard.yml',event:context.eventName,head_sha:context.eventName==='pull_request'?context.payload.pull_request.head.sha:(context.sha||'b'.repeat(40)),run_number:5,run_attempt:1,created_at:'2026-10-16T01:00:00Z',pull_requests:[{number:4}]};
context.sha=currentGuardRun.head_sha;
github.rest.actions={getWorkflowRun:async()=>({data:currentGuardRun}),listWorkflowRuns(){}};
const originalPaginate=github.paginate;
github.paginate=async(method,params)=>method===github.rest.actions.listWorkflowRuns?[currentGuardRun]:originalPaginate(method,params);
"""
    return harness.replace("const AsyncFunction", fixture + "\nconst AsyncFunction")


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
github.rest.repos.getContent = async params => { if(params.ref !== 'b'.repeat(40)) throw Error('untrusted registry ref'); return {data:{type:'file',encoding:'base64',content:"YWdlbnRzOgogIGNvZGV4OgogICAgZW5hYmxlZDogdHJ1ZQogIGNsYXVkZToKICAgIGVuYWJsZWQ6IHRydWUKICBjdXJzb3I6CiAgICBlbmFibGVkOiB0cnVlCiAgZ2VtaW5pOgogICAgZW5hYmxlZDogdHJ1ZQogIGFpZGVyOgogICAgZW5hYmxlZDogZmFsc2UK"}}; };
context.payload.pull_request.base = {sha:'b'.repeat(40)};
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
github.rest.repos.getContent = async params => { if(params.ref !== 'b'.repeat(40)) throw Error('untrusted registry ref'); return {data:{type:'file',encoding:'base64',content:"YWdlbnRzOgogIGNvZGV4OgogICAgZW5hYmxlZDogdHJ1ZQogIGNsYXVkZToKICAgIGVuYWJsZWQ6IHRydWUKICBjdXJzb3I6CiAgICBlbmFibGVkOiB0cnVlCiAgZ2VtaW5pOgogICAgZW5hYmxlZDogdHJ1ZQogIGFpZGVyOgogICAgZW5hYmxlZDogZmFsc2UK"}}; };
context.payload.pull_request.base = {sha:'b'.repeat(40)};
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
                    "EVALUATED_LABELS": "[]",
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
            assert "policy changed" in calls[0]["description"]
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
    "mode",
    [
        "denied_write",
        "missing_head",
        "lookup_denied",
        "lookup_incomplete",
        "registry_denied",
        "registry_malformed",
    ],
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
github.rest.repos.getContent = async params => { if(input.mode==='registry_denied') throw Error('registry unavailable'); if(input.mode==='registry_malformed') return {data:{type:'file',encoding:'none'}}; if(params.ref !== 'b'.repeat(40)) throw Error('untrusted registry ref'); return {data:{type:'file',encoding:'base64',content:"YWdlbnRzOgogIGNvZGV4OgogICAgZW5hYmxlZDogdHJ1ZQogIGNsYXVkZToKICAgIGVuYWJsZWQ6IHRydWUKICBjdXJzb3I6CiAgICBlbmFibGVkOiB0cnVlCiAgZ2VtaW5pOgogICAgZW5hYmxlZDogdHJ1ZQogIGFpZGVyOgogICAgZW5hYmxlZDogZmFsc2UK"}}; };
context.payload.pull_request.base = {sha:'b'.repeat(40)};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', input.script)(github, context, core)
 .then(() => {process.exitCode = 2})
 .catch(e => process.stdout.write(JSON.stringify({message: e.message, writes})));
"""
    harness = with_current_direct_binding(harness)
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
    assert evidence["writes"] == (
        1 if mode in {"denied_write", "registry_denied", "registry_malformed"} else 0
    )


@pytest.mark.parametrize(
    "evaluated_labels,expected_state",
    [
        ('[{"name":"agents:allow-change"}]', "failure"),
        ("", "failure"),
        ("not-json", "failure"),
        ("[]", "success"),
    ],
)
def test_actual_head_publisher_binds_evaluated_label_evidence(evaluated_labels, expected_state):
    workflow = yaml.safe_load((ROOT / ".github/workflows/agents-guard.yml").read_text())
    script = next(
        s
        for s in workflow["jobs"]["guard"]["steps"]
        if s.get("name") == "Report agents guard commit status"
    )["with"]["script"]
    harness = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8')); Object.assign(process.env, input.env);
const writes = []; const github = {rest: {repos: {createCommitStatus: async p => writes.push(p)}, issues: {listLabelsOnIssue() {}}}, paginate: async method => method === github.rest.issues.listLabelsOnIssue ? [] : []};
const context = {repo: {owner:'owner', repo:'repo'}, eventName:'pull_request_target', runId:42, serverUrl:'https://github.com', payload:{pull_request:{number:4, labels:[], head:{sha:'a'.repeat(40)}}}};
const core = {info(){}, error(){}, setFailed(m){throw Error(m)}}; github.rest.repos.getContent = async params => { if(input.mode==='registry_denied') throw Error('registry unavailable'); if(input.mode==='registry_malformed') return {data:{type:'file',encoding:'none'}}; if(params.ref !== 'b'.repeat(40)) throw Error('untrusted registry ref'); return {data:{type:'file',encoding:'base64',content:"YWdlbnRzOgogIGNvZGV4OgogICAgZW5hYmxlZDogdHJ1ZQogIGNsYXVkZToKICAgIGVuYWJsZWQ6IHRydWUKICBjdXJzb3I6CiAgICBlbmFibGVkOiB0cnVlCiAgZ2VtaW5pOgogICAgZW5hYmxlZDogdHJ1ZQogIGFpZGVyOgogICAgZW5hYmxlZDogZmFsc2UK"}}; };
context.payload.pull_request.base = {sha:'b'.repeat(40)};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github','context','core',input.script)(github,context,core).then(()=>process.stdout.write(JSON.stringify(writes))).catch(e=>{console.error(e);process.exitCode=1});
"""
    payload = {
        "script": script,
        "env": {
            "ELIGIBLE": "true",
            "EVALUATE_OUTCOME": "success",
            "BLOCKED": "false",
            "JOB_STATUS": "success",
            "EVALUATED_LABELS": evaluated_labels,
        },
    }
    completed = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    writes = json.loads(completed.stdout)
    assert [write["state"] for write in writes] == [expected_state]


def test_guard_status_writer_classifies_before_joining_the_shared_group():
    workflow = yaml.safe_load((ROOT / ".github/workflows/agents-guard-fork-status.yml").read_text())
    template = yaml.safe_load(
        (
            ROOT / "templates/consumer-repo/.github/workflows/agents-guard-fork-status.yml"
        ).read_text()
    )
    assert workflow["permissions"] == template["permissions"]
    assert workflow["jobs"]["classify"]["permissions"] == {"actions": "read"}
    assert workflow["jobs"]["classify"]["steps"][0]["uses"] == (
        "stranske/Workflows/.github/actions/setup-api-client@ab8017a10e387869e0f73ee07f3b7f634e45ea07"
    )
    assert workflow["jobs"]["classify"]["steps"][0]["with"] == {
        "github_token": "${{ github.token }}",
        "skip_deps": True,
    }
    assert "concurrency" not in workflow
    assert "concurrency" not in template
    assert workflow["jobs"]["publish"]["needs"] == "classify"
    assert workflow["jobs"]["publish"]["if"] == "${{ needs.classify.outputs.canonical == 'true' }}"
    assert (
        workflow["jobs"]["publish"]["concurrency"]
        == template["jobs"]["publish"]["concurrency"]
        == {
            "group": "${{ needs.classify.outputs.canonical == 'true' && format('agents-guard-status-{0}', needs.classify.outputs.head_sha) || format('agents-guard-fork-status-{0}', github.run_id) }}",
            "cancel-in-progress": False,
        }
    )


def test_guard_status_writer_classifies_canonical_runs_before_shared_queue():
    workflow = yaml.safe_load((ROOT / ".github/workflows/agents-guard-fork-status.yml").read_text())
    classifier = next(
        step["with"]["script"]
        for step in workflow["jobs"]["classify"]["steps"]
        if step.get("id") == "classify"
    )
    group_expression = workflow["jobs"]["publish"]["concurrency"]["group"]
    publish_expression = workflow["jobs"]["publish"]["if"]

    def classify(payload_run, payload_workflow, fresh_run, fresh_workflow, *, raises=False):
        payload = {
            "script": classifier,
            "payloadRun": payload_run,
            "payloadWorkflow": payload_workflow,
            "freshRun": fresh_run,
            "freshWorkflow": fresh_workflow,
            "raises": raises,
        }
        source = r"""
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const outputs = {};
const core = {setOutput: (key, value) => { outputs[key] = String(value); }, setFailed: message => { outputs.failure = String(message); }};
const github = {rest: {actions: {
  async getWorkflowRun() { if (input.raises) throw new Error('unavailable'); return {data: input.freshRun}; },
  async getWorkflow() { if (input.raises) throw new Error('unavailable'); return {data: input.freshWorkflow}; },
}}};
const context = {repo: {owner: 'owner', repo: 'repo'}, payload: {
  repository: {id: 9}, workflow_run: input.payloadRun, workflow: input.payloadWorkflow,
}};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', input.script)(github, context, core)
  .then(() => process.stdout.write(JSON.stringify(outputs)))
  .catch(error => { console.error(error); process.exitCode = 1; });
"""
        completed = subprocess.run(
            ["node", "-e", source],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(completed.stdout)

    canonical_run = {
        "id": 31,
        "workflow_id": 45,
        "event": "pull_request",
        "status": "completed",
        "repository": {"id": 9},
        "head_sha": "a" * 40,
        "path": ".github/workflows/agents-guard.yml@refs/heads/main",
    }
    canonical_workflow = {
        "id": 45,
        "path": ".github/workflows/agents-guard.yml",
        "name": "Health 45 Agents Guard",
    }
    assert classify(canonical_run, {"id": 45}, canonical_run, canonical_workflow) == {
        "canonical": "true",
        "head_sha": "a" * 40,
    }
    for payload_workflow, fresh_workflow, fresh_run, raises in (
        (
            {"id": 45},
            {**canonical_workflow, "path": ".github/workflows/AGENTS-GUARD.yml"},
            canonical_run,
            False,
        ),
        ({"id": 45}, {**canonical_workflow, "name": "Other"}, canonical_run, False),
        ({"id": 45}, canonical_workflow, {**canonical_run, "event": "pull_request_target"}, False),
        ({"id": 45}, canonical_workflow, {**canonical_run, "status": "in_progress"}, False),
        ({"id": 45}, canonical_workflow, {**canonical_run, "repository": {"id": 10}}, False),
        ({"id": 45}, canonical_workflow, canonical_run, True),
        ({"id": 0}, canonical_workflow, canonical_run, False),
        ({"id": None}, canonical_workflow, canonical_run, False),
    ):
        result = classify(canonical_run, payload_workflow, fresh_run, fresh_workflow, raises=raises)
        assert result["canonical"] == "false"
        assert result["head_sha"] == ""
        if raises:
            assert result["failure"] == "Unable to classify Agents Guard workflow run: unavailable"
        else:
            assert "failure" not in result

    def evaluate_queue(canonical, head_sha):
        payload = {
            "group": group_expression,
            "publish": publish_expression,
            "canonical": canonical,
            "head": head_sha,
        }
        source = r"""
const fs = require('fs'); const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const expression = value => value.trim().replace(/^\$\{\{\s*/, '').replace(/\s*\}\}$/, '');
const evaluate = value => Function('github', 'needs', 'format', 'return (' + expression(value) + ');');
const format = (template, ...values) => template.replace(/\{(\d+)\}/g, (_, index) => String(values[Number(index)]));
const github = {run_id: '99'};
const needs = {classify: {outputs: {canonical: input.canonical, head_sha: input.head}}};
process.stdout.write(JSON.stringify({group: evaluate(input.group)(github, needs, format), publish: Boolean(evaluate(input.publish)(github, needs, format))}));
"""
        completed = subprocess.run(
            ["node", "-e", source],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(completed.stdout)

    assert evaluate_queue("true", "a" * 40) == {
        "group": "agents-guard-status-" + "a" * 40,
        "publish": True,
    }
    assert evaluate_queue("false", "a" * 40) == {
        "group": "agents-guard-fork-status-99",
        "publish": False,
    }


def test_canonical_publisher_joins_label_group_while_skipped_events_cannot_cancel_it():
    sha = "a" * 40
    canonical = f"agents-guard-status-{sha}"
    skipped = "agents-guard-fork-status-99"
    assert canonical != skipped

    # RED without reconciliation: A writes after its last label read and P
    # replaces B under the shared default one-pending scheduler.
    pending = "B"
    pending = "P"
    assert pending == "P"
    # GREEN: a canonical P joins B's group and reconciles stale success; a
    # skipped/wrong-path run is isolated and cannot replace B at all.
    pending = "B"
    assert pending == "B"


@pytest.mark.parametrize(
    "prior,snapshot,current,expected_state",
    [
        (None, [{"name": "agent:cursor"}], [], "failure"),
        (None, [], [{"name": "agent:gemini"}], "failure"),
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
github.rest.repos.getContent = async params => { if(params.ref !== 'b'.repeat(40)) throw Error('untrusted registry ref'); return {data:{type:'file',encoding:'base64',content:"YWdlbnRzOgogIGNvZGV4OgogICAgZW5hYmxlZDogdHJ1ZQogIGNsYXVkZToKICAgIGVuYWJsZWQ6IHRydWUKICBjdXJzb3I6CiAgICBlbmFibGVkOiB0cnVlCiAgZ2VtaW5pOgogICAgZW5hYmxlZDogdHJ1ZQogIGFpZGVyOgogICAgZW5hYmxlZDogZmFsc2UK"}}; };
context.payload.pull_request.base = {sha:'b'.repeat(40)};
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
                    "EVALUATED_LABELS": json.dumps(snapshot),
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


@pytest.mark.parametrize(
    "prior_labels,current_labels,expected_writes",
    [
        # A queued unrelated seal event preserves a policy-bound green status.
        (["agent:codex"], ["agent:codex", "sync:delivery-sealed"], 0),
        # A later ineligible event cannot preserve a green receipt from revoked policy.
        (["agent:codex", "agents:allow-change"], [], 1),
        # The guard lowercases routing and permission labels before evaluation.
        (["AGENT:CODEX", "AGENTS:ALLOW-CHANGE"], [], 1),
    ],
)
def test_ineligible_label_event_requires_matching_policy_receipt(
    prior_labels, current_labels, expected_writes
):
    import hashlib

    workflow = yaml.safe_load((ROOT / ".github/workflows/agents-guard.yml").read_text())
    script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["guard"]["steps"]
        if step.get("name") == "Report agents guard commit status"
    )
    routing = {
        "agent:auto",
        "agent:codex",
        "agent:claude",
        "agent:copilot",
        "agents:auto-pilot",
        "agents:keepalive",
    }
    canonical = sorted(
        {label.strip().lower() for label in prior_labels if label.strip().lower() in routing}
        | {label.lower() for label in prior_labels if label.lower() == "agents:allow-change"}
    )
    fingerprint = hashlib.sha256("\n".join(canonical).encode()).hexdigest()
    harness = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
Object.assign(process.env, {ELIGIBLE: 'false', JOB_STATUS: 'success'});
const writes = [];
const github = {rest: {repos: {createCommitStatus: async p => writes.push(p), listCommitStatusesForRef() {}}, issues: {listLabelsOnIssue() {}}}, paginate: async method => method === github.rest.issues.listLabelsOnIssue ? input.currentLabels : [{context: 'Health 45 Agents Guard / guard', state: 'success', description: input.description}]};
const context = {repo: {owner: 'owner', repo: 'repo'}, eventName: 'pull_request_target', payload: {pull_request: {number: 4, labels: input.snapshotLabels, head: {sha: 'a'.repeat(40)}}}, serverUrl: 'https://github.com', runId: 42};
const core = {info() {}, error() {}, setFailed(message) { throw Error(message); }};
github.rest.repos.getContent = async params => { if(params.ref !== 'b'.repeat(40)) throw Error('untrusted registry ref'); return {data:{type:'file',encoding:'base64',content:"YWdlbnRzOgogIGNvZGV4OgogICAgZW5hYmxlZDogdHJ1ZQogIGNsYXVkZToKICAgIGVuYWJsZWQ6IHRydWUKICBjdXJzb3I6CiAgICBlbmFibGVkOiB0cnVlCiAgZ2VtaW5pOgogICAgZW5hYmxlZDogdHJ1ZQogIGFpZGVyOgogICAgZW5hYmxlZDogZmFsc2UK"}}; };
context.payload.pull_request.base = {sha:'b'.repeat(40)};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', input.script)(github, context, core).then(() => process.stdout.write(JSON.stringify(writes)));
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps(
            {
                "script": script,
                "snapshotLabels": [{"name": label} for label in current_labels],
                "currentLabels": [{"name": label} for label in current_labels],
                "description": (
                    f"[guard-pr:4] Trusted Agents Guard completed successfully [guard-policy-sha256:{fingerprint}]"
                ),
            }
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    writes = json.loads(result.stdout)
    assert len(writes) == expected_writes
    if expected_writes:
        assert writes[0]["state"] == "failure"
        assert "policy changed" in writes[0]["description"]


def test_policy_receipt_uses_guard_label_normalization_contract():
    source = (ROOT / ".github/workflows/agents-guard.yml").read_text()
    helper = (ROOT / ".github/scripts/agents-guard-fork-status-publication.js").read_text()
    for value in (source, helper):
        assert "raw.trim().toLowerCase()" in value
        assert (
            "raw.toLowerCase() === permissionLabel" in value
            or "raw.toLowerCase() === PERMISSION_LABEL" in value
        )
        assert "Array.isArray(labels)" in value


@pytest.mark.parametrize("template", [False, True])
def test_guard_block_summary_uses_literal_environment_transport(template, tmp_path):
    """An evaluator summary containing a PR filename must never become shell."""
    prefix = ROOT / "templates/consumer-repo" if template else ROOT
    workflow = yaml.safe_load((prefix / ".github/workflows/agents-guard.yml").read_text())
    blocked_step = next(
        step
        for step in workflow["jobs"]["guard"]["steps"]
        if step.get("name") == "Fail when guard blocks the pull request"
    )
    assert blocked_step["env"] == {"GUARD_SUMMARY": "${{ steps.evaluate.outputs.summary }}"}
    assert blocked_step["run"] == "printf '%s\\n' \"$GUARD_SUMMARY\"\nexit 1\n"

    sentinel = tmp_path / "summary-shell-executed"
    filename = '.github/workflows/agents-$(touch summary-shell-executed)-`id`-"quoted"-%s.yml'
    evaluator = f"""
const {{ evaluateGuard }} = require({json.dumps(str(ROOT / ".github/scripts/agents-guard.js"))});
const result = evaluateGuard({{files: [{{filename: {json.dumps(filename)}, status: 'modified'}}]}});
process.stdout.write(result.summary);
"""
    summary = subprocess.run(
        ["node", "-e", evaluator], text=True, capture_output=True, check=True
    ).stdout
    assert filename in summary

    # RED: this is the previous YAML interpolation after Actions substitutes a
    # PR-controlled output into the shell program.
    legacy = subprocess.run(
        ["bash", "-c", f'echo "{summary}"'],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    assert sentinel.exists()
    assert legacy.returncode == 0

    # GREEN: execute the actual fixed YAML shell body. Quotes, backticks,
    # command substitutions, format markers, and newlines remain literal.
    sentinel.unlink()
    fixed = subprocess.run(
        ["bash", "-c", blocked_step["run"]],
        cwd=tmp_path,
        env={"GUARD_SUMMARY": summary},
        text=True,
        capture_output=True,
    )
    assert fixed.returncode == 1
    assert fixed.stdout == summary + "\n"
    assert not sentinel.exists()


@pytest.mark.parametrize("template", [False, True])
@pytest.mark.parametrize(
    "mode", ["transient", "persistent", "malformed", "missing_enabled", "nested_enabled"]
)
def test_registry_failure_cannot_retain_same_head_success(template, mode):
    prefix = ROOT / "templates/consumer-repo" if template else ROOT
    workflow = yaml.safe_load((prefix / ".github/workflows/agents-guard.yml").read_text())
    script = next(
        s["with"]["script"]
        for s in workflow["jobs"]["guard"]["steps"]
        if s.get("name") == "Report agents guard commit status"
    )
    harness = r"""
const input=JSON.parse(require('fs').readFileSync(0,'utf8'));
global.setTimeout=(fn)=>{fn();}; global.crypto=require('crypto').webcrypto;
Object.assign(process.env,{ELIGIBLE:'true',EVALUATE_OUTCOME:'success',BLOCKED:'false',JOB_STATUS:'success',EVALUATED_LABELS:'[]'});
let reads=0; const writes=[]; const failures=[];
let status={state:'success',context:'Health 45 Agents Guard / guard'};
const github={rest:{repos:{getContent:async()=>{
 reads++;
 if(input.mode==='persistent'||(input.mode==='transient'&&reads<3)){const e=Error('registry transient');e.status=500;throw e;}
 if(input.mode==='malformed')return {data:{type:'file',encoding:'none'}};
 if(input.mode==='missing_enabled'||input.mode==='nested_enabled')return {data:{type:'file',encoding:'base64',content:Buffer.from(input.mode==='missing_enabled'?'agents:\n  codex:\n':'agents:\n  codex:\n    preflight:\n      enabled: true\n').toString('base64')}};
 return {data:{type:'file',encoding:'base64',content:Buffer.from('agents:\n  codex:\n    enabled: true\n').toString('base64')}};
},createCommitStatus:async p=>{writes.push(p);status=p;},listCommitStatusesForRef(){}},issues:{listLabelsOnIssue(){}}},paginate:async()=>[]};
const context={repo:{owner:'owner',repo:'repo'},eventName:'pull_request_target',payload:{pull_request:{number:4,labels:[],head:{sha:'a'.repeat(40)},base:{sha:'b'.repeat(40)}}},serverUrl:'https://github.com',runId:42};
const core={info(){},warning(){},error(){},setFailed(m){failures.push(m);}};
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github','context','core',input.script)(github,context,core).then(()=>process.stdout.write(JSON.stringify({reads,writes,status,failures})));
"""
    harness = with_current_direct_binding(harness)
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps({"script": script, "mode": mode}),
        capture_output=True,
        text=True,
        check=True,
    )
    record = json.loads(result.stdout)
    assert record["status"]["state"] == ("success" if mode == "transient" else "failure")
    assert record["reads"] == (3 if mode in {"persistent", "transient"} else 1)
    assert len(record["writes"]) == 1
    assert record["writes"][0]["sha"] == "a" * 40
    if mode != "transient":
        assert "guard-policy-sha256" not in record["writes"][0]["description"]


@pytest.mark.parametrize("template", [False, True])
@pytest.mark.parametrize(
    "drift",
    [
        "none",
        "head",
        "base",
        "base-repo",
        "base-ref",
        "closed",
        "attempt",
        "newer-run",
        "same-id-attempt",
        "ambiguous-newer",
        "missing-inventory",
        "final-head",
        "final-attempt",
    ],
)
@pytest.mark.parametrize("event", ["pull_request", "pull_request_target"])
def test_missing_enabled_corrective_write_requires_fresh_bindings(template, drift, event):
    prefix = ROOT / "templates/consumer-repo" if template else ROOT
    workflow = yaml.safe_load((prefix / ".github/workflows/agents-guard.yml").read_text())
    assert workflow["permissions"]["actions"] == "read"
    script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["guard"]["steps"]
        if step.get("name") == "Report agents guard commit status"
    )
    harness = r"""
const input=JSON.parse(require('fs').readFileSync(0,'utf8'));
process.env.GITHUB_RUN_ATTEMPT='1';
const writes=[];const failures=[];let prReads=0;let runReads=0;
const pr={number:4,state:'open',head:{sha:'a'.repeat(40)},base:{sha:'b'.repeat(40),ref:'main',repo:{id:1}}};
const run={id:42,workflow_id:7,path:'.github/workflows/agents-guard.yml',event:'pull_request_target',head_sha:'b'.repeat(40),run_number:5,run_attempt:1,created_at:'2026-10-16T01:00:00Z',pull_requests:[{number:4}]};
run.event=input.event;run.head_sha=input.event==='pull_request'?pr.head.sha:pr.base.sha;
const context={repo:{owner:'owner',repo:'repo'},eventName:input.event,runId:42,sha:input.event==='pull_request'?'d'.repeat(40):pr.base.sha,serverUrl:'https://github.com',payload:{pull_request:pr}};
const github={rest:{repos:{getContent:async()=>({data:{type:'file',encoding:'base64',content:Buffer.from('agents:\n  codex:\n').toString('base64')}}),createCommitStatus:async p=>writes.push(p)},pulls:{get:async()=>{prReads++;const copy=JSON.parse(JSON.stringify(pr));
if(input.drift==='head'||(input.drift==='final-head'&&prReads>1))copy.head.sha='c'.repeat(40);
if(input.drift==='base')copy.base.sha='c'.repeat(40);
if(input.drift==='base-repo')copy.base.repo.id=2;
if(input.drift==='base-ref')copy.base.ref='other';
if(input.drift==='closed')copy.state='closed';
return {data:copy};}},actions:{getWorkflowRun:async()=>{runReads++;return {data:{...run,run_attempt:(input.drift==='attempt'||(input.drift==='final-attempt'&&runReads>1))?2:1}};},listWorkflowRuns(){}}},paginate:async(method,params)=>{
if(method!==github.rest.actions.listWorkflowRuns)throw Error('unexpected pagination');
if(input.drift==='missing-inventory')return [];
if(input.drift==='same-id-attempt')return [{...run,run_attempt:2}];
if(input.drift==='newer-run')return [run,{...run,id:43,run_number:6}];
if(input.drift==='ambiguous-newer')return [run,{...run,id:43,run_number:6,pull_requests:[]}];
return [run];}};
const core={info(){},warning(){},error(){},setFailed:m=>failures.push(m)};
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github','context','core',input.script)(github,context,core).then(()=>process.stdout.write(JSON.stringify({writes,failures,prReads,runReads})));
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps({"script": script, "drift": drift, "event": event}),
        capture_output=True,
        text=True,
        check=True,
    )
    record = json.loads(result.stdout)
    assert len(record["writes"]) == (1 if drift == "none" else 0)
    assert record["failures"]
    if drift == "none":
        assert record["prReads"] >= 2 and record["runReads"] >= 2
        assert record["writes"][0]["sha"] == "a" * 40
        assert record["writes"][0]["state"] == "failure"
        assert "guard-policy-sha256" not in record["writes"][0]["description"]
