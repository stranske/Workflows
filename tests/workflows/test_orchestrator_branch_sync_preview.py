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
  pulls: readOnly({get: async (args) => {
    assert.deepEqual(args, {owner:'stranske', repo:'Workflows', pull_number:4937});
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


def branch_job():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["dry-run-branch-sync"]


def test_dry_run_branch_job_uses_read_only_authority():
    job = branch_job()
    assert job["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert "inputs.dry_run == 'true'" in job["if"]
    assert "needs.belt-dispatch.outputs.dry_run == 'true'" in job["if"]
    assert [step["uses"] for step in job["steps"] if "uses" in step] == ["actions/github-script@v9"]
    assert job["steps"][0]["with"]["github-token"] == "${{ github.token }}"
    assert job["steps"][1]["if"] == "always()"


@pytest.mark.parametrize(
    ("case", "expected", "reads"),
    [
        ("behind", "would-require-sync", 3),
        ("current", "already-up-to-date", 3),
        ("fork", "would-require-sync", 3),
        ("moved-before", "unknown", 1),
        ("moved-during", "unknown", 3),
        ("base-moved-during", "unknown", 3),
        ("missing-expected-head", "unknown", 0),
        ("fork-missing-repo", "unknown", 1),
        ("closed", "unknown", 1),
        ("comparison-unavailable", "unknown", 2),
        ("unbound-comparison", "unknown", 2),
    ],
)
def test_authored_branch_preview_readback(case, expected, reads, tmp_path):
    expected_repo = "contributor/Workflows" if case.startswith("fork") else "stranske/Workflows"
    head = {"ref": HEAD_REF, "sha": HEAD, "repo": {"full_name": expected_repo}}
    base = {"ref": "main", "sha": BASE, "repo": {"full_name": "stranske/Workflows"}}

    def pull(*, head=head, base=base, state="open"):
        return {"number": 4937, "state": state, "head": head, "base": base}

    first = pull()
    second = first
    if case == "moved-before":
        first = pull(head={**head, "sha": ANCESTOR})
    elif case == "moved-during":
        second = pull(head={**head, "sha": ANCESTOR})
    elif case == "base-moved-during":
        second = pull(base={**base, "sha": ANCESTOR})
    elif case == "fork-missing-repo":
        first = pull(head={**head, "repo": None})
    elif case == "closed":
        first = pull(state="closed")

    fixture = {
        "script": branch_job()["steps"][0]["with"]["script"],
        "pulls": [first, second],
        "basehead": f"{BASE}...{HEAD}",
        "compareError": case == "comparison-unavailable",
        "comparison": {
            "base_commit": {"sha": ANCESTOR if case == "unbound-comparison" else BASE},
            "merge_base_commit": {"sha": BASE if case == "current" else ANCESTOR},
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
            "PR_NUMBER": "4937",
            "BASE_REF": "main",
            "HEAD_REF": HEAD_REF,
            "HEAD_SHA": "" if case == "missing-expected-head" else HEAD,
            "HEAD_REPO": expected_repo,
        },
    )
    reply = json.loads(result.stdout)
    assert reply["forbidden"] == []
    assert len(reply["reads"]) == reads
    assert reply["outputs"]["result"] == expected
    assert bool(reply["errors"]) == (expected == "unknown")
    if reads:
        assert reply["outputs"]["pr_url"] == "https://github.com/stranske/Workflows/pull/4937"
        assert reply["outputs"]["observed_head"] == (
            ANCESTOR if case in {"moved-before", "moved-during"} else HEAD
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
