"""Exercise the authored dry-run branch preview with a read-only GitHub fixture."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-70-orchestrator-main.yml"

# Actual divergent source refs from Workflows PR #4937, confirmed by GitHub compare.
BASE = "1b496b2f9b17dedecfef322bbc325a1f1a573f88"
HEAD = "8fa2a0247fa0c27d4d5193303606bdbacc144e06"
ANCESTOR = "5fcd51d31705496c1d8d18d264dfce72767a1ba4"
HEAD_REF = "codex/defer-action-version-api-setup"

HARNESS = """
const fs = require('node:fs');
const assert = require('node:assert/strict');
const fixture = JSON.parse(fs.readFileSync(0, 'utf8'));
const outputs = {};
const errors = [];
const reads = [];
const forbidden = [];
const readOnly = target => new Proxy(target, {get(object, key) {
  if (Object.hasOwn(object, key)) return object[key];
  forbidden.push(String(key));
  throw new Error('Unexpected API access');
}});
const core = {setOutput: (k, v) => { outputs[k] = v; }, setFailed: m => errors.push(m)};
const context = {repo: {owner: 'stranske', repo: 'Workflows'}, serverUrl: 'https://github.com'};
const github = {rest: readOnly({
  git: readOnly({getRef: async (args) => {
    assert.deepEqual(args, {owner:'stranske', repo:'Workflows', ref: fixture.ref});
    const index = reads.filter(item => item === 'git.getRef').length;
    reads.push('git.getRef');
    const data = fixture.baseRefs[index];
    if (data === null) throw Object.assign(new Error('ref unavailable'), {status:404});
    return {data};
  }}),
  pulls: readOnly({get: async (args) => {
    assert.deepEqual(args, {owner:'stranske', repo:'Workflows', pull_number:fixture.prNumber});
    const index = reads.filter(item => item === 'pulls.get').length;
    reads.push('pulls.get');
    return {data: fixture.pulls[index]};
  }}),
  repos: readOnly({compareCommitsWithBasehead: async (args) => {
    assert.deepEqual(args, {owner:'stranske', repo:'Workflows',
      basehead: fixture.basehead, per_page:1});
    reads.push('repos.compareCommitsWithBasehead');
    if (fixture.compareError) throw Object.assign(new Error('unavailable'), {status:404});
    return {data: fixture.comparison};
  }}),
})};
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction('core', 'context', 'github', fixture.script)(core, context, github)
  .then(() => console.log(JSON.stringify({outputs, errors, reads, forbidden})))
  .catch(error => { console.error(error); process.exitCode = 1; });
"""


def workflow_jobs(path=WORKFLOW):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]


def branch_job():
    return workflow_jobs()["dry-run-branch-sync"]


def test_dry_run_branch_job_uses_read_only_authority():
    job = branch_job()
    assert job["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert "belt-worker" not in job["needs"]
    assert "!cancelled()" in job["if"]
    assert "needs.keepalive-prep.outputs.pr_number != ''" in job["if"]
    for snapshot_output in ("base_ref", "head_ref", "baseline_head"):
        assert f"needs.keepalive-prep.outputs.{snapshot_output}" not in job["if"]
    assert "inputs.dry_run == 'true'" in job["if"]
    assert "needs.belt-dispatch.outputs.dry_run == 'true'" in job["if"]
    assert [step["uses"] for step in job["steps"] if "uses" in step] == ["actions/github-script@v9"]
    assert job["steps"][0]["with"]["github-token"] == "${{ github.token }}"
    assert job["steps"][1]["if"] == "always()"


@pytest.mark.parametrize(
    ("case", "expected", "reads"),
    [
        ("behind", "would-require-sync", 5),
        ("current", "already-up-to-date", 5),
        ("fork", "would-require-sync", 5),
        ("stale-pr-base-4924", "would-require-sync", 5),
        ("unusual-refs", "would-require-sync", 5),
        ("moved-before", "unknown", 1),
        ("moved-during", "unknown", 4),
        ("base-moved-during", "unknown", 5),
        ("base-metadata-only-changed", "would-require-sync", 5),
        ("retargeted-during", "unknown", 4),
        ("base-missing", "unknown", 2),
        ("base-deleted-during", "unknown", 5),
        ("base-ref-mismatch", "unknown", 2),
        ("missing-expected-head", "unknown", 0),
        ("fork-missing-repo", "unknown", 1),
        ("missing-expected-repo", "unknown", 0),
        ("snapshot-unavailable", "unknown", 0),
        ("closed", "unknown", 1),
        ("comparison-unavailable", "unknown", 3),
        ("unbound-comparison", "unknown", 3),
    ],
)
def test_authored_branch_preview_readback(case, expected, reads, tmp_path):
    expected_repo = "contributor/Workflows" if case.startswith("fork") else "stranske/Workflows"
    pr_number, head_ref, head_sha = 4937, HEAD_REF, HEAD
    base_ref, live_base, pr_base, merge_base = "main", BASE, BASE, ANCESTOR
    if case == "stale-pr-base-4924":
        pr_number, head_ref = 4924, "docs/guard-required-contexts-guide"
        head_sha = "14cfc4af41067bacf09840f13956715c1fda57e5"
        live_base = "8c53ad22b3833a27187121fcd99e0d6a406a46f2"
        pr_base = merge_base = "0513e66b7c91cbac7dc99c5c7fa16fa0f748cccd"
    elif case == "unusual-refs":
        base_ref, head_ref = "release/2026.11+preview%candidate", "codex/évaluation/branch+name"
    elif case == "current":
        merge_base = live_base

    head = {"ref": head_ref, "sha": head_sha, "repo": {"full_name": expected_repo}}
    base = {"ref": base_ref, "sha": pr_base, "repo": {"full_name": "stranske/Workflows"}}
    first = {"number": pr_number, "state": "open", "head": head, "base": base}
    second = first
    ref = {"ref": f"refs/heads/{base_ref}", "object": {"type": "commit", "sha": live_base}}
    first_ref, second_ref = ref, ref
    if case == "moved-before":
        first = {**first, "head": {**head, "sha": ANCESTOR}}
    elif case == "moved-during":
        second = {**second, "head": {**head, "sha": ANCESTOR}}
    elif case == "base-moved-during":
        second_ref = {**ref, "object": {**ref["object"], "sha": ANCESTOR}}
    elif case == "base-metadata-only-changed":
        second = {**second, "base": {**base, "sha": ANCESTOR}}
    elif case == "retargeted-during":
        second = {**second, "base": {**base, "ref": "other-base"}}
    elif case == "base-missing":
        first_ref = None
    elif case == "base-deleted-during":
        second_ref = None
    elif case == "base-ref-mismatch":
        first_ref = {**ref, "ref": "refs/heads/different"}
    elif case == "fork-missing-repo":
        first = {**first, "head": {**head, "repo": None}}
    elif case == "closed":
        first = {**first, "state": "closed"}

    fixture = {
        "script": branch_job()["steps"][0]["with"]["script"],
        "pulls": [first, second],
        "prNumber": pr_number,
        "ref": f"heads/{base_ref}",
        "baseRefs": [first_ref, second_ref],
        "basehead": f"{live_base}...{head_sha}",
        "compareError": case == "comparison-unavailable",
        "comparison": {
            "base_commit": {"sha": ANCESTOR if case == "unbound-comparison" else live_base},
            "merge_base_commit": {"sha": merge_base},
        },
    }
    result = subprocess.run(
        ["node", "-e", HARNESS],
        input=json.dumps(fixture),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
        env={
            "PATH": os.environ["PATH"],
            "PR_NUMBER": str(pr_number),
            "BASE_REF": "" if case == "snapshot-unavailable" else base_ref,
            "HEAD_REF": "" if case == "snapshot-unavailable" else head_ref,
            "HEAD_SHA": (
                "" if case in {"missing-expected-head", "snapshot-unavailable"} else head_sha
            ),
            "HEAD_REPO": (
                "" if case in {"missing-expected-repo", "snapshot-unavailable"} else expected_repo
            ),
        },
    )
    reply = json.loads(result.stdout)
    assert reply["forbidden"] == []
    assert (
        reply["reads"]
        == [
            "pulls.get",
            "git.getRef",
            "repos.compareCommitsWithBasehead",
            "pulls.get",
            "git.getRef",
        ][:reads]
    )
    assert reply["outputs"]["result"] == expected
    assert bool(reply["errors"]) == (expected == "unknown")
    assert reply["outputs"]["pr_url"] == f"https://github.com/stranske/Workflows/pull/{pr_number}"
    if reads:
        assert reply["outputs"]["observed_head"] == (
            ANCESTOR if case in {"moved-before", "moved-during"} else head_sha
        )

    summary = tmp_path / "summary.md"
    subprocess.run(
        ["bash", "-c", branch_job()["steps"][1]["run"]],
        check=True,
        timeout=10,
        env={
            "PATH": os.environ["PATH"],
            "GITHUB_STEP_SUMMARY": str(summary),
            "ROUND": "3",
            "TRACE": "recorded-4937",
            "RESULT": reply["outputs"]["result"],
            "PR_URL": reply["outputs"].get("pr_url", ""),
            "OBSERVED_HEAD": reply["outputs"].get("observed_head", ""),
        },
    )
    rendered = summary.read_text()
    assert f"| 3 | `recorded-4937` | {expected} |" in rendered
    assert reply["outputs"].get("observed_head", "unknown") in rendered


def test_public_dry_run_guards_keepalive_snapshot_and_token_mints():
    jobs = workflow_jobs()
    init = workflow_jobs(WORKFLOW.with_name("reusable-70-orchestrator-init.yml"))
    for job in (
        *(
            jobs[name]
            for name in (
                "keepalive-guard",
                "keepalive-prep",
                "belt-dispatch-summary",
            )
        ),
    ):
        mint = next(step for step in job["steps"] if step.get("id") == "app_token")
        assert mint["if"] == "inputs.dry_run != 'true'"
    for step in init["token-preflight"]["steps"][:2]:
        assert step["if"] == "needs.rate-limit-check.outputs.dry_run == 'false'"
    for flow, job, mode in (
        (init, "rate-limit-check", "steps.dry_run.outputs.value"),
        (init, "idle-precheck", "needs.rate-limit-check.outputs.dry_run"),
        (jobs, "keepalive-guard", "inputs.dry_run"),
        (jobs, "belt-scan-ready-prs", "inputs.dry_run"),
    ):
        setup = next(step for step in flow[job]["steps"] if step.get("name") == "Setup API client")
        guard = "!= 'true'" if mode == "inputs.dry_run" else "== 'false'"
        assert setup["with"]["github_token"] == "${{ github.token }}"
        for name, expression in setup["with"].items():
            if name != "github_token":
                assert expression.startswith(f"${{{{ {mode} {guard} && secrets.")
    gate = next(step for step in jobs["keepalive-guard"]["steps"] if step.get("id") == "guard")
    assert gate["env"]["DRY_RUN"] == "${{ inputs.dry_run }}"
    assert "inputs.dry_run != 'true'" in gate["with"]["github-token"]
    snapshot = next(
        step
        for step in jobs["keepalive-prep"]["steps"]
        if step.get("name") == "Persist keepalive head snapshot"
    )
    assert snapshot["if"] == "inputs.dry_run != 'true' && steps.snapshot.outputs.head != ''"
    assert "inputs.dry_run != 'true'" in jobs["keepalive-post-work"]["if"]


@pytest.mark.parametrize(("dry_run", "should_post"), [("true", "false"), ("false", "true")])
def test_instruction_gate_respects_dry_run_even_when_post_work_reports_change(
    tmp_path,
    dry_run,
    should_post,
):
    gate = workflow_jobs()["keepalive-instruction"]["steps"][0]
    assert gate["id"] == "gate"
    output = tmp_path / "output"
    subprocess.run(
        ["bash", "-c", gate["run"]],
        env={
            "PATH": os.environ["PATH"],
            "GITHUB_OUTPUT": str(output),
            "GITHUB_ENV": str(tmp_path / "env"),
            "POST_WORK_RESULT": "success",
            "POST_WORK_SUCCESS": "true",
            "POST_WORK_CHANGED": "true",
            "DRY_RUN": dry_run,
        },
        check=True,
        timeout=10,
    )
    assert f"should_post={should_post}\n" in output.read_text()
    if dry_run == "true":
        assert "skip_reason=dry-run\n" in output.read_text()


@pytest.mark.parametrize("dry_run", ["true", "false"])
def test_worker_outcome_renders_summary_without_dry_run_pr_comment(dry_run):
    step = next(
        step
        for step in workflow_jobs()["belt-dispatch-summary"]["steps"]
        if step.get("name") == "Record keepalive worker outcome"
    )
    assert "inputs.dry_run == 'true'" in step["env"]["WORKER_DRY_RUN"]
    harness = """
const fs = require('node:fs');
const writes = [];
const summaries = [];
const summary = {
  addHeading(value) { summaries.push(value); return this; },
  addTable(rows) { summaries.push(rows); return this; },
  write() { return Promise.resolve(); },
};
const core = {summary, info() {}, warning(message) { throw Error(message); }};
const github = {rest: {issues: {async createComment(value) { writes.push(value); }}}};
const context = {repo: {owner:'stranske', repo:'Workflows'}};
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction('core', 'context', 'github', 'require', fs.readFileSync(0, 'utf8'))(
  core, context, github, require,
).then(() => console.log(JSON.stringify({writes, summaries})))
.catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=step["with"]["script"],
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
        cwd=ROOT,
        env={
            "PATH": os.environ["PATH"],
            "WORKER_DRY_RUN": dry_run,
            "KEEPALIVE_PR": "4937",
            "KEEPALIVE_TRACE": "recorded-4937",
            "KEEPALIVE_ROUND": "3",
            "WORKER_RESULT": "success",
            "KEEPALIVE_HEAD_SHA": HEAD,
        },
    )
    reply = json.loads(result.stdout)
    assert reply["summaries"][0] == "Keepalive worker outcome"
    assert reply["summaries"][1][1] == ["3", "recorded-4937", "success", HEAD]
    assert len(reply["writes"]) == (dry_run == "false")


@pytest.mark.parametrize(
    ("dry_run", "line"),
    [
        ("true", "WORKER PREVIEW: result=success pr=#4937 head=8fa2a02 trace=recorded-4937"),
        ("false", "WORKER: action=execute reason=new-instruction pr=#4937 head=8fa2a02"),
    ],
)
def test_worker_observability_distinguishes_preview_from_execution(tmp_path, dry_run, line):
    step = next(
        step
        for step in workflow_jobs()["belt-dispatch-summary"]["steps"]
        if step.get("name") == "Emit worker observability line"
    )
    summary = tmp_path / "worker.md"
    subprocess.run(
        ["bash", "-c", step["run"]],
        check=True,
        timeout=10,
        env={
            "PATH": os.environ["PATH"],
            "GITHUB_STEP_SUMMARY": str(summary),
            "PROCEED": "true",
            "CAP_OK": "true",
            "SHOULD_POST": "false" if dry_run == "true" else "true",
            "COMMENT_ID": "" if dry_run == "true" else "7351",
            "TRACE": "recorded-4937",
            "PR_NUMBER": "4937",
            "BASELINE_HEAD": HEAD,
            "WORKER_RESULT": "success",
            "INSTRUCTION_RESULT": "success",
            "DRY_RUN": dry_run,
        },
    )
    assert summary.read_text().startswith(line)


@pytest.mark.parametrize(
    ("input_mode", "params", "expected"),
    [
        ("  YES ", '{"dry_run": false}', "true"),
        ("y", "{}", "true"),
        ("1", "{}", "true"),
        ("off", '{"dry_run": true}', "false"),
        ("", '{"dry_run": true}', "true"),
        ("", "{unparseable", "false"),
    ],
)
def test_init_resolves_public_aliases_before_accessing_write_credentials(
    tmp_path,
    input_mode,
    params,
    expected,
):
    init = workflow_jobs(WORKFLOW.with_name("reusable-70-orchestrator-init.yml"))
    steps = init["rate-limit-check"]["steps"]
    normalize = next(step for step in steps if step.get("id") == "dry_run")
    setup = next(step for step in steps if step.get("name") == "Setup API client")
    assert steps.index(normalize) < steps.index(setup)
    output = tmp_path / "credential-mode"
    subprocess.run(
        ["bash", "-c", normalize["run"]],
        check=True,
        timeout=10,
        cwd=ROOT,
        env={
            "PATH": os.environ["PATH"],
            "GITHUB_OUTPUT": str(output),
            "WORKFLOW_DRY_RUN": input_mode,
            "PARAMS_JSON": params,
        },
    )
    assert output.read_text().strip() == f"value={expected}"


def test_dispatch_summary_keeps_preview_mode_when_worker_is_skipped():
    steps = workflow_jobs()["belt-dispatch-summary"]["steps"]
    append = next(step for step in steps if step.get("name") == "Append dispatch summary")
    record = next(step for step in steps if step.get("name") == "Record keepalive worker outcome")
    assert append["env"]["WORKER_DRY_RUN"] == record["env"]["WORKER_DRY_RUN"]
    assert append["env"]["WORKER_DRY_RUN"].startswith("${{ inputs.dry_run == 'true' && 'true' ||")
