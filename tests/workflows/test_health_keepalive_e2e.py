"""Run the mode selector and receipt verifier directly from the workflow."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/health-keepalive-e2e.yml"
PING = b"keepalive-e2e-ping-ok"


def test_ping_prompt_requests_the_reply_accepted_by_the_verifier():
    prompt = (ROOT / ".github/codex/prompts/e2e-ping.md").read_text()
    assert f'Simply respond with exactly: "{PING.decode()}"' in prompt


def run_step(job, step_name, tmp_path, **outputs):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"][job]["steps"]
    step = next(step for step in steps if step["name"] == step_name)
    env = {
        **os.environ,
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        **{key: outputs.get(key, "") for key in step["env"]},
    }
    return subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=ROOT,
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


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        pytest.param({}, "", id="exact-reply"),
        pytest.param(
            {"FINAL_MESSAGE": base64.b64encode(PING + b"\r\n\n").decode()},
            "",
            id="terminal-line-endings",
        ),
        pytest.param({"FINAL_MESSAGE": ""}, "missing final message", id="missing-reply"),
        pytest.param(
            {"FINAL_MESSAGE": base64.b64encode(b"private model reply").decode()},
            "unexpected reply",
            id="incorrect-reply",
        ),
        pytest.param(
            {"FINAL_MESSAGE": base64.b64encode(PING + b" ").decode()},
            "unexpected reply",
            id="trailing-space",
        ),
        pytest.param({"FINAL_MESSAGE": "%%%="}, "invalid base64", id="invalid-encoding"),
        pytest.param(
            {"FINAL_MESSAGE": base64.b64encode(PING).decode() + "="},
            "invalid base64",
            id="extra-base64-padding",
        ),
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
        "FINAL_MESSAGE": base64.b64encode(PING).decode(),
    } | overrides
    result = run_step("codex-ping-verify", "Check results", tmp_path, **receipt)
    logs = result.stdout + result.stderr
    assert "private model reply" not in logs
    assert PING.decode() not in logs
    if receipt["FINAL_MESSAGE"]:
        assert receipt["FINAL_MESSAGE"] not in logs
    assert result.returncode == (1 if expected_error else 0), logs
    if expected_error:
        assert expected_error in logs
        assert "Codex ping E2E passed" not in logs
    else:
        assert "Codex ping E2E passed" in logs
