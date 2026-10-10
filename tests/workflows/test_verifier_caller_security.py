"""Exercise the post-merge caller trust boundary against production YAML."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CALLERS = [
    ".github/workflows/agents-verifier.yml",
    "templates/consumer-repo/.github/workflows/agents-verifier.yml",
]
REUSABLE = ".github/workflows/reusable-agents-verifier.yml"
VERIFIER_PERMISSIONS = {
    "contents": "read",
    "pull-requests": "write",
    "issues": "read",
    "actions": "read",
    "models": "read",
}
SECRET_MAPPING = {
    name: "${{ secrets." + name + " }}"
    for name in ["CODEX_AUTH_JSON", "OPENAI_API_KEY", "CLAUDE_API_STRANSKE", "LANGSMITH_API_KEY"]
} | {
    "workflows_app_id": "${{ secrets.WORKFLOWS_APP_ID }}",
    "workflows_app_private_key": "${{ secrets.WORKFLOWS_APP_PRIVATE_KEY }}",
}


def workflow(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text())


def step(path: str, job: str, name: str) -> dict:
    return next(s for s in workflow(path)["jobs"][job]["steps"] if s.get("name") == name)


@pytest.mark.parametrize("path", CALLERS)
def test_secret_allowlist_matches_declared_contract(path: str) -> None:
    declared = workflow(REUSABLE)[True]["workflow_call"]["secrets"]
    assert set(SECRET_MAPPING) == set(declared)
    assert workflow(path)["jobs"]["verifier"]["secrets"] == SECRET_MAPPING
    # The gate must not elevate its read-only token through PAT/App rotation.
    assert step(path, "check", "Setup API client")["with"] == {
        "github_token": "${{ github.token }}"
    }


@pytest.mark.parametrize("path", CALLERS + [REUSABLE])
def test_job_scoped_permissions(path: str) -> None:
    data = workflow(path)
    assert data["permissions"] == {}
    assert data["jobs"]["verifier"]["permissions"] == VERIFIER_PERMISSIONS
    if path in CALLERS:
        assert data["jobs"]["check"]["permissions"] == {
            "contents": "read",
            "pull-requests": "read",
        }
    if "persist-fingerprint" in data["jobs"]:
        assert data["jobs"]["persist-fingerprint"]["permissions"] == {
            "contents": "read",
            "pull-requests": "write",
        }


@pytest.mark.parametrize("path", CALLERS + [REUSABLE])
def test_checkout_executes_trusted_source_without_credentials(path: str) -> None:
    checkouts = [
        s
        for job in workflow(path)["jobs"].values()
        for s in job.get("steps", [])
        if s.get("uses", "").startswith("actions/checkout@")
    ]
    assert checkouts
    for checkout in checkouts:
        options = checkout["with"]
        assert options["persist-credentials"] is False
        if options.get("repository") == "stranske/Workflows":
            assert options["ref"] == "${{ steps.workflows_ref.outputs.ref }}"
        else:
            assert options["ref"] == "${{ github.sha }}"
    if path == REUSABLE:
        options = step(path, "verifier", "Mint GitHub App token")["with"]
        assert options["repositories"] == "${{ github.event.repository.name }}"
        assert {k: v for k, v in options.items() if k.startswith("permission-")} == {
            "permission-contents": "read"
        }
        assert (
            step(path, "verifier", "Checkout Workflows scripts")["with"]["token"]
            == "${{ github.token }}"
        )


@pytest.mark.parametrize("path", CALLERS)
def test_trigger_gate_runs_before_any_checkout_or_secret(path: str) -> None:
    data = workflow(path)
    assert data[True]["pull_request_target"]["types"] == ["labeled"]
    expression = data["jobs"]["check"]["if"]
    # This Actions expression uses the JS-compatible boolean/property subset.
    # Evaluate the exact authored expression, including its exact-label allowlist.
    cases = [
        ("pull_request_target", False, "verify:compare", False),
        ("pull_request_target", True, "verify:create-issue", False),
        ("pull_request_target", True, "verify:compare-extra", False),
        ("pull_request_target", True, "unrelated", False),
        ("pull_request_target", True, "verify:checkbox", True),
        ("pull_request_target", True, "verify:evaluate", True),
        ("pull_request_target", True, "verify:compare", True),
        ("workflow_dispatch", False, "", True),
    ]
    for event, merged, label, expected in cases:
        for fork in [False, True]:
            github = {
                "event_name": event,
                "event": {
                    "pull_request": {"merged": merged, "head": {"repo": {"fork": fork}}},
                    "label": {"name": label},
                },
            }
            script = """
const [expression, github] = JSON.parse(process.argv[1]);
const result = Function('github', 'fromJSON', 'contains', 'return (' + expression + ')')(
  github, JSON.parse, (values, value) => values.includes(value));
process.stdout.write(JSON.stringify(result));
"""
            result = subprocess.run(
                ["node", "-e", script, json.dumps([expression, github])],
                check=True,
                capture_output=True,
                text=True,
            )
            assert json.loads(result.stdout) is expected
    text = (ROOT / path).read_text()
    assert text.count("zizmor: ignore[") == 1
    assert "pull_request_target: # zizmor: ignore[dangerous-triggers]" in text


@pytest.mark.parametrize("path", CALLERS)
@pytest.mark.parametrize("merged", [False, True])
def test_manual_dispatch_rechecks_merged_state(path: str, merged: bool) -> None:
    script = step(path, "check", "Check trigger conditions")["with"]["script"]
    harness = """
const [script, merged] = JSON.parse(process.argv[1]);
const outputs = {}, failures = [];
const core = {setOutput: (k,v) => outputs[k] = v, info: () => {},
              setFailed: msg => failures.push(msg)};
const context = {eventName: 'workflow_dispatch', repo: {owner: 'base', repo: 'repo'},
  payload: {inputs: {pr_number: '42', mode: 'compare', model: '', provider: 'auto'}}};
const github = {rest: {pulls: {get: async () => ({data: {merged}})}}};
const fakeRequire = name => {if (name === 'fs') return {existsSync: () => false};
                            throw Error('Unexpected module ' + name)};
(async () => {
  await (Object.getPrototypeOf(async function(){}).constructor)(
    'require','github','core','context',script)(fakeRequire,github,core,context);
  process.stdout.write(JSON.stringify({outputs, failures}));
})().catch(e => {console.error(e);process.exit(1)});
"""
    result = subprocess.run(
        ["node", "-e", harness, json.dumps([script, merged])],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(result.stdout)
    assert result["outputs"]["should_run"] == str(merged).lower()
    assert bool(result["failures"]) is not merged


def test_fingerprint_shell_treats_outputs_as_data(tmp_path: Path) -> None:
    path = CALLERS[1]
    report = step(path, "check", "Report unchanged state skip")
    persist = step(path, "persist-fingerprint", "Persist state fingerprint")
    assert report["env"]["FINGERPRINT_REASON"] == "${{ steps.fingerprint.outputs.reason }}"
    assert persist["env"]["FINGERPRINT_HASH"] == (
        "${{ needs.check.outputs.fingerprint_current_hash }}"
    )
    sentinel = tmp_path / "injected"
    payload = f'$(touch {sentinel}); `touch {sentinel}`; " untrusted'
    fake_python = tmp_path / "python"
    fake_python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    fake_python.chmod(0o755)
    env = os.environ | {
        "FINGERPRINT_REASON": payload,
        "FINGERPRINT_HASH": payload,
        "GITHUB_WORKFLOW": "Agents Verifier",
        "PATH": f"{tmp_path}:/usr/bin:/bin",
    }
    for item in [report, persist]:
        assert "${{" not in item["run"]
        result = subprocess.run(
            ["bash", "-eu", "-c", item["run"]], env=env, capture_output=True, text=True, check=True
        )
        assert payload in result.stdout
        assert not sentinel.exists()
    # Retain the consumer-only success-bound fingerprint persistence contract.
    assert (
        "needs.verifier.result == 'success'" in workflow(path)["jobs"]["persist-fingerprint"]["if"]
    )
