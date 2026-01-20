from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import metrics_alerting


def _build_thresholds() -> dict:
    return {
        "thresholds": {
            "success_rate": {
                "warning": 0.95,
                "critical": 0.9,
                "window_days": 7,
                "min_runs": 2,
            },
            "duration_ms": {
                "p95_warning": 800,
                "p95_critical": 900,
                "window_days": 7,
                "min_runs": 2,
            },
            "token_usage": {
                "p95_warning": 1000,
                "p95_critical": 2000,
                "window_days": 7,
                "min_runs": 2,
            },
        },
        "issue_labels": ["metrics", "alert"],
    }


def test_build_alerts_success_rate_warning() -> None:
    thresholds = _build_thresholds()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    entries = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "summary": {"passed": 92, "tests": 100},
        },
        {
            "timestamp": "2026-01-01T01:00:00Z",
            "summary": {"passed": 46, "tests": 50},
        },
    ]

    alerts = metrics_alerting.build_alerts(entries, thresholds, now=now)

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.metric == "success_rate"
    assert alert.severity == "warning"
    assert alert.sample_count == 2


def test_build_alerts_duration_p95_critical() -> None:
    thresholds = _build_thresholds()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    entries = [
        {"timestamp": "2026-01-01T00:00:00Z", "duration_ms": 500},
        {"timestamp": "2026-01-01T01:00:00Z", "duration_ms": 600},
        {"timestamp": "2026-01-01T02:00:00Z", "duration_ms": 1000},
    ]

    alerts = metrics_alerting.build_alerts(entries, thresholds, now=now)

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.metric == "duration_ms"
    assert alert.severity == "critical"
    assert alert.sample_count == 3


def test_append_alert_history(tmp_path: Path) -> None:
    alert = metrics_alerting.Alert(
        metric="token_usage",
        severity="warning",
        value=1234.0,
        threshold=1000.0,
        window_days=7,
        min_runs=2,
        sample_count=3,
        alert_key="metrics_alert:token_usage",
        details={},
    )
    history_path = tmp_path / "metrics-history.ndjson"
    now = datetime(2026, 1, 1, tzinfo=UTC)

    metrics_alerting._append_alert_history(
        history_path,
        alert,
        issue_url="https://example.com/issue/1",
        issue_number=1,
        issue_status="created",
        now=now,
    )

    line = history_path.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["metric_type"] == "alert"
    assert record["alert_key"] == "metrics_alert:token_usage"
    assert record["issue"]["status"] == "created"


def test_main_creates_issue_and_records_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    thresholds = _build_thresholds()
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps(thresholds), encoding="utf-8")
    metrics_path = tmp_path / "metrics.ndjson"
    now = datetime.now(UTC)
    metrics_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": now.isoformat().replace("+00:00", "Z"),
                        "summary": {"passed": 92, "tests": 100},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": now.isoformat().replace("+00:00", "Z"),
                        "summary": {"passed": 46, "tests": 50},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    history_path = tmp_path / "history.ndjson"

    created = {}

    def fake_create_issue(repo, token, title, body, labels):
        created["repo"] = repo
        created["token"] = token
        created["title"] = title
        created["body"] = body
        created["labels"] = labels
        return {"html_url": "https://example.com/issue/1", "number": 1}

    monkeypatch.setattr(metrics_alerting.api_client, "create_issue", fake_create_issue)
    monkeypatch.setattr(
        metrics_alerting.duplicate_detection, "find_source_issue", lambda *_args, **_kwargs: None
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "octo/test")
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    exit_code = metrics_alerting.main(
        [
            "--metrics-path",
            str(metrics_path),
            "--thresholds-path",
            str(thresholds_path),
            "--alert-history-path",
            str(history_path),
        ]
    )

    assert exit_code == 0
    assert created["labels"] == ["metrics", "alert"]
    assert "Metrics alert:" in created["title"]
    history_entries = history_path.read_text(encoding="utf-8").strip().splitlines()
    assert history_entries


def test_main_dedup_skips_issue_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    thresholds = _build_thresholds()
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps(thresholds), encoding="utf-8")
    metrics_path = tmp_path / "metrics.ndjson"
    now = datetime.now(UTC)
    metrics_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": now.isoformat().replace("+00:00", "Z"),
                        "summary": {"passed": 92, "tests": 100},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": now.isoformat().replace("+00:00", "Z"),
                        "summary": {"passed": 46, "tests": 50},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    history_path = tmp_path / "history.ndjson"

    def fake_create_issue(*_args, **_kwargs):
        raise AssertionError("create_issue should not be called when deduped")

    monkeypatch.setattr(metrics_alerting.api_client, "create_issue", fake_create_issue)
    monkeypatch.setattr(
        metrics_alerting.duplicate_detection,
        "find_source_issue",
        lambda *_args, **_kwargs: metrics_alerting.duplicate_detection.SourceIssue(
            number=1,
            title="Metrics alert: success_rate warning",
            body=None,
            url="https://example.com/issue/1",
        ),
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "octo/test")
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    exit_code = metrics_alerting.main(
        [
            "--metrics-path",
            str(metrics_path),
            "--thresholds-path",
            str(thresholds_path),
            "--alert-history-path",
            str(history_path),
        ]
    )

    assert exit_code == 0
    history_entries = history_path.read_text(encoding="utf-8").strip().splitlines()
    assert history_entries


def test_main_sends_slack_notification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    thresholds = _build_thresholds()
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps(thresholds), encoding="utf-8")
    metrics_path = tmp_path / "metrics.ndjson"
    now = datetime.now(UTC)
    metrics_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": now.isoformat().replace("+00:00", "Z"),
                        "summary": {"passed": 92, "tests": 100},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": now.isoformat().replace("+00:00", "Z"),
                        "summary": {"passed": 46, "tests": 50},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    history_path = tmp_path / "history.ndjson"

    monkeypatch.setattr(metrics_alerting.api_client, "create_issue", lambda *_: {})
    monkeypatch.setattr(
        metrics_alerting.duplicate_detection, "find_source_issue", lambda *_args, **_kwargs: None
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "octo/test")
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    called = {}

    def fake_slack(webhook, alerts, issue_urls):
        called["webhook"] = webhook
        called["count"] = len(alerts)
        called["urls"] = issue_urls

    monkeypatch.setattr(metrics_alerting, "_send_slack_notification", fake_slack)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.com/hook")

    exit_code = metrics_alerting.main(
        [
            "--metrics-path",
            str(metrics_path),
            "--thresholds-path",
            str(thresholds_path),
            "--alert-history-path",
            str(history_path),
        ]
    )

    assert exit_code == 0
    assert called["webhook"] == "https://example.com/hook"
