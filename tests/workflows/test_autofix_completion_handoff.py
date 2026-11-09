"""The autofix metrics job must finish the reservation made by prepare."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from scripts.runner_lib import core

ROOT = Path(__file__).resolve().parents[2]


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
