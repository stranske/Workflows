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


WORKFLOW = ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
HELPER_SOURCES = [
    ".github/scripts/autofix_metrics.js",
    "templates/consumer-repo/.github/scripts/autofix_metrics.js",
]
# Authentic dispatch head from native run 42575919772, retained by the
# historical recovery tests. Fault injection changes only the API responses.
NATIVE_HEAD = "f27f30c19b225fcc0c248ef57a31e5df2bc4730c"
OBSERVATIONS = {
    "lookup-failed": None,
    "missing-head": {},
    "malformed-head": {"sha": "not-a-sha"},
    "unchanged": {"sha": NATIVE_HEAD},
    "changed": {"sha": "b" * 40},
    "unchanged-telemetry-failed": {"sha": NATIVE_HEAD},
    "changed-telemetry-failed": {"sha": "b" * 40},
}


def _metrics_steps():
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["metrics"]["steps"]
    collect = next(s for s in steps if s.get("id") == "collect")
    completion = next(s for s in steps if s.get("name") == "Record autofix completion")
    checkout = next(s for s in steps if "checkout@" in s.get("uses", ""))
    return collect, completion, checkout


def _run_collector(workspace: Path, helper_source: str, observation: str):
    """Execute the wired Collect metrics script in a sparse-checkout workspace.

    The helper is copied from the shipped source into the path the workflow's
    sparse checkout delivers; head_observed comes only from that helper.
    """
    collect, _completion, checkout = _metrics_steps()
    sparse = checkout["with"]["sparse-checkout"].split()
    assert ".github/scripts/autofix_metrics.js" in sparse
    helper = workspace / ".github/scripts/autofix_metrics.js"
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_bytes((ROOT / helper_source).read_bytes())
    values = {
        "needs.prepare.outputs.pr_number || 0": "1286",
        "needs.prepare.outputs.head_sha": NATIVE_HEAD,
        "needs.prepare.outputs.gate_conclusion": "failure",
        "needs.autofix.result": "success",
        "needs.autofix-claude.result": "skipped",
        "needs.autofix-cursor.result": "skipped",
        "needs.autofix-muse.result": "skipped",
    }
    script = re.sub(
        r"\$\{\{\s*(.*?)\s*\}\}", lambda m: values.get(m[1], ""), collect["with"]["script"]
    )
    collector = workspace / "collect.js"
    collector.write_text(
        "const head = " + json.dumps(OBSERVATIONS[observation]) + ";\n"
        "const telemetryFails = " + json.dumps(observation.endswith("telemetry-failed")) + ";\n"
        "const outputs = {};\n"
        "const core = {info() {}, warning() {}, setOutput(k, v) { outputs[k] = v; }};\n"
        "const context = {repo: {owner: 'stranske', repo: 'Orchestrator'}, payload: {}};\n"
        "const github = {rest: {\n"
        "  pulls: {async get() {\n"
        "    if (head === null) throw new Error('injected PR read failure');\n"
        "    return {data: {head, labels: [{name: 'autofix:escalated'}]}};\n"
        "  }},\n"
        "  issues: {async removeLabel() {\n"
        "    if (telemetryFails) throw new Error('injected label failure');\n"
        "  }},\n"
        "  actions: {async listWorkflowRuns() {\n"
        "    if (telemetryFails) throw new Error('injected Gate read failure');\n"
        "    return {data: {workflow_runs: [{conclusion: 'success'}]}};\n"
        "  }},\n"
        "}};\n"
        "(async () => {\n" + script + "\n})().then(\n"
        "  () => process.stdout.write(JSON.stringify(outputs)),\n"
        "  (error) => { console.error(error); process.exitCode = 1; },\n"
        ");\n"
    )
    measured = subprocess.run(
        ["node", str(collector)], cwd=workspace, capture_output=True, text=True, check=True
    )
    return json.loads(measured.stdout)


def _completion_env(tmp_path: Path, metrics_json: str, state: Path):
    """Run the real runner CLI, substituting only its storage transport."""
    binary = tmp_path / "bin"
    binary.mkdir(exist_ok=True)
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
    return {
        **os.environ,
        "PATH": str(binary) + ":" + os.environ["PATH"],
        "PYTHONPATH": str(ROOT),
        "REAL_PYTHON": sys.executable,
        "RUNNER_HELPER": str(runner),
        "RESERVATION_PATH": str(state),
        "GITHUB_OUTPUT": str(tmp_path / "github-output"),
        "PR_NUMBER": "1286",
        "HEAD_SHA": NATIVE_HEAD,
        "PROVIDER": "codex",
        "METRICS_JSON": metrics_json,
    }


@pytest.mark.parametrize("observation", list(OBSERVATIONS))
@pytest.mark.parametrize("helper_source", HELPER_SOURCES)
def test_wired_collector_and_completion_shell_record_only_observed_heads(
    tmp_path, observation, helper_source
):
    """Run the wired collector, step condition and completion shell end to end."""
    _collect, completion, _checkout = _metrics_steps()
    assert "steps.collect.outputs.head_observed == 'true'" in completion["if"]
    workspace = tmp_path / "workspace"
    outputs = _run_collector(workspace, helper_source, observation)
    metrics = json.loads(outputs["metrics_json"])
    observed = OBSERVATIONS[observation] in ({"sha": NATIVE_HEAD}, {"sha": "b" * 40})
    assert outputs["head_observed"] == str(observed).lower()
    assert metrics["head_observed"] is observed

    state = tmp_path / "reservation.json"
    state.write_text(
        json.dumps(
            {
                "provider": "codex",
                "pr_number": 1286,
                "head_sha": NATIVE_HEAD,
                "key": core._runner_key(1286, NATIVE_HEAD, "codex"),
                "status": "pending",
                "workflow_attempt_id": "test-source",
                "unproductive_completions": 1,
            }
        )
    )
    original = state.read_bytes()
    env = _completion_env(tmp_path, outputs["metrics_json"], state)

    def completion_shell():
        return subprocess.run(
            ["bash", "-c", completion["run"]],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
        )

    if not observed:
        assert metrics["head_sha_after"] == ""
        assert metrics["fix_applied"] is False
        # The step condition skips it; even if run, the helper CLI refuses and
        # repeated failures cannot spend the remaining retry allowance.
        for _ in range(2):
            result = completion_shell()
            assert result.returncode != 0
            assert "retain reservation" in result.stderr
            assert state.read_bytes() == original
        return

    changed = OBSERVATIONS[observation]["sha"] != NATIVE_HEAD
    assert metrics["head_sha_after"] == OBSERVATIONS[observation]["sha"]
    assert metrics["fix_applied"] is changed
    assert metrics["gate_result_after"] == (
        "failure" if observation.endswith("telemetry-failed") else "success"
    )
    result = completion_shell()
    assert result.returncode == 0, result.stderr
    recorded = json.loads(state.read_text())
    assert recorded["status"] == "completed"
    assert recorded["productive"] is changed
    assert recorded["unproductive_completions"] == (0 if changed else 2)
    if changed:
        assert recorded["observed_head_sha"] == "b" * 40


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
    # Execute the actual shell against metrics the wired collector measures
    # for the retained native 42575919772 dispatch head.
    workspace = tmp_path / "workspace"
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
        "METRICS_JSON": _run_collector(
            workspace, HELPER_SOURCES[1], "changed" if advanced else "unchanged"
        )["metrics_json"],
    }
    subprocess.run(
        ["bash", "-c", completion["run"]], cwd=workspace, env=env, check=True, capture_output=True
    )
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
