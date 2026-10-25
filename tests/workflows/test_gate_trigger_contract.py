"""Prevent label churn from restarting Gate while commits still supersede runs.

Root and consumer-template Gate workflows must omit pull_request label activity
types (`labeled` / `unlabeled`). Agent routing labels must not start or cancel
Gate; new commits (`synchronize`) still supersede in-flight runs.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GATE_FILES = (
    ".github/workflows/pr-00-gate.yml",
    "templates/consumer-repo/.github/workflows/pr-00-gate.yml",
)
# Exact allowlist: label activity types are intentionally excluded (#3977 / #3983).
ALLOWED_PULL_REQUEST_TYPES = (
    "opened",
    "synchronize",
    "reopened",
    "ready_for_review",
)
FORBIDDEN_LABEL_TYPES = ("labeled", "unlabeled")


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_gate_trigger_contract(workflow_path: str) -> None:
    workflow = yaml.safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    # PyYAML's YAML 1.1 resolver reads the Actions key `on` as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    types = triggers["pull_request"]["types"]

    for label_type in FORBIDDEN_LABEL_TYPES:
        assert label_type not in types, f"{workflow_path}: labels must not restart Gate"
    assert "opened" in types, f"{workflow_path}: new PRs must start Gate"
    assert "synchronize" in types, f"{workflow_path}: new commits must start Gate"
    assert "reopened" in types, f"{workflow_path}: reopened PRs must start Gate"
    assert "ready_for_review" in types, f"{workflow_path}: PRs ready for review must start Gate"
    # Catch extras (e.g. edited) after required-type checks so regressions keep
    # their specific diagnostics.
    assert list(types) == list(
        ALLOWED_PULL_REQUEST_TYPES
    ), f"{workflow_path}: unexpected pull_request types {types!r}"
    assert workflow["concurrency"]["cancel-in-progress"] == (
        "${{ github.event_name != 'workflow_dispatch' }}"
    ), f"{workflow_path}: new commits must still supersede in-flight runs"


@pytest.mark.parametrize("workflow_path", GATE_FILES)
@pytest.mark.parametrize(
    ("activity", "diagnostic"),
    (
        ("labeled", "labels must not restart Gate"),
        ("unlabeled", "labels must not restart Gate"),
        ("opened", "new PRs must start Gate"),
        ("synchronize", "new commits must start Gate"),
        ("reopened", "reopened PRs must start Gate"),
        ("ready_for_review", "PRs ready for review must start Gate"),
    ),
)
def test_gate_trigger_contract_rejects_regressions(
    workflow_path: str, activity: str, diagnostic: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove the contract detects broken triggers without editing workflow files."""
    target = ROOT / workflow_path
    read_text = Path.read_text
    workflow = yaml.safe_load(target.read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    types = triggers["pull_request"]["types"]
    if activity in FORBIDDEN_LABEL_TYPES:
        types.append(activity)
    else:
        types.remove(activity)
    broken_workflow = yaml.safe_dump(workflow)

    def read_workflow(path: Path, *args, **kwargs) -> str:
        if path == target:
            return broken_workflow
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_workflow)
    with pytest.raises(AssertionError, match=re.escape(f"{workflow_path}: {diagnostic}")):
        test_gate_trigger_contract(workflow_path)


def test_gate_triggers_match_template() -> None:
    workflows = [yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) for path in GATE_FILES]
    triggers = [workflow.get("on", workflow.get(True)) for workflow in workflows]
    assert triggers[0] == triggers[1], f"Gate triggers must agree across {GATE_FILES}"


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_dispatch_retains_pr_context_and_queues(workflow_path: str) -> None:
    workflow = yaml.safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["workflow_dispatch"]["inputs"]["pr_number"]["type"] == "string"
    assert "inputs.pr_number" in workflow["concurrency"]["group"]
    assert workflow["concurrency"]["cancel-in-progress"] == (
        "${{ github.event_name != 'workflow_dispatch' }}"
    )
    for name in ("issue-consistency", "test-quality"):
        assert "fromJSON(needs.resolve-pr.outputs.pull_request).number" in (
            workflow["jobs"][name]["if"]
        ), f"{workflow_path}: {name} must run for PR dispatches too"
    for name, job in workflow["jobs"].items():
        if name == "resolve-pr":
            continue
        assert "resolve-pr" in job["needs"], f"{workflow_path}: {name} needs resolved PR"
        if "steps" in job:
            assert job["env"]["GATE_PR_JSON"] == "${{ needs.resolve-pr.outputs.pull_request }}"
            assert job["steps"][0]["name"] == "Restore resolved PR event for Gate helpers"


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_dispatch_resolves_current_head_and_rejects_races(workflow_path: str) -> None:
    """Execute the actual workflow resolver against API fixtures, not a copy."""
    import json
    import subprocess

    workflow = yaml.safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    script = workflow["jobs"]["resolve-pr"]["steps"][0]["with"]["script"]
    harness = r"""
const assert = require('node:assert/strict');
const execute = new (Object.getPrototypeOf(async function(){}).constructor)(
  'github', 'context', 'core', SCRIPT);
(async () => {
  process.env.PR_NUMBER = '42';
  process.env.GITHUB_REPOSITORY = 'owner/repo';
  const pr = {number: 42, state: 'open', body: 'sealed body',
    head: {sha: 'current-head', repo: {full_name: 'owner/repo'}}};
  const context = {eventName: 'workflow_dispatch', sha: 'current-head',
    payload: {}, repo: {owner: 'owner', repo: 'repo'}};
  const github = {rest: {pulls: {get: async args => {
    assert.equal(args.pull_number, 42); return {data: pr};
  }}}};
  let output;
  const core = {setOutput: (name, value) => {output = JSON.parse(value);}};
  await execute(github, context, core);
  assert.deepEqual(output, pr);
  for (const change of [
    p => {p.head.sha = 'new-head';},
    p => {p.head.repo.full_name = 'fork/repo';},
    p => {p.state = 'closed';},
  ]) {
    const original = structuredClone(pr); change(pr);
    await assert.rejects(execute(github, context, core), /current open same-repository/);
    Object.assign(pr, original);
  }
  process.env.PR_NUMBER = 'oops';
  await assert.rejects(execute(github, context, core), /positive integer/);
  context.eventName = 'pull_request'; context.payload.pull_request = pr;
  await execute(github, context, core);
  assert.deepEqual(output, pr);
  context.eventName = 'workflow_dispatch'; context.payload = {};
  process.env.PR_NUMBER = '';
  await execute(github, context, core);
  assert.equal(output, null);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    result = subprocess.run(
        ["node", "-e", "const SCRIPT = " + json.dumps(script) + ";\n" + harness],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_dispatch_restores_event_for_seal_and_summary(workflow_path: str, tmp_path: Path) -> None:
    import json
    import subprocess

    workflow = yaml.safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    script = jobs["generated-delivery-seal"]["steps"][0]["with"]["script"]
    assert script == jobs["summary"]["steps"][0]["with"]["script"]
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"inputs": {"pr_number": "42"}}))
    pr = {"number": 42, "body": "fresh sealed body", "head": {"sha": "current-head"}}
    harness = (
        "process.env.GITHUB_EVENT_PATH = " + json.dumps(str(event_path)) + ";\n"
        "process.env.GATE_PR_JSON = " + json.dumps(json.dumps(pr)) + ";\n" + script
    )
    subprocess.run(["node", "-e", harness], check=True, capture_output=True, text=True)
    event = json.loads(event_path.read_text())
    assert event["pull_request"] == pr
    assert event["number"] == 42
    assert event["inputs"] == {"pr_number": "42"}


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_base_metadata_is_shell_data(workflow_path: str, tmp_path: Path) -> None:
    """Execute base-ref commands with shell metacharacters in API metadata."""
    import os
    import subprocess

    workflow = yaml.safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    marker = tmp_path / "injected"
    hostile = f"topic/$(touch${{IFS}}{marker})"
    seen = set()
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") not in {
                "Fetch base ref",
                "Check test quality and secret diff",
                "Check deliberate-break acceptance criterion",
            }:
                continue
            seen.add(step["name"])
            script = step["run"]
            assert "${{" not in script, f"{workflow_path}: metadata must not become shell source"
            assert step["env"]["GATE_BASE_REF"] == (
                "${{ fromJSON(needs.resolve-pr.outputs.pull_request).base.ref }}"
            )
            # Replace network/checker commands with argument recorders, retaining
            # the actual workflow shell code and quoting under test.
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'git() { printf "%s\\n" "$@"; }; python() { printf "%s\\n" "$@"; };\n' + script,
                ],
                env={**os.environ, "GATE_BASE_REF": hostile, "GATE_BASE_REPO": hostile},
                capture_output=True,
                text=True,
                check=True,
            )
            assert hostile in result.stdout
            assert not marker.exists(), f"{workflow_path}: API metadata executed as shell code"
    assert "Fetch base ref" in seen
    assert "Check deliberate-break acceptance criterion" in seen


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_pr_rerun_refreshes_same_head_metadata(workflow_path: str) -> None:
    """Execute the authored resolver: reruns retain the old event body."""
    import json
    import subprocess

    workflow = yaml.safe_load((ROOT / workflow_path).read_text())
    script = workflow["jobs"]["resolve-pr"]["steps"][0]["with"]["script"]
    harness = r"""
const assert = require('node:assert/strict');
const execute = new (Object.getPrototypeOf(async function(){}).constructor)(
  'github', 'context', 'core', SCRIPT);
(async () => {
  process.env.PR_NUMBER = '';
  process.env.GITHUB_REPOSITORY = 'owner/repo';
  const original = {number:42,state:'open',body:'staging',
    head:{sha:'same-head',repo:{full_name:'owner/repo'}}};
  const fresh = structuredClone(original); fresh.body='sealed';
  const context = {eventName:'pull_request',sha:'synthetic-merge',
    repo:{owner:'owner',repo:'repo'},payload:{pull_request:original}};
  let reads=0; let output;
  const github={rest:{pulls:{get:async args=>{
    reads++; assert.deepEqual(args,{owner:'owner',repo:'repo',pull_number:42});
    return {data:structuredClone(fresh)};
  }}}};
  const core={setOutput:(_name,value)=>{output=JSON.parse(value);}};
  await execute(github,context,core);
  assert.equal(reads,1); assert.equal(output.body,'sealed');
  assert.equal(original.body,'staging');
  for (const mutate of [
    p=>{p.head.sha='changed-head';},
    p=>{p.head.repo.full_name='foreign/repo';},
    p=>{p.state='closed';},
  ]) {
    const saved=structuredClone(fresh); mutate(fresh); output=undefined;
    await assert.rejects(execute(github,context,core));
    assert.equal(output,undefined); Object.assign(fresh,saved);
  }
  // Ordinary fork PRs retain their read-only identity; dispatch is stricter.
  original.head.repo.full_name='fork/repo'; fresh.head.repo.full_name='fork/repo';
  await execute(github,context,core); assert.equal(output.body,'sealed');
  github.rest.pulls.get=async()=>{throw Error('metadata unavailable');};
  output=undefined; await assert.rejects(execute(github,context,core),/metadata unavailable/);
  assert.equal(output,undefined);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        ["node", "-e", "const SCRIPT = " + json.dumps(script) + ";\n" + harness],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_resolved_snapshot_drives_both_delivery_guards(workflow_path: str, tmp_path: Path) -> None:
    """Authored resolver/restore plus actual classifier/seal validate one snapshot."""
    import json
    import subprocess

    workflow = yaml.safe_load((ROOT / workflow_path).read_text())
    jobs = workflow["jobs"]
    scripts = {
        "resolve": jobs["resolve-pr"]["steps"][0]["with"]["script"],
        "restore": [
            jobs[name]["steps"][0]["with"]["script"]
            for name in ("detect", "generated-delivery-seal")
        ],
    }
    for name in ("detect", "generated-delivery-seal"):
        assert "needs.resolve-pr.outputs.pull_request" in jobs[name]["steps"][0]["if"]
        assert "workflow_dispatch" not in jobs[name]["steps"][0]["if"]
    harness = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const classifier=require(path.join(ROOT,'.github/actions/path-classifier/classify.js'));
const seal=require(path.join(ROOT,'.github/actions/generated-delivery-seal/check.js'));
const contract=require(path.join(ROOT,'.github/scripts/sync_pr_lease_contract.js'));
const execute=new(Object.getPrototypeOf(async function(){}).constructor)(
 'github','context','core',SCRIPTS.resolve);
(async()=>{
 const now='2026-10-25T14:40:00Z',repo='owner/repo',sha='a'.repeat(40);
 const record={durable_issue_url:'https://github.com/owner/Workflows/issues/1',
  plan_id:'sha256:'+'b'.repeat(64),generation:'bbbbbbbbbbbb',repository:repo,
  desired_tree_hash:'c'.repeat(40),source_commit:'d'.repeat(40),
  head_observed_sha:sha,head_observed_at:'2026-10-25T14:30:00Z',
  lease_expires_at:'2026-10-28T14:30:00Z',delivery_state:'staging'};
 const pr={number:42,state:'open',head:{ref:'sync/workflows-candidate',sha,
  repo:{full_name:repo}},base:{repo:{full_name:repo}},body:contract.formatDeliveryRecord(record)};
 const original=structuredClone(pr),fresh=structuredClone(pr);
 fresh.body=contract.formatDeliveryRecord({...record,delivery_state:'sealed',
  review_started_at:'2026-10-25T14:31:00Z',sealed_at:'2026-10-25T14:31:00Z',sealed_head_sha:sha});
 const ctx={event_name:'pull_request',repository:repo,event:{pull_request:original}};
 assert.equal(seal.evaluateDeliverySeal(ctx.event,repo,now).valid,false);
 assert.equal(classifier.stableDeliverySealStatus(ctx,{contract,now}).valid,false);
 process.env.GITHUB_REPOSITORY=repo;process.env.PR_NUMBER='';
 const github={rest:{pulls:{get:async()=>({data:fresh})}}};
 let output;const core={setOutput:(_n,v)=>{output=v;}};
 await execute(github,{eventName:'pull_request',payload:ctx.event,
  repo:{owner:'owner',repo:'repo'},sha:'merge-sha'},core);
 process.env.GATE_PR_JSON=output;process.env.GITHUB_CONTEXT_JSON=JSON.stringify(ctx);
 for (let i=0;i<SCRIPTS.restore.length;i++) {
  process.env.GITHUB_EVENT_PATH=path.join(TEMP,'event-'+i+'.json');
  fs.writeFileSync(process.env.GITHUB_EVENT_PATH,JSON.stringify(ctx.event));
  new Function('require',SCRIPTS.restore[i])(require);
  const restored=JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH,'utf8'));
  const parsed=classifier.parseGithubContext();
  assert.deepEqual(restored.pull_request,parsed.event.pull_request);
  assert.equal(seal.evaluateDeliverySeal(restored,repo,now).valid,true);
  assert.equal(classifier.stableDeliverySealStatus(parsed,{contract,now}).valid,true);
 }
 for (const mutate of [
  p=>{p.number=43;},p=>{p.head.sha='changed';},
  p=>{p.head.repo.full_name='foreign/repo';},p=>{p.state='closed';},
 ]) {
  const wrong=structuredClone(fresh);mutate(wrong);process.env.GATE_PR_JSON=JSON.stringify(wrong);
  assert.throws(()=>classifier.parseGithubContext());
 }
 process.env.GATE_PR_JSON='{broken';assert.throws(()=>classifier.parseGithubContext());
 // No resolved snapshot retains normal pre-seal refusal; it does not waive it.
 delete process.env.GATE_PR_JSON;
 assert.equal(classifier.stableDeliverySealStatus(classifier.parseGithubContext(),{contract,now}).valid,false);
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    prefix = (
        "const ROOT="
        + json.dumps(str(ROOT))
        + ";const TEMP="
        + json.dumps(str(tmp_path))
        + ";const SCRIPTS="
        + json.dumps(scripts)
        + ";\n"
    )
    result = subprocess.run(["node", "-e", prefix + harness], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
