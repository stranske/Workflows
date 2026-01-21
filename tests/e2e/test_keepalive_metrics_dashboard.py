import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import keepalive_metrics_collector as collector
from scripts import keepalive_metrics_dashboard as dashboard
from scripts import keepalive_post_merge_metrics as post_merge

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


def test_keepalive_post_merge_metrics_pipeline(tmp_path: Path) -> None:
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

    output_path = tmp_path / "post-merge.ndjson"
    exit_code = post_merge.main(
        [
            "--metrics-path",
            str(log_path),
            "--output-path",
            str(output_path),
            "--pr-number",
            str(record["pr_number"]),
            "--merged-at",
            "2025-01-01T00:00:00Z",
            "--human-interventions",
            "0",
        ]
    )
    assert exit_code == 0
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    persisted = json.loads(lines[0])
    assert persisted["metric_type"] == "post-merge"
    assert persisted["pr_number"] == record["pr_number"]
