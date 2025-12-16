import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

GUARD_ANALYSIS = Path(__file__).resolve().parent / "fixtures" / "keepalive" / "guard_analysis.js"


def _require_node() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for keepalive guard tests")


def _run_guard_analysis(comments: list[str]) -> dict:
    _require_node()
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as handle:
        json.dump({"comments": comments}, handle)
        temp_path = handle.name
    try:
        result = subprocess.run(
            ["node", str(GUARD_ANALYSIS), temp_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.fail(
                "Guard analysis failed with code %s:\nSTDOUT:\n%s\nSTDERR:\n%s"
                % (result.returncode, result.stdout, result.stderr)
            )
        try:
            return json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            pytest.fail(f"Invalid guard analysis output: {exc}: {result.stdout}")
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_guard_analysis_counts_gate_and_non_gate() -> None:
    comments = [
        "<!-- keepalive-skip -->\n<!-- keepalive-skip-count: 1 -->\nKeepalive 1 abc skipped: gate-not-green",
        "<!-- keepalive-skip -->\n<!-- keepalive-skip-count: 2 -->\nKeepalive 2 def skipped: pr-draft",
        "Random observer comment",
    ]
    data = _run_guard_analysis(comments)
    assert data["total"] == 2
    assert data["gateCount"] == 1
    assert data["nonGateCount"] == 1
    assert data["highestCount"] == 2
    assert "pr-draft" in data["nonGateReasons"]


def test_guard_analysis_handles_legacy_comments() -> None:
    comments = [
        "Keepalive 3 token skipped: missing-label:agent:codex",
        "<!-- keepalive-skip -->\nKeepalive 4 token skipped: gate-run-missing",
    ]
    data = _run_guard_analysis(comments)
    assert data["total"] == 2
    assert data["gateCount"] == 1
    assert data["nonGateCount"] == 1
    # Legacy comments without explicit count should fall back to total
    assert data["highestCount"] == 2
