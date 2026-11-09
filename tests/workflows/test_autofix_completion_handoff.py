"""The autofix metrics job must finish the reservation made by prepare."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from scripts.runner_lib import core

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("lookup_failure", ["unavailable", "missing-head"])
@pytest.mark.parametrize("advanced", [False, True])
@pytest.mark.parametrize(
    "helper_source",
    [
        ".github/scripts/autofix_metrics.js",
        "templates/consumer-repo/.github/scripts/autofix_metrics.js",
    ],
)
def test_collector_failure_retains_reservation_through_completion_shell(
    tmp_path, lookup_failure, advanced, helper_source
):
    """Run the shipped collector and shell, including the runner's receipt boundary."""
    workflow = yaml.safe_load(
        (
            ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
        ).read_text()
    )
    steps = workflow["jobs"]["metrics"]["steps"]
    collect = next(step for step in steps if step.get("id") == "collect")
    completion = next(step for step in steps if step.get("name") == "Record autofix completion")
    head = "a" * 40
    inputs = {
        "needs.prepare.outputs.pr_number || 0": "42",
        "needs.prepare.outputs.head_sha": head,
        "needs.prepare.outputs.gate_conclusion": "failure",
        "needs.autofix.result": "success",
        "needs.autofix-claude.result": "skipped",
        "needs.autofix-cursor.result": "skipped",
        "needs.autofix-muse.result": "skipped",
    }
    script = re.sub(
        r"\$\{\{\s*(.*?)\s*\}\}", lambda m: inputs.get(m[1], ""), collect["with"]["script"]
    )
    collector = tmp_path / "collect.js"
    collector.write_text(
        "const context = {repo: {owner: 'owner', repo: 'repo'}, payload: {}};\n"
        "const core = {info() {}, warning() {}, setOutput(name, value) {\n"
        "  if (name === 'metrics_json') process.stdout.write(value);\n"
        "}};\n"
        "const github = {rest: {pulls: {async get() {\n"
        + (
            "throw new Error('PR lookup unavailable');\n"
            if lookup_failure == "unavailable"
            else "return {data: {head: {}}};\n"
        )
        + "}}, actions: {async listWorkflowRuns() { return {data: []}; }}}};\n"
        + "async function collect() {\n"
        + script
        + "\n}\ncollect().catch(() => {process.exitCode = 1;});\n"
    )
    measured = subprocess.run(
        ["node", str(collector)], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    metrics = json.loads(measured.stdout)
    assert metrics["head_sha_after"] == head
    assert metrics["fix_applied"] is False

    # Keep the real CLI validation and persistence code, substituting only its
    # storage transport. No network or workflow permissions are needed.
    state = tmp_path / "reservation.json"
    pending = {
        "provider": "codex",
        "pr_number": 42,
        "head_sha": head,
        "key": core._runner_key(42, head, "codex"),
        "status": "pending",
        "workflow_attempt_id": "test-source",
        "unproductive_completions": 1,
    }
    state.write_text(json.dumps(pending))
    original = state.read_bytes()
    binary = tmp_path / "bin"
    binary.mkdir()
    wrapper = binary / "python"
    wrapper.write_text('#!/bin/sh\nexec "$REAL_PYTHON" "$RUNNER_HELPER" "$@"\n')
    wrapper.chmod(0o755)
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "from scripts.runner_lib import core\n"
        "state = Path(os.environ['RESERVATION_PATH'])\n"
        "class Storage:\n"
        "    def read_record(self, *_): return json.loads(state.read_text())\n"
        "    def write_record(self, _pr, _provider, record):\n"
        "        state.write_text(json.dumps(record))\n"
        "core._storage_from_name = lambda _: Storage()\n"
        "core._workflow_attempt_id = lambda: 'test-source'\n"
        "assert sys.argv[1:3] == ['-m', 'scripts.runner_lib']\n"
        "sys.exit(core.main(sys.argv[3:]))\n"
    )
    env = {
        **os.environ,
        "PATH": str(binary) + ":" + os.environ["PATH"],
        "PYTHONPATH": str(ROOT),
        "REAL_PYTHON": sys.executable,
        "RUNNER_HELPER": str(runner),
        "RESERVATION_PATH": str(state),
        "GITHUB_OUTPUT": str(tmp_path / "github-output"),
        "PR_NUMBER": "42",
        "HEAD_SHA": head,
        "PROVIDER": "codex",
        "METRICS_JSON": measured.stdout,
    }
    # Repeated observation failures must not spend the remaining retry allowance.
    for _ in range(2):
        result = subprocess.run(
            ["bash", "-c", completion["run"]], env=env, capture_output=True, text=True
        )
        assert result.returncode != 0
        assert "retain reservation" in result.stderr
        assert state.read_bytes() == original

    # Recover through the shipped observer rather than manufacturing its evidence
    # flag. Gate telemetry can still fail after a valid PR-head observation.
    observed_head = "b" * 40 if advanced else head
    observed = subprocess.run(
        [
            "node",
            "-e",
            "const {observeAutofixHead} = require(process.env.OBSERVER_PATH);\n"
            "const outputs = {};\n"
            "const github = {rest: {pulls: {async get() {\n"
            "  return {data: {head: {sha: process.env.OBSERVED_HEAD}, labels: []}};\n"
            "}}, actions: {listWorkflowRuns() {}}}};\n"
            "observeAutofixHead({github, context: {repo: {owner: 'owner', repo: 'repo'}},\n"
            "  core: {warning() {}, info() {}, setOutput(k, v) {outputs[k] = v;}},\n"
            "  withRetry: fn => fn(github),\n"
            "  paginateWithRetry: async () => {throw new Error('Gate unavailable');},\n"
            "  prNumber: 42, headShaBefore: process.env.HEAD_SHA,\n"
            "  gateConclusionBefore: 'failure'\n"
            "}).then(observation => process.stdout.write(JSON.stringify({\n"
            "  ...JSON.parse(process.env.METRICS_JSON), ...observation, outputs\n"
            "}))).catch(() => {process.exitCode = 1;});\n",
        ],
        env={**env, "OBSERVER_PATH": str(ROOT / helper_source), "OBSERVED_HEAD": observed_head},
        capture_output=True,
        text=True,
        check=True,
    )
    recovered = json.loads(observed.stdout)
    assert recovered["head_observed"] is True
    assert recovered["outputs"]["head_observed"] == "true"
    assert recovered["head_sha_after"] == observed_head
    assert recovered["fix_applied"] is advanced
    assert recovered["gate_result_after"] == "failure"
    env["METRICS_JSON"] = observed.stdout
    subprocess.run(["bash", "-c", completion["run"]], env=env, capture_output=True, check=True)
    recorded = json.loads(state.read_text())
    assert recorded["status"] == "completed"
    assert recorded["productive"] is advanced
    assert recorded["unproductive_completions"] == (0 if advanced else 2)
    if advanced:
        assert recorded["observed_head_sha"] == observed_head


@pytest.mark.parametrize("advanced", [False, True])
def test_consumer_autofix_records_its_own_completion(tmp_path, monkeypatch, advanced):
    workflow = yaml.safe_load(
        (
            ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
        ).read_text()
    )
    metrics = workflow["jobs"]["metrics"]
    steps = metrics["steps"]
    completion = next((s for s in steps if s.get("name") == "Record autofix completion"), None)
    assert completion is not None, "autofix finishes without acknowledging its runner reservation"
    assert "always()" in completion["if"]
    assert "needs.prepare.outputs.dispatch_should_run == 'true'" in completion["if"]
    assert "steps.collect.outcome == 'success'" in completion["if"]
    assert all(
        f"needs.{job}.result != 'skipped'" in completion["if"]
        for job in ["autofix", "autofix-claude", "autofix-cursor", "autofix-muse"]
    )
    checkout = next(s for s in steps if "checkout@" in s.get("uses", ""))
    assert "scripts/runner_lib" in checkout["with"]["sparse-checkout"]
    # Execute the actual shell against the retained native 42575919772 metrics.
    binary = tmp_path / "bin"
    binary.mkdir()
    capture = tmp_path / "calls.jsonl"
    wrapper = binary / "python"
    wrapper.write_text('#!/bin/sh\nexec "$REAL_PYTHON" "$CAPTURE_HELPER" "$@"\n')
    wrapper.chmod(0o755)
    helper = tmp_path / "capture.py"
    helper.write_text(
        'import json,os,sys\nopen(os.environ["CAPTURE"],"a").write(json.dumps(sys.argv[1:])+"\\n")\n'
    )
    import sys

    env = {
        **os.environ,
        "PATH": str(binary) + ":" + os.environ["PATH"],
        "REAL_PYTHON": sys.executable,
        "CAPTURE_HELPER": str(helper),
        "CAPTURE": str(capture),
        "PR_NUMBER": "1286",
        "HEAD_SHA": "f27f30c19b225fcc0c248ef57a31e5df2bc4730c",
        "PROVIDER": "codex",
        "METRICS_JSON": json.dumps(
            {
                "head_sha_before": "f27f30c19b225fcc0c248ef57a31e5df2bc4730c",
                "head_sha_after": (
                    "b" * 40 if advanced else "f27f30c19b225fcc0c248ef57a31e5df2bc4730c"
                ),
                "fix_applied": advanced,
                "autofix_result": "success",
            }
        ),
    }
    subprocess.run(["bash", "-c", completion["run"]], env=env, check=True, capture_output=True)
    calls = [json.loads(line) for line in capture.read_text().splitlines()]
    assert len(calls) == 1
    args = calls[0]
    assert args[:3] == ["-m", "scripts.runner_lib", "record-completion"]
    assert args[args.index("--head-sha") + 1] == env["HEAD_SHA"]
    assert args[args.index("--produced-work") + 1] == str(advanced).lower()
    assert args[args.index("--exit-code") + 1] == "0"
    assert "GITHUB_RUN_ID=" not in completion["run"]

    class Memory:
        row = {
            "provider": "codex",
            "pr_number": 1286,
            "head_sha": env["HEAD_SHA"],
            "status": "pending",
            "key": core._runner_key(1286, env["HEAD_SHA"], "codex"),
            "workflow_attempt_id": "test-source",
        }

        def read_record(self, *_):
            return dict(self.row)

        def write_record(self, _pr, _provider, record):
            self.row = dict(record)

    storage = Memory()
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "test-source")
    observed = args[args.index("--observed-head-sha") + 1] if "--observed-head-sha" in args else ""
    result = core.record_completion(
        1286,
        env["HEAD_SHA"],
        "codex",
        {"success": True},
        storage=storage,
        produced_work=advanced,
        observed_head_sha=observed,
    )
    assert (
        result.get("productive") is advanced
    ), "measured autofix productivity must not become unmeasured terminal completion"
    if advanced:
        assert result["observed_head_sha"] == "b" * 40
        assert result["completion_incomplete"] is False
        return
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "test-next")
    decision = core.should_dispatch(1286, env["HEAD_SHA"], "codex", storage=storage)
    assert decision.should_dispatch
    assert decision.reason == "retry-unproductive-completion"
