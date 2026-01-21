import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import keepalive_metrics_collector as collector
from scripts import keepalive_metrics_dashboard as dashboard

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "scripts" / "fixtures" / "keepalive_metrics"
HARNESS = FIXTURES_DIR / "harness.js"


def _require_node() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for keepalive metrics dashboard E2E tests")


def test_keepalive_metrics_dashboard_pipeline(tmp_path: Path) -> None:
    _require_node()
    assert HARNESS.exists(), f"Missing keepalive metrics harness: {HARNESS}"

    result = subprocess.run(
        ["node", str(HARNESS)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Harness failed with code {result.returncode}:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    record = json.loads(result.stdout or "{}")
    collector.validate_record(record)

    log_path = tmp_path / "keepalive-metrics.ndjson"
    collector.append_record(log_path, record)

    output_path = tmp_path / "dashboard.md"
    exit_code = dashboard.main(["--path", str(log_path), "--output", str(output_path)])
    assert exit_code == 0
    content = output_path.read_text(encoding="utf-8")
    assert "# Keepalive Metrics Dashboard" in content
    assert "| Metric | Value | Status |" in content
    assert "Total records" in content
    assert "Success rate" in content
