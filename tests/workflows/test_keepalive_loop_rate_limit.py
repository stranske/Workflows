import json
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "keepalive_loop"
HARNESS = FIXTURES_DIR / "harness.js"


def _require_node() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for keepalive loop harness tests")


def _run_scenario(name: str) -> dict:
    _require_node()
    scenario_path = FIXTURES_DIR / f"{name}.json"
    assert scenario_path.exists(), f"Scenario fixture missing: {scenario_path}"
    command = ["node", str(HARNESS), str(scenario_path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(
            f"Harness failed with code {result.returncode}:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        pytest.fail(f"Invalid harness output: {exc}: {result.stdout}")


def test_keepalive_loop_bypasses_rate_limit_cancellation() -> None:
    """Rate limits cause defer to wait for reset."""
    result = _run_scenario("cancelled_rate_limit")
    # New behavior: Rate limit detected early, defer immediately
    # Old behavior was: Check gate, detect rate limit cancellation, bypass and run
    assert result["action"] == "defer"
    assert result["reason"] == "rate-limit-exhausted"


def test_keepalive_loop_defers_on_gate_rate_limit_signal() -> None:
    """Gate cancellation with rate limit signals bypasses when tokens remain."""
    result = _run_scenario("cancelled_rate_limit_secondary")
    assert result["action"] == "run"
    assert result["reason"] == "bypass-rate-limit-gate"


def test_keepalive_loop_defers_on_success_when_rate_limit_exhausted() -> None:
    """Successful gate still defers when primary token capacity is exhausted."""
    result = _run_scenario("success_rate_limit_exhausted")
    assert result["action"] == "defer"
    assert result["reason"] == "rate-limit-exhausted"


def test_keepalive_loop_rejects_foreign_recovery_owner_markers() -> None:
    """Attempt-not-current runs must not poison recovery_owner_attempt markers."""
    _require_node()
    repo_root = Path(__file__).resolve().parents[2]
    test_file = repo_root / ".github/scripts/__tests__/keepalive-loop.test.js"
    command = [
        "node",
        "--test",
        "--test-name-pattern=non-authority failed summary does not record recovery owner",
        str(test_file),
    ]
    result = subprocess.run(command, capture_output=True, text=True, cwd=repo_root)
    if result.returncode != 0:
        pytest.fail(
            f"Node regression failed with code {result.returncode}:\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
