import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import autopilot_metrics_collector as collector


def _step_record(success: bool = True) -> dict:
    return {
        "schema_version": collector.AUTOPILOT_METRICS_SCHEMA_VERSION,
        "metric_type": "step",
        "issue_number": 101,
        "timestamp": datetime(2025, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "cycle_count": 2,
        "step_name": "format-issue",
        "duration_ms": 4321,
        "success": success,
        "failure_reason": "none" if success else "timeout",
    }


def _cycle_record() -> dict:
    return {
        "schema_version": collector.AUTOPILOT_METRICS_SCHEMA_VERSION,
        "metric_type": "cycle",
        "issue_number": 101,
        "timestamp": datetime(2025, 1, 2, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "cycle_count": 3,
        "max_cycles": 6,
        "steps_attempted": 2,
        "steps_completed": 1,
    }


def _escalation_record() -> dict:
    return {
        "schema_version": collector.AUTOPILOT_METRICS_SCHEMA_VERSION,
        "metric_type": "escalation",
        "issue_number": 101,
        "timestamp": datetime(2025, 1, 3, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "cycle_count": 4,
        "escalation_reason": "needs-human label applied",
    }


def test_validate_record_accepts_step_payload() -> None:
    collector.validate_record(_step_record())


def test_validate_record_accepts_trace_fields() -> None:
    record = _step_record()
    record["langsmith_trace_id"] = "trace-123"
    record["langsmith_trace_url"] = "https://smith.langchain.com/r/trace-123"

    collector.validate_record(record)


def test_validate_record_rejects_blank_trace_fields() -> None:
    record = _step_record()
    record["langsmith_trace_id"] = "   "

    with pytest.raises(collector.ValidationError, match="langsmith_trace_id must be"):
        collector.validate_record(record)


def test_validate_record_accepts_cycle_payload() -> None:
    collector.validate_record(_cycle_record())


def test_validate_record_accepts_escalation_payload() -> None:
    collector.validate_record(_escalation_record())


def test_validate_record_rejects_missing_fields() -> None:
    record = _step_record()
    record.pop("step_name")

    with pytest.raises(collector.ValidationError, match="missing fields"):
        collector.validate_record(record)


def test_validate_record_rejects_invalid_metric_type() -> None:
    record = _step_record()
    record["metric_type"] = "unknown"

    with pytest.raises(collector.ValidationError, match="metric_type must be"):
        collector.validate_record(record)


def test_validate_record_rejects_missing_metric_type() -> None:
    record = _step_record()
    record["metric_type"] = None

    with pytest.raises(collector.ValidationError, match="metric_type must be set"):
        collector.validate_record(record)


def test_validate_record_rejects_non_int_schema_version() -> None:
    record = _step_record()
    record["schema_version"] = "1"

    with pytest.raises(collector.ValidationError, match="schema_version must be an integer"):
        collector.validate_record(record)


def test_validate_record_rejects_unknown_schema_version() -> None:
    record = _step_record()
    record["schema_version"] = collector.AUTOPILOT_METRICS_SCHEMA_VERSION + 1

    with pytest.raises(collector.ValidationError, match="schema_version must be"):
        collector.validate_record(record)


def test_validate_record_rejects_invalid_timestamp() -> None:
    record = _step_record()
    record["timestamp"] = "not-a-timestamp"

    with pytest.raises(collector.ValidationError, match="timestamp must be ISO 8601"):
        collector.validate_record(record)


def test_validate_record_rejects_invalid_types() -> None:
    record = _step_record()
    record["duration_ms"] = "fast"

    with pytest.raises(collector.ValidationError, match="duration_ms must be an integer"):
        collector.validate_record(record)


def test_validate_record_requires_failure_reason_on_failure() -> None:
    record = _step_record(success=False)
    record["failure_reason"] = "  "

    with pytest.raises(collector.ValidationError, match="failure_reason must be set"):
        collector.validate_record(record)


def test_validate_record_requires_none_failure_reason_on_success() -> None:
    record = _step_record(success=True)
    record["failure_reason"] = "timeout"

    with pytest.raises(collector.ValidationError, match="failure_reason must be 'none'"):
        collector.validate_record(record)


def test_validate_cycle_rejects_invalid_optional_fields() -> None:
    record = _cycle_record()
    record["steps_completed"] = "one"

    with pytest.raises(collector.ValidationError, match="steps_completed must be an integer"):
        collector.validate_record(record)


def test_coerce_bool_rejects_invalid_value() -> None:
    with pytest.raises(collector.ValidationError, match="success must be a boolean"):
        collector._coerce_bool("maybe", "success")


def test_build_record_from_args_defaults_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector, "_utc_now_iso", lambda: "2025-04-05T06:07:08Z")
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp=None,
        step_name="format-issue",
        duration_ms="1200",
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success="true",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["timestamp"] == "2025-04-05T06:07:08Z"
    assert record["schema_version"] == collector.AUTOPILOT_METRICS_SCHEMA_VERSION
    assert record["issue_number"] == 12
    assert record["failure_reason"] == "none"


def test_build_record_from_args_includes_trace_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACE_ID", "trace-456")
    monkeypatch.setenv("LANGSMITH_TRACE_URL", "https://smith.langchain.com/r/trace-456")
    args = collector.argparse.Namespace(
        metric_type="cycle",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name=None,
        duration_ms=None,
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success=None,
        failure_reason=None,
        max_cycles="5",
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["langsmith_trace_id"] == "trace-456"
    assert record["langsmith_trace_url"] == "https://smith.langchain.com/r/trace-456"


def test_build_record_from_args_derives_trace_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACE_ID", "trace-789")
    monkeypatch.delenv("LANGSMITH_TRACE_URL", raising=False)
    args = collector.argparse.Namespace(
        metric_type="cycle",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name=None,
        duration_ms=None,
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success=None,
        failure_reason=None,
        max_cycles="5",
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["langsmith_trace_id"] == "trace-789"
    assert record["langsmith_trace_url"] == "https://smith.langchain.com/r/trace-789"


def test_build_record_from_args_normalizes_failure_reason_on_success() -> None:
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms="1200",
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success="true",
        failure_reason="flaky infra",
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["failure_reason"] == "none"


def test_build_record_from_args_normalizes_blank_failure_reason_on_success() -> None:
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="42",
        cycle_count="5",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms="1200",
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success="true",
        failure_reason="   ",
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["failure_reason"] == "none"


def test_load_record_from_json_normalizes_failure_reason_on_success() -> None:
    payload = json.dumps(
        {
            "schema_version": collector.AUTOPILOT_METRICS_SCHEMA_VERSION,
            "metric_type": "STEP",
            "issue_number": 101,
            "timestamp": "2025-04-05T06:07:08Z",
            "cycle_count": 1,
            "step_name": "format-issue",
            "duration_ms": 1200,
            "success": "true",
            "failure_reason": "infra flake",
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["failure_reason"] == "none"


def test_load_record_from_json_rejects_missing_failure_reason_on_failure() -> None:
    payload = json.dumps(
        {
            "schema_version": collector.AUTOPILOT_METRICS_SCHEMA_VERSION,
            "metric_type": "step",
            "issue_number": 101,
            "timestamp": "2025-04-05T06:07:08Z",
            "cycle_count": 1,
            "step_name": "format-issue",
            "duration_ms": 1200,
            "success": False,
        }
    )

    with pytest.raises(collector.ValidationError, match="failure_reason is required"):
        collector.load_record_from_json(payload)


def test_schema_payload_contains_record_types() -> None:
    payload = json.loads(collector.schema_payload())

    assert payload["version"] == collector.AUTOPILOT_METRICS_SCHEMA_VERSION
    assert set(payload["record_types"].keys()) == {"cycle", "escalation", "step"}


def test_build_record_from_args_escalation_requires_reason() -> None:
    args = collector.argparse.Namespace(
        metric_type="escalation",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-05-06T07:08:09Z",
        step_name=None,
        duration_ms=None,
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success=None,
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    with pytest.raises(collector.ValidationError, match="escalation_reason must be"):
        collector.build_record_from_args(args)


def test_build_record_from_args_escalation_rejects_blank_reason() -> None:
    args = collector.argparse.Namespace(
        metric_type="escalation",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-05-06T07:08:09Z",
        step_name=None,
        duration_ms=None,
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success=None,
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason="   ",
    )

    with pytest.raises(collector.ValidationError, match="escalation_reason must be"):
        collector.build_record_from_args(args)


def test_build_record_from_args_requires_failure_reason_on_failure() -> None:
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms="1200",
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success="false",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    with pytest.raises(collector.ValidationError, match="failure_reason is required"):
        collector.build_record_from_args(args)


def test_load_record_from_json_defaults_schema_and_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collector, "_utc_now_iso", lambda: "2025-01-01T00:00:00Z")
    payload = json.dumps(
        {
            "metric_type": "cycle",
            "issue_number": 101,
            "cycle_count": 2,
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["schema_version"] == collector.AUTOPILOT_METRICS_SCHEMA_VERSION
    assert record["timestamp"] == "2025-01-01T00:00:00Z"
    collector.validate_record(record)


def test_load_record_from_json_defaults_null_schema_version() -> None:
    payload = json.dumps(
        {
            "schema_version": None,
            "metric_type": "cycle",
            "issue_number": 101,
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": 2,
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["schema_version"] == collector.AUTOPILOT_METRICS_SCHEMA_VERSION
    collector.validate_record(record)


def test_load_record_from_json_defaults_blank_schema_version() -> None:
    payload = json.dumps(
        {
            "schema_version": "  ",
            "metric_type": "cycle",
            "issue_number": 101,
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": 2,
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["schema_version"] == collector.AUTOPILOT_METRICS_SCHEMA_VERSION
    collector.validate_record(record)


def test_load_record_from_json_defaults_null_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collector, "_utc_now_iso", lambda: "2025-02-03T04:05:06Z")
    payload = json.dumps(
        {
            "schema_version": collector.AUTOPILOT_METRICS_SCHEMA_VERSION,
            "metric_type": "cycle",
            "issue_number": 101,
            "timestamp": None,
            "cycle_count": 2,
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["timestamp"] == "2025-02-03T04:05:06Z"
    collector.validate_record(record)


def test_load_record_from_json_defaults_blank_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collector, "_utc_now_iso", lambda: "2025-02-03T04:05:06Z")
    payload = json.dumps(
        {
            "schema_version": collector.AUTOPILOT_METRICS_SCHEMA_VERSION,
            "metric_type": "cycle",
            "issue_number": 101,
            "timestamp": "   ",
            "cycle_count": 2,
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["timestamp"] == "2025-02-03T04:05:06Z"
    collector.validate_record(record)


def test_load_record_from_json_normalizes_metric_type() -> None:
    payload = json.dumps(
        {
            "metric_type": " Step ",
            "issue_number": 101,
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": 2,
            "step_name": "format-issue",
            "duration_ms": 1200,
            "success": True,
            "failure_reason": "none",
            "schema_version": collector.AUTOPILOT_METRICS_SCHEMA_VERSION,
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["metric_type"] == "step"
    collector.validate_record(record)


def test_load_record_from_json_coerces_int_fields() -> None:
    payload = json.dumps(
        {
            "schema_version": "1",
            "metric_type": "step",
            "issue_number": "101",
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": "2",
            "step_name": "format-issue",
            "duration_ms": "1200",
            "success": True,
            "failure_reason": "none",
            "max_cycles": "6",
            "steps_attempted": "4",
            "steps_completed": "3",
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["schema_version"] == 1
    assert record["issue_number"] == 101
    assert record["cycle_count"] == 2
    assert record["duration_ms"] == 1200
    assert record["max_cycles"] == 6
    assert record["steps_attempted"] == 4
    assert record["steps_completed"] == 3
    collector.validate_record(record)


def test_load_record_from_json_coerces_success_flag() -> None:
    payload = json.dumps(
        {
            "schema_version": "1",
            "metric_type": "step",
            "issue_number": "101",
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": "2",
            "step_name": "format-issue",
            "duration_ms": "1200",
            "success": "true",
            "failure_reason": "none",
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["success"] is True
    collector.validate_record(record)


def test_load_record_from_json_rejects_invalid_success_flag() -> None:
    payload = json.dumps(
        {
            "schema_version": "1",
            "metric_type": "step",
            "issue_number": "101",
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": "2",
            "step_name": "format-issue",
            "duration_ms": "1200",
            "success": "maybe",
            "failure_reason": "none",
        }
    )

    with pytest.raises(collector.ValidationError, match="success must be a boolean"):
        collector.load_record_from_json(payload)


def test_load_record_from_json_defaults_failure_reason_for_success() -> None:
    payload = json.dumps(
        {
            "schema_version": "1",
            "metric_type": "step",
            "issue_number": "101",
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": "2",
            "step_name": "format-issue",
            "duration_ms": "1200",
            "success": "true",
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["failure_reason"] == "none"
    collector.validate_record(record)


def test_load_record_from_json_derives_trace_url() -> None:
    payload = json.dumps(
        {
            "schema_version": "1",
            "metric_type": "cycle",
            "issue_number": "101",
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": "2",
            "langsmith_trace_id": "trace-999",
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["langsmith_trace_id"] == "trace-999"
    assert record["langsmith_trace_url"] == "https://smith.langchain.com/r/trace-999"
    collector.validate_record(record)


def test_load_record_from_json_normalizes_blank_failure_reason_on_success() -> None:
    payload = json.dumps(
        {
            "schema_version": "1",
            "metric_type": "step",
            "issue_number": "101",
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": "2",
            "step_name": "format-issue",
            "duration_ms": "1200",
            "success": "true",
            "failure_reason": "   ",
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["failure_reason"] == "none"
    collector.validate_record(record)


def test_load_record_from_json_coerces_and_normalizes_failure_reason_on_success() -> None:
    payload = json.dumps(
        {
            "schema_version": "1",
            "metric_type": "step",
            "issue_number": "101",
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": "2",
            "step_name": "format-issue",
            "duration_ms": "1200",
            "success": "true",
            "failure_reason": "infra flaky",
        }
    )

    record = collector.load_record_from_json(payload)

    assert record["failure_reason"] == "none"
    collector.validate_record(record)


def test_load_record_from_json_requires_failure_reason_on_failure() -> None:
    payload = json.dumps(
        {
            "schema_version": "1",
            "metric_type": "step",
            "issue_number": "101",
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": "2",
            "step_name": "format-issue",
            "duration_ms": "1200",
            "success": "false",
        }
    )

    with pytest.raises(collector.ValidationError, match="failure_reason is required"):
        collector.load_record_from_json(payload)


def test_load_record_from_json_rejects_blank_failure_reason_on_failure() -> None:
    payload = json.dumps(
        {
            "schema_version": "1",
            "metric_type": "step",
            "issue_number": "101",
            "timestamp": "2025-01-01T00:00:00Z",
            "cycle_count": "2",
            "step_name": "format-issue",
            "duration_ms": "1200",
            "success": "false",
            "failure_reason": "   ",
        }
    )

    with pytest.raises(collector.ValidationError, match="failure_reason is required"):
        collector.load_record_from_json(payload)


def test_build_record_from_args_computes_duration_from_bounds() -> None:
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms=None,
        started_at="2025-04-05T06:07:00Z",
        ended_at="2025-04-05T06:07:01Z",
        started_at_ms=None,
        ended_at_ms=None,
        success="true",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["duration_ms"] == 1000


def test_build_record_from_args_uses_now_for_missing_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector, "_utc_now_iso", lambda: "2025-04-05T06:07:01Z")
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms=None,
        started_at="2025-04-05T06:07:00Z",
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success="true",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["duration_ms"] == 1000


def test_build_record_from_args_rejects_missing_bounds() -> None:
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms=None,
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success="true",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    with pytest.raises(collector.ValidationError, match="duration_ms is required unless"):
        collector.build_record_from_args(args)


def test_build_record_from_args_rejects_negative_bounds() -> None:
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms=None,
        started_at="2025-04-05T06:07:02Z",
        ended_at="2025-04-05T06:07:01Z",
        started_at_ms=None,
        ended_at_ms=None,
        success="true",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    with pytest.raises(collector.ValidationError, match="ended_at must be after started_at"):
        collector.build_record_from_args(args)


def test_build_record_from_args_computes_duration_from_epoch_bounds() -> None:
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms=None,
        started_at=None,
        ended_at=None,
        started_at_ms="1000",
        ended_at_ms="4000",
        success="true",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["duration_ms"] == 3000


def test_build_record_from_args_uses_epoch_env_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPILOT_STEP_STARTED_AT_MS", "1000")
    monkeypatch.setenv("AUTOPILOT_STEP_ENDED_AT_MS", "4500")
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms=None,
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success="true",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["duration_ms"] == 3500


def test_build_record_from_args_uses_iso_env_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPILOT_STEP_STARTED_AT", "2025-04-05T06:07:00Z")
    monkeypatch.setenv("AUTOPILOT_STEP_ENDED_AT", "2025-04-05T06:07:02Z")
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms=None,
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success="true",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["duration_ms"] == 2000


def test_build_record_from_args_normalizes_failure_reason_env_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPILOT_FAILURE_REASON", "pipeline error")
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms="1200",
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success="true",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["failure_reason"] == "none"


def test_build_record_from_args_uses_failure_reason_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPILOT_FAILURE_REASON", "pipeline error")
    args = collector.argparse.Namespace(
        metric_type="step",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-04-05T06:07:08Z",
        step_name="format-issue",
        duration_ms="1200",
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success="false",
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["failure_reason"] == "pipeline error"


def test_build_record_from_args_uses_escalation_reason_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPILOT_ESCALATION_REASON", "manual review required")
    args = collector.argparse.Namespace(
        metric_type="escalation",
        issue_number="12",
        cycle_count="3",
        timestamp="2025-05-06T07:08:09Z",
        step_name=None,
        duration_ms=None,
        started_at=None,
        ended_at=None,
        started_at_ms=None,
        ended_at_ms=None,
        success=None,
        failure_reason=None,
        max_cycles=None,
        steps_attempted=None,
        steps_completed=None,
        escalation_reason=None,
    )

    record = collector.build_record_from_args(args)

    assert record["escalation_reason"] == "manual review required"


def test_append_record_appends_lines(tmp_path: Path) -> None:
    record = _step_record()
    path = tmp_path / "metrics.ndjson"

    collector.append_record(path, record)
    collector.append_record(path, record)

    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert lines[0] == lines[1]


def test_load_record_from_json_adds_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector, "_utc_now_iso", lambda: "2025-06-07T08:09:10Z")

    record = collector.load_record_from_json(
        '{"metric_type": "cycle", "issue_number": 1, "cycle_count": 1}'
    )

    assert record["schema_version"] == collector.AUTOPILOT_METRICS_SCHEMA_VERSION
    assert record["timestamp"] == "2025-06-07T08:09:10Z"


def test_load_record_from_json_rejects_invalid_payloads() -> None:
    with pytest.raises(collector.ValidationError, match="record_json must be valid JSON"):
        collector.load_record_from_json("{")

    with pytest.raises(collector.ValidationError, match="record_json must decode to an object"):
        collector.load_record_from_json('["list"]')


def test_main_writes_record_to_stdout_and_log(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    log_path = tmp_path / "metrics.ndjson"
    exit_code = collector.main(
        [
            "--path",
            str(log_path),
            "--metric-type",
            "step",
            "--issue-number",
            "12",
            "--cycle-count",
            "1",
            "--step-name",
            "format",
            "--duration-ms",
            "1200",
            "--success",
            "true",
        ]
    )

    assert exit_code == 0
    stdout = capsys.readouterr().out.strip()
    assert stdout
    log_contents = log_path.read_text(encoding="utf-8").strip()
    assert log_contents == stdout
    record = json.loads(stdout)
    collector.validate_record(record)


def test_main_writes_failure_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.ndjson"
    monkeypatch.setenv("AUTOPILOT_METRICS_SUMMARY_PATH", str(summary_path))
    monkeypatch.setenv("AUTOPILOT_STEP_NAME", "format")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")

    exit_code = collector.main(
        [
            "--metric-type",
            "step",
            "--issue-number",
            "12",
            "--cycle-count",
            "1",
            "--step-name",
            "format",
            "--success",
            "true",
        ]
    )

    assert exit_code == 1
    summary_lines = summary_path.read_text(encoding="utf-8").splitlines()
    assert len(summary_lines) == 1
    summary = json.loads(summary_lines[0])
    assert summary["summary_type"] == "autopilot-metrics-error"
    assert summary["component"] == "autopilot_metrics_collector"
    assert summary["step_name"] == "format"
    assert summary["error_category"] == "validation_error"
    assert summary["exit_code"] == 1
    assert summary["environment"]["github_run_id"] == "12345"
