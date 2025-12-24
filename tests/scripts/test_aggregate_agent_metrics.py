import json
from pathlib import Path

import pytest

from scripts import aggregate_agent_metrics


def _write_ndjson(path: Path, entries: list[dict]) -> None:
    lines = [json.dumps(entry, sort_keys=True) for entry in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_build_summary_formats_sections() -> None:
    entries = [
        {
            "pr_number": 101,
            "iteration_count": 3,
            "stop_reason": "tasks-complete",
            "gate_conclusion": "success",
            "timestamp": "2025-01-01T00:00:00Z",
        },
        {
            "pr_number": 202,
            "iteration_count": 4,
            "stop_reason": "max-iterations",
            "gate_conclusion": "success",
        },
        {
            "pr_number": 101,
            "attempt_number": 1,
            "trigger_reason": "mypy",
            "fix_applied": True,
            "gate_result_after": "success",
        },
        {
            "pr_number": 101,
            "verdict": "pass",
            "issues_created": 0,
            "acceptance_criteria_count": 3,
        },
    ]

    summary = aggregate_agent_metrics.build_summary(entries, errors=1)

    assert "Records: 4 (keepalive 2, autofix 1, verifier 1, unknown 0)" in summary
    assert "Parse errors: 1" in summary
    assert "Avg iterations: 3.5" in summary
    assert "tasks-complete (1)" in summary
    assert "max-iterations (1)" in summary
    assert "Fixes applied: 100.0% (1/1)" in summary
    assert "Verdicts: pass (1)" in summary
    assert "Avg acceptance criteria: 3.0" in summary


def test_main_writes_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    keepalive_path = tmp_path / "keepalive.ndjson"
    autofix_path = tmp_path / "autofix.ndjson"
    output_path = tmp_path / "summary.md"

    _write_ndjson(
        keepalive_path,
        [
            {
                "pr_number": 111,
                "iteration_count": 1,
                "stop_reason": "tasks-complete",
                "gate_conclusion": "success",
            }
        ],
    )
    _write_ndjson(
        autofix_path,
        [
            {
                "pr_number": 111,
                "attempt_number": 2,
                "trigger_reason": "pytest",
                "fix_applied": False,
                "gate_result_after": "failure",
            }
        ],
    )

    monkeypatch.setenv("METRICS_PATHS", f"{keepalive_path},{autofix_path}")
    monkeypatch.setenv("OUTPUT_PATH", str(output_path))

    exit_code = aggregate_agent_metrics.main()

    assert exit_code == 0
    assert output_path.exists()
    summary = output_path.read_text(encoding="utf-8")
    assert "Keepalive" in summary
    assert "Autofix" in summary

    monkeypatch.delenv("METRICS_PATHS", raising=False)
    monkeypatch.delenv("OUTPUT_PATH", raising=False)
