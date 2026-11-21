"""Run the keepalive ping receipt contract directly from the workflows."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/health-keepalive-e2e.yml"
RUNNER = ROOT / ".github/workflows/reusable-codex-run.yml"
PING = b"keepalive-e2e-ping-ok"


def test_ping_prompt_requests_the_reply_accepted_by_the_verifier():
    prompt = (ROOT / ".github/codex/prompts/e2e-ping.md").read_text()
    assert f'Simply respond with exactly: "{PING.decode()}"' in prompt


def run_step(job, step_name, tmp_path, **outputs):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"][job]["steps"]
    step = next(step for step in steps if step["name"] == step_name)
    return run_bash(step["run"], tmp_path, **{key: outputs.get(key, "") for key in step["env"]})


def run_bash(script, tmp_path, **variables):
    env = {
        **os.environ,
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        **variables,
    }
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )


@pytest.mark.parametrize(
    ("labels", "mode"),
    [
        pytest.param(["other", "e2e:codex-ping"], "codex-ping", id="exact-label"),
        pytest.param(["e2e:codex-ping-disabled"], "orchestration", id="label-lookalike"),
        pytest.param([], "orchestration", id="default"),
    ],
)
def test_select_mode(tmp_path, labels, mode):
    result = run_step(
        "detect-mode", "Check for codex-ping label", tmp_path, LABELS=json.dumps(labels)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "output").read_text() == f"mode={mode}\n"


def test_ping_receipt_wiring():
    health_jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    call = health_jobs["codex-ping-run"]
    verifier = health_jobs["codex-ping-verify"]
    assert call["uses"] == "./.github/workflows/reusable-codex-run.yml"
    assert call["with"]["mode"] == "e2e-test"
    assert call["if"] == verifier["if"] == "needs.detect-mode.outputs.mode == 'codex-ping'"
    assert verifier["needs"] == ["detect-mode", "codex-ping-run"]
    assert [step["name"] for step in verifier["steps"]] == ["Check results", "Summary"]
    assert all("uses" not in step for step in verifier["steps"])
    assert verifier["steps"][0]["env"] == {
        "EXIT_CODE": "${{ needs.codex-ping-run.outputs.exit-code }}",
        "CHANGES_MADE": "${{ needs.codex-ping-run.outputs.changes-made }}",
        "PING_REPLY_MATCHED": "${{ needs.codex-ping-run.outputs.e2e-ping-reply-matched }}",
    }

    runner = yaml.safe_load(RUNNER.read_text())
    codex = runner["jobs"]["codex"]
    setup = next(step for step in codex["steps"] if step.get("id") == "run_base")
    assert setup["with"]["runner_mode"] == "${{ inputs.mode }}"
    assert setup["with"]["mode_env_name"] == "CODEX_MODE"
    assert (
        codex["outputs"]["e2e-ping-reply-matched"]
        == "${{ steps.run_codex.outputs.e2e-ping-reply-matched }}"
    )
    assert (
        runner[True]["workflow_call"]["outputs"]["e2e-ping-reply-matched"]["value"]
        == "${{ jobs.codex.outputs.e2e-ping-reply-matched }}"
    )


@pytest.mark.parametrize(
    ("raw", "mode", "matched"),
    [
        pytest.param(PING, "e2e-test", "true", id="exact"),
        pytest.param(PING + b"\r\n\n\r", "e2e-test", "true", id="terminal-line-endings"),
        pytest.param(None, "e2e-test", "false", id="missing"),
        pytest.param(b"", "e2e-test", "false", id="empty"),
        pytest.param(b"private model reply", "e2e-test", "false", id="wrong-reply"),
        pytest.param(PING + b"\xff\x00\n", "e2e-test", "false", id="malformed-bytes"),
        pytest.param(b" " + PING, "e2e-test", "false", id="leading-space"),
        pytest.param(PING + b" \r\n", "e2e-test", "false", id="trailing-space"),
        pytest.param(PING, "keepalive", None, id="production-mode"),
        pytest.param(PING, "e2e-test-other", None, id="mode-lookalike"),
    ],
)
def test_raw_ping_receipt(tmp_path, raw, mode, matched):
    steps = yaml.safe_load(RUNNER.read_text())["jobs"]["codex"]["steps"]
    run_codex = next(step["run"] for step in steps if step.get("id") == "run_codex")
    assert '--output-last-message "$OUTPUT_FILE"' in run_codex
    start = run_codex.index("# Check the raw E2E ping reply")
    end = run_codex.index("# Set outputs for downstream steps", start)

    raw_file = tmp_path / "raw reply"
    if raw is not None:
        raw_file.write_bytes(raw)
    output = tmp_path / "output"
    output.touch()
    result = run_bash(run_codex[start:end], tmp_path, CODEX_MODE=mode, OUTPUT_FILE=str(raw_file))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert output.read_text() == ("" if matched is None else f"e2e-ping-reply-matched={matched}\n")


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        pytest.param({}, "", id="matched"),
        pytest.param({"PING_REPLY_MATCHED": "false"}, "expected a matching reply", id="unmatched"),
        pytest.param({"PING_REPLY_MATCHED": ""}, "expected a matching reply", id="missing-match"),
        pytest.param({"CHANGES_MADE": "true"}, "expected changes-made=false", id="changes-made"),
        pytest.param(
            {"CHANGES_MADE": "unknown"}, "expected changes-made=false", id="invalid-change"
        ),
        pytest.param({"CHANGES_MADE": ""}, "expected changes-made=false", id="missing-change"),
        pytest.param({"EXIT_CODE": "1"}, "expected exit-code=0", id="nonzero-exit"),
        pytest.param({"EXIT_CODE": "success"}, "expected exit-code=0", id="invalid-exit"),
        pytest.param({"EXIT_CODE": ""}, "expected exit-code=0", id="missing-exit"),
    ],
)
def test_verify_receipt(tmp_path, overrides, expected_error):
    receipt = {
        "EXIT_CODE": "0",
        "CHANGES_MADE": "false",
        "PING_REPLY_MATCHED": "true",
    } | overrides
    result = run_step("codex-ping-verify", "Check results", tmp_path, **receipt)
    logs = result.stdout + result.stderr
    assert PING.decode() not in logs
    assert result.returncode == (1 if expected_error else 0), logs
    if expected_error:
        assert expected_error in logs
        assert "Codex ping E2E passed" not in logs
    else:
        assert "Codex ping E2E passed" in logs
