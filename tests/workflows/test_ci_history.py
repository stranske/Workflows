from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import ci_history, ci_metrics


def _write_sample_junit(tmp_path: Path) -> Path:
    junit_xml = """
    <testsuite name="pytest" tests="3" failures="1" errors="1" skipped="0" time="3.1">
      <testcase classname="pkg.mod" name="test_pass" time="0.4" />
      <testcase classname="pkg.mod" name="test_failure" time="1.2">
        <failure message="expected 1 == 2" type="AssertionError">assertion details</failure>
      </testcase>
      <testcase classname="pkg.mod" name="test_error" time="0.3">
        <error message="boom" type="ValueError">call stack</error>
      </testcase>
    </testsuite>
    """.strip()
    junit_path = tmp_path / "pytest-junit.xml"
    junit_path.write_text(junit_xml, encoding="utf-8")
    return junit_path


def test_ci_history_appends_record_and_classification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    junit_path = _write_sample_junit(tmp_path)
    metrics_path = tmp_path / "ci-metrics.json"
    metrics_payload = ci_metrics.build_metrics(junit_path)
    metrics_path.write_text(json.dumps(metrics_payload), encoding="utf-8")

    history_path = tmp_path / "metrics-history.ndjson"
    classification_path = tmp_path / "classification.json"

    monkeypatch.setenv("JUNIT_PATH", str(junit_path))
    monkeypatch.setenv("METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("ENABLE_CLASSIFICATION", "true")
    monkeypatch.setenv("CLASSIFICATION_OUT", str(classification_path))

    try:
        exit_code = ci_history.main()
    finally:
        for key in [
            "JUNIT_PATH",
            "METRICS_PATH",
            "HISTORY_PATH",
            "ENABLE_CLASSIFICATION",
            "CLASSIFICATION_OUT",
        ]:
            monkeypatch.delenv(key, raising=False)

    assert exit_code == 0

    lines = history_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["summary"]["tests"] == 3
    assert record["metrics_path"] == str(metrics_path)

    classification = json.loads(classification_path.read_text(encoding="utf-8"))
    assert classification["total"] == 2
    assert classification["counts"] == {"failure": 1, "error": 1}
    assert {entry["status"] for entry in classification["entries"]} == {
        "failure",
        "error",
    }


def test_ci_history_generates_metrics_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    junit_path = _write_sample_junit(tmp_path)
    history_path = tmp_path / "metrics-history.ndjson"

    monkeypatch.setenv("JUNIT_PATH", str(junit_path))
    monkeypatch.setenv("METRICS_PATH", str(tmp_path / "absent.json"))
    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("ENABLE_CLASSIFICATION", "false")

    try:
        exit_code = ci_history.main()
    finally:
        for key in [
            "JUNIT_PATH",
            "METRICS_PATH",
            "HISTORY_PATH",
            "ENABLE_CLASSIFICATION",
        ]:
            monkeypatch.delenv(key, raising=False)

    assert exit_code == 0
    record = json.loads(history_path.read_text(encoding="utf-8").strip())
    assert record["summary"]["tests"] == 3
    assert "metrics_path" not in record


def test_load_metrics_falls_back_on_invalid_json(tmp_path: Path) -> None:
    junit_path = _write_sample_junit(tmp_path)
    metrics_path = tmp_path / "corrupt.json"
    metrics_path.write_text("not-json", encoding="utf-8")

    data, from_file = ci_history._load_metrics(junit_path, metrics_path)

    assert from_file is False
    assert data["summary"]["tests"] == 3


def test_build_history_record_enriches_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = {
        "summary": {"tests": 10},
        "failures": [
            {
                "status": "failure",
                "nodeid": "tests/test_mod.py::test_sample",
                "message": "boom",
                "type": "AssertionError",
                "time": 1.23,
            }
        ],
        "slow_tests": {"threshold_seconds": 0.5, "limit": 1, "items": []},
    }
    junit_path = Path("/tmp/junit.xml")
    metrics_path = Path("/tmp/ci-metrics.json")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "7")
    monkeypatch.setenv("GITHUB_SHA", "deadbeef")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")

    record = ci_history._build_history_record(
        metrics,
        junit_path=junit_path,
        metrics_path=metrics_path,
        metrics_from_file=True,
    )

    assert record["metrics_path"] == str(metrics_path)
    assert record["github"] == {
        "github_run_id": "42",
        "github_run_number": "7",
        "github_sha": "deadbeef",
        "github_ref": "refs/heads/main",
    }
    assert record["slow_tests"]["threshold_seconds"] == 0.5

    for key in [
        "GITHUB_RUN_ID",
        "GITHUB_RUN_NUMBER",
        "GITHUB_SHA",
        "GITHUB_REF",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_ci_history_missing_junit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    junit_path = tmp_path / "missing.xml"
    history_path = tmp_path / "metrics-history.ndjson"

    monkeypatch.setenv("JUNIT_PATH", str(junit_path))
    monkeypatch.setenv("HISTORY_PATH", str(history_path))

    try:
        exit_code = ci_history.main()
    finally:
        monkeypatch.delenv("JUNIT_PATH", raising=False)
        monkeypatch.delenv("HISTORY_PATH", raising=False)

    assert exit_code == 1
    assert not history_path.exists()


def test_main_handles_load_metrics_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    junit_path = _write_sample_junit(tmp_path)
    history_path = tmp_path / "metrics-history.ndjson"

    monkeypatch.setenv("JUNIT_PATH", str(junit_path))
    monkeypatch.setenv("HISTORY_PATH", str(history_path))

    monkeypatch.setenv("METRICS_PATH", str(tmp_path / "ci-metrics.json"))

    def raise_missing(*_args, **_kwargs):
        raise FileNotFoundError("bad")

    monkeypatch.setattr(ci_history, "_load_metrics", raise_missing)

    try:
        exit_code = ci_history.main()
    finally:
        for key in ["JUNIT_PATH", "HISTORY_PATH", "METRICS_PATH"]:
            monkeypatch.delenv(key, raising=False)

    assert exit_code == 1
    assert not history_path.exists()


def test_main_removes_existing_classification_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    junit_path = _write_sample_junit(tmp_path)
    metrics_payload = ci_metrics.build_metrics(junit_path)
    metrics_path = tmp_path / "ci-metrics.json"
    metrics_path.write_text(json.dumps(metrics_payload), encoding="utf-8")

    history_path = tmp_path / "metrics-history.ndjson"
    classification_path = tmp_path / "classification.json"
    classification_path.write_text("old", encoding="utf-8")

    monkeypatch.setenv("JUNIT_PATH", str(junit_path))
    monkeypatch.setenv("METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("ENABLE_CLASSIFICATION", "false")
    monkeypatch.setenv("CLASSIFICATION_OUT", str(classification_path))

    try:
        exit_code = ci_history.main()
    finally:
        for key in [
            "JUNIT_PATH",
            "METRICS_PATH",
            "HISTORY_PATH",
            "ENABLE_CLASSIFICATION",
            "CLASSIFICATION_OUT",
        ]:
            monkeypatch.delenv(key, raising=False)

    assert exit_code == 0
    assert not classification_path.exists()
