import json
from pathlib import Path

import pytest
from scripts import autopilot_step_timer as timer


def test_timer_writes_failure_summary_when_env_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary_path = tmp_path / "summary.ndjson"
    monkeypatch.setenv("AUTOPILOT_METRICS_SUMMARY_PATH", str(summary_path))
    monkeypatch.setenv("AUTOPILOT_STEP_NAME", "format")
    monkeypatch.setenv("GITHUB_RUN_ID", "run-123")
    monkeypatch.delenv("GITHUB_ENV", raising=False)

    exit_code = timer.main(["--event", "start", "--github-env"])

    assert exit_code != 0
    summary_lines = summary_path.read_text(encoding="utf-8").splitlines()
    assert len(summary_lines) == 1
    summary = json.loads(summary_lines[0])
    assert summary["summary_type"] == "autopilot-metrics-error"
    assert summary["component"] == "autopilot_step_timer"
    assert summary["step_name"] == "format"
    assert summary["error_category"] == "timer_error"
    assert summary["exit_code"] == 1
    assert summary["environment"]["github_run_id"] == "run-123"
