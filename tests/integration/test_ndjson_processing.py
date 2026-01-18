from __future__ import annotations

import json
from pathlib import Path

from scripts import aggregate_repo_metrics


def test_ndjson_processing_integration(tmp_path: Path) -> None:
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir()

    (metrics_dir / "alpha__one.ndjson").write_text(
        '{"metric_name": "latency", "workflow": "build", "dimension": "cpu", "value": 10}\n',
        encoding="utf-8",
    )
    (metrics_dir / "beta__two.ndjson").write_text(
        '{"metric_name": "latency", "workflow": "build", "dimension": "cpu", "value": 30}\n',
        encoding="utf-8",
    )

    output = tmp_path / "combined.ndjson"
    summary_output = tmp_path / "summary.json"

    result = aggregate_repo_metrics.main(
        [
            "--repos",
            "alpha/one,beta/two",
            "--metrics-dir",
            str(metrics_dir),
            "--output",
            str(output),
            "--summary-output",
            str(summary_output),
        ]
    )

    assert result == 0

    combined_entries = [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ]
    raw_entries = [entry for entry in combined_entries if entry.get("entry_type") != "aggregate"]
    aggregate_entries = [
        entry for entry in combined_entries if entry.get("entry_type") == "aggregate"
    ]

    assert {entry["repo"] for entry in raw_entries} == {"alpha/one", "beta/two"}
    assert aggregate_entries
    aggregate = aggregate_entries[0]
    assert aggregate["group"]["metric_name"] == "latency"
    assert aggregate["summary"]["p50"] == 20.0
