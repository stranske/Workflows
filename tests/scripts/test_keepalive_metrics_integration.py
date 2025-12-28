import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import keepalive_metrics_collector as collector

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "keepalive_metrics"
HARNESS = FIXTURES_DIR / "harness.js"


def _require_node() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for keepalive metrics integration tests")


def test_keepalive_metrics_smoke(tmp_path: Path) -> None:
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

    output_path = tmp_path / "metrics.ndjson"
    collector.append_record(output_path, record)
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    persisted = json.loads(lines[0])
    assert persisted["pr_number"] == record["pr_number"]
