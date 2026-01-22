import json
from pathlib import Path

from scripts import autopilot_metrics


def _read_record(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def test_print_schema_outputs_json(capsys) -> None:
    exit_code = autopilot_metrics.main(["print-schema"])

    assert exit_code == 0
    captured = capsys.readouterr().out.strip()
    schema = json.loads(captured)
    assert schema["version"] >= 1
    assert "record_types" in schema


def test_emit_step_writes_record(tmp_path: Path) -> None:
    log_path = tmp_path / "metrics.ndjson"

    exit_code = autopilot_metrics.main(
        [
            "emit-step",
            "--issue",
            "12",
            "--cycle",
            "3",
            "--step",
            "format",
            "--duration-ms",
            "1500",
            "--success",
            "true",
            "--path",
            str(log_path),
        ]
    )

    assert exit_code == 0
    record = _read_record(log_path)
    assert record["metric_type"] == "step"
    assert record["issue_number"] == 12
    assert record["cycle_count"] == 3
    assert record["step_name"] == "format"
    assert record["duration_ms"] == 1500
    assert record["success"] is True
    assert record["failure_reason"] == "none"


def test_emit_cycle_start_writes_record(tmp_path: Path) -> None:
    log_path = tmp_path / "cycle.ndjson"

    exit_code = autopilot_metrics.main(
        [
            "emit-cycle-start",
            "--issue",
            "21",
            "--cycle",
            "2",
            "--path",
            str(log_path),
        ]
    )

    assert exit_code == 0
    record = _read_record(log_path)
    assert record["metric_type"] == "cycle"
    assert record["issue_number"] == 21
    assert record["cycle_count"] == 2
    assert record["cycle_event"] == "start"


def test_emit_cycle_end_writes_record(tmp_path: Path) -> None:
    log_path = tmp_path / "cycle_end.ndjson"

    exit_code = autopilot_metrics.main(
        [
            "emit-cycle-end",
            "--issue",
            "21",
            "--cycle",
            "3",
            "--path",
            str(log_path),
        ]
    )

    assert exit_code == 0
    record = _read_record(log_path)
    assert record["metric_type"] == "cycle"
    assert record["issue_number"] == 21
    assert record["cycle_count"] == 3
    assert record["cycle_event"] == "end"


def test_emit_escalation_writes_record(tmp_path: Path) -> None:
    log_path = tmp_path / "escalation.ndjson"

    exit_code = autopilot_metrics.main(
        [
            "emit-escalation",
            "--issue",
            "99",
            "--cycle",
            "5",
            "--reason",
            "needs-human label applied",
            "--path",
            str(log_path),
        ]
    )

    assert exit_code == 0
    record = _read_record(log_path)
    assert record["metric_type"] == "escalation"
    assert record["issue_number"] == 99
    assert record["cycle_count"] == 5
    assert record["escalation_reason"] == "needs-human label applied"


def test_emit_summary_writes_record(tmp_path: Path) -> None:
    log_path = tmp_path / "summary.ndjson"

    exit_code = autopilot_metrics.main(
        [
            "emit-summary",
            "--issue",
            "44",
            "--total-cycles",
            "7",
            "--outcome",
            "completed",
            "--path",
            str(log_path),
        ]
    )

    assert exit_code == 0
    record = _read_record(log_path)
    assert record["metric_type"] == "cycle"
    assert record["issue_number"] == 44
    assert record["cycle_count"] == 7
    assert record["summary"] is True
    assert record["outcome"] == "completed"


def test_emit_cycle_start_rejects_non_integer_issue(capsys, tmp_path: Path) -> None:
    log_path = tmp_path / "cycle.ndjson"

    exit_code = autopilot_metrics.main(
        [
            "emit-cycle-start",
            "--issue",
            "nope",
            "--cycle",
            "2",
            "--path",
            str(log_path),
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "issue must be an integer" in stderr


def test_emit_summary_rejects_non_integer_total_cycles(capsys, tmp_path: Path) -> None:
    log_path = tmp_path / "summary.ndjson"

    exit_code = autopilot_metrics.main(
        [
            "emit-summary",
            "--issue",
            "44",
            "--total-cycles",
            "not-a-number",
            "--outcome",
            "completed",
            "--path",
            str(log_path),
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "total_cycles must be an integer" in stderr


def test_emit_cycle_start_rejects_non_integer_max_cycles(capsys, tmp_path: Path) -> None:
    log_path = tmp_path / "cycle.ndjson"

    exit_code = autopilot_metrics.main(
        [
            "emit-cycle-start",
            "--issue",
            "21",
            "--cycle",
            "2",
            "--max-cycles",
            "nope",
            "--path",
            str(log_path),
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "max_cycles must be an integer" in stderr


def test_emit_summary_rejects_non_integer_steps_completed(capsys, tmp_path: Path) -> None:
    log_path = tmp_path / "summary.ndjson"

    exit_code = autopilot_metrics.main(
        [
            "emit-summary",
            "--issue",
            "44",
            "--total-cycles",
            "7",
            "--outcome",
            "completed",
            "--steps-completed",
            "nope",
            "--path",
            str(log_path),
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "steps_completed must be an integer" in stderr
