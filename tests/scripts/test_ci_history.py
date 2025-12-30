import json
from pathlib import Path

import pytest

from scripts import ci_history


def test_truthy_accepts_common_values() -> None:
    assert ci_history._truthy("1") is True
    assert ci_history._truthy("true") is True
    assert ci_history._truthy("YES") is True
    assert ci_history._truthy("on") is True
    assert ci_history._truthy("0") is False
    assert ci_history._truthy(None) is False


def test_load_metrics_prefers_existing_file(tmp_path: Path) -> None:
    junit_path = tmp_path / "pytest-junit.xml"
    junit_path.write_text("<testsuite />", encoding="utf-8")
    metrics_path = tmp_path / "ci-metrics.json"
    payload = {"summary": {"tests": 1}}
    metrics_path.write_text(json.dumps(payload), encoding="utf-8")

    metrics, from_file = ci_history._load_metrics(junit_path, metrics_path)

    assert metrics == payload
    assert from_file is True


def test_load_metrics_falls_back_to_builder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    junit_path = tmp_path / "pytest-junit.xml"
    junit_path.write_text("<testsuite />", encoding="utf-8")
    metrics_path = tmp_path / "ci-metrics.json"
    metrics_path.write_text("not-json", encoding="utf-8")

    expected = {"summary": {"tests": 2}}

    def fake_build_metrics(path: Path) -> dict:
        assert path == junit_path
        return expected

    monkeypatch.setattr(ci_history.ci_metrics, "build_metrics", fake_build_metrics)

    metrics, from_file = ci_history._load_metrics(junit_path, metrics_path)

    assert metrics == expected
    assert from_file is False


def test_build_history_record_includes_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metrics = {"summary": {"tests": 3}, "failures": [{"nodeid": "x"}], "slow_tests": {}}
    junit_path = tmp_path / "pytest-junit.xml"
    metrics_path = tmp_path / "ci-metrics.json"

    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", "abc")

    record = ci_history._build_history_record(
        metrics,
        junit_path=junit_path,
        metrics_path=metrics_path,
        metrics_from_file=True,
    )

    assert record["summary"] == metrics["summary"]
    assert record["failures"] == metrics["failures"]
    assert record["junit_path"] == str(junit_path)
    assert record["metrics_path"] == str(metrics_path)
    assert record["timestamp"].endswith("Z")
    assert record["github"]["github_run_id"] == "123"
    assert record["github"]["github_sha"] == "abc"


def test_build_classification_payload_counts_statuses() -> None:
    metrics = {
        "failures": [
            {"status": "failure", "nodeid": "a"},
            {"status": "error", "nodeid": "b"},
            {"status": "failure", "nodeid": "c"},
        ]
    }

    payload = ci_history._build_classification_payload(metrics)

    assert payload["total"] == 3
    assert payload["counts"] == {"failure": 2, "error": 1}
    assert payload["timestamp"].endswith("Z")
    assert payload["entries"][0]["nodeid"] == "a"
