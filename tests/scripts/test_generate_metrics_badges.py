from __future__ import annotations

import json
from pathlib import Path

from scripts import generate_metrics_badges


def test_build_endpoint_payloads_formats_metrics() -> None:
    metrics = {
        "success_rate": 0.96,
        "avg_duration_seconds": 625,
        "last_run_status": "success",
    }

    payloads = generate_metrics_badges.build_endpoint_payloads(metrics)

    success = payloads["success_rate"]
    assert success["label"] == "Success Rate"
    assert success["message"] == "96.0%"
    assert success["color"] == "brightgreen"

    duration = payloads["avg_duration"]
    assert duration["message"] == "10m 25s"
    assert duration["color"] == "yellow"

    status = payloads["last_run_status"]
    assert status["message"] == "success"
    assert status["color"] == "brightgreen"


def test_main_writes_badge_files(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "success_rate": 0.94,
                "avg_duration_seconds": 450,
                "last_run_status": "failure",
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "badges"

    exit_code = generate_metrics_badges.main(
        ["--metrics-path", str(metrics_path), "--output-dir", str(output_dir)]
    )

    assert exit_code == 0
    success = json.loads((output_dir / "success_rate.json").read_text(encoding="utf-8"))
    assert success["message"] == "94.0%"


def test_main_emits_single_badge(capsys, tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "success_rate": 0.5,
                "avg_duration_seconds": 1200,
                "last_run_status": "queued",
            }
        ),
        encoding="utf-8",
    )

    exit_code = generate_metrics_badges.main(
        ["--metrics-path", str(metrics_path), "--badge", "last_run_status"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["message"] == "queued"
    assert payload["color"] == "blue"
