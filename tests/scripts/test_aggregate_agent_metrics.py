import json
from collections import Counter
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


def test_parse_timestamp_variants() -> None:
    epoch = aggregate_agent_metrics._parse_timestamp(0)
    assert epoch is not None
    assert epoch.tzinfo is not None
    assert aggregate_agent_metrics._parse_timestamp("") is None
    assert aggregate_agent_metrics._parse_timestamp("not-a-date") is None

    naive = aggregate_agent_metrics._parse_timestamp("2025-01-01T00:00:00")
    assert naive is not None
    assert naive.tzinfo is not None

    parsed = aggregate_agent_metrics._parse_timestamp("2025-01-01T12:30:00Z")
    assert parsed is not None
    assert parsed.isoformat().startswith("2025-01-01T12:30:00")

    assert aggregate_agent_metrics._parse_timestamp(object()) is None
    assert aggregate_agent_metrics._parse_timestamp(1e20) is None


def test_gather_metrics_files_prefers_explicit_paths(tmp_path: Path) -> None:
    explicit = [
        str(tmp_path / "a.ndjson"),
        "",
        str(tmp_path / "b.ndjson"),
    ]
    files = aggregate_agent_metrics._gather_metrics_files(explicit, str(tmp_path))
    assert [path.name for path in files] == ["a.ndjson", "b.ndjson"]


def test_gather_metrics_files_falls_back_to_dir(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    first = tmp_path / "nested" / "alpha.ndjson"
    second = tmp_path / "beta.ndjson"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")

    files = aggregate_agent_metrics._gather_metrics_files([], str(tmp_path))
    assert [path.name for path in files] == ["beta.ndjson", "alpha.ndjson"]


def test_gather_metrics_files_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    files = aggregate_agent_metrics._gather_metrics_files([], str(missing))
    assert files == []


def test_read_ndjson_counts_parse_errors(tmp_path: Path) -> None:
    path = tmp_path / "metrics.ndjson"
    path.write_text(
        "\n".join(
            [
                '{"key": "value"}',
                '{"key": "value"',
                "[1, 2, 3]",
                "   ",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    entries, errors = aggregate_agent_metrics._read_ndjson([path])

    assert entries == [{"key": "value"}]
    assert errors == 2


def test_read_ndjson_counts_unreadable_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ndjson"
    entries, errors = aggregate_agent_metrics._read_ndjson([missing])
    assert entries == []
    assert errors == 1


def test_classify_entry_prefers_explicit_type() -> None:
    assert aggregate_agent_metrics._classify_entry({"metric_type": "Keepalive"}) == "keepalive"
    assert aggregate_agent_metrics._classify_entry({"workflow": "autofix"}) == "autofix"
    assert aggregate_agent_metrics._classify_entry({"type": "Verifier"}) == "verifier"
    assert aggregate_agent_metrics._classify_entry({"iteration_count": 1}) == "keepalive"
    assert aggregate_agent_metrics._classify_entry({"trigger_reason": "pytest"}) == "autofix"
    assert aggregate_agent_metrics._classify_entry({"verdict": "pass"}) == "verifier"
    assert aggregate_agent_metrics._classify_entry({"other": "value"}) == "unknown"


def test_safe_number_helpers() -> None:
    assert aggregate_agent_metrics._safe_int("3") == 3
    assert aggregate_agent_metrics._safe_int("bad") is None
    assert aggregate_agent_metrics._safe_float("1.5") == 1.5
    assert aggregate_agent_metrics._safe_float(None) is None
    assert aggregate_agent_metrics._safe_float(object()) is None


def test_summary_helpers_cover_branches() -> None:
    keepalive = aggregate_agent_metrics._summarise_keepalive(
        [
            {
                "stop_reason": "tasks-complete",
                "gate_result": "failure",
                "iteration": "2",
                "pr": "101",
            },
            {
                "stop_reason": None,
                "gate_conclusion": "success",
                "iteration_count": 1,
                "pr_number": 101,
            },
        ]
    )
    assert keepalive["tasks_complete"] == 1
    assert keepalive["stop_reasons"]["tasks-complete"] == 1
    assert keepalive["gate_results"]["failure"] == 1
    assert keepalive["gate_results"]["success"] == 1

    autofix = aggregate_agent_metrics._summarise_autofix(
        [
            {
                "trigger_reason": "pytest",
                "gate_result": "success",
                "pr": 202,
                "fix_applied": "1",
            }
        ]
    )
    assert autofix["fixes_applied"] == 1
    assert autofix["triggers"]["pytest"] == 1
    assert autofix["gate_results"]["success"] == 1

    verifier = aggregate_agent_metrics._summarise_verifier(
        [
            {
                "verdict": "fail",
                "issues_created": "2",
                "acceptance_criteria_count": "3",
                "pr": 303,
            }
        ]
    )
    assert verifier["issues_created"] == 2
    assert verifier["verdicts"]["fail"] == 1
    assert verifier["avg_acceptance"] == 3


def test_format_helpers_and_summary_range() -> None:
    assert aggregate_agent_metrics._format_counter(Counter()) == "n/a"
    assert aggregate_agent_metrics._format_rate(1, 0) == "n/a"

    entries = [
        {
            "metric_type": "keepalive",
            "timestamp": "2025-01-01T00:00:00Z",
            "iteration_count": 1,
            "stop_reason": "tasks-complete",
        },
        {
            "metric_type": "unknown",
            "timestamp": "2025-01-02T00:00:00Z",
        },
    ]
    summary = aggregate_agent_metrics.build_summary(entries, errors=0)
    assert "Range: 2025-01-01T00:00:00Z to 2025-01-02T00:00:00Z" in summary


def test_main_returns_error_when_no_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("METRICS_PATHS", "")
    monkeypatch.setenv("METRICS_DIR", str(tmp_path / "missing"))
    monkeypatch.setenv("OUTPUT_PATH", str(tmp_path / "summary.md"))

    exit_code = aggregate_agent_metrics.main()

    assert exit_code == 1
