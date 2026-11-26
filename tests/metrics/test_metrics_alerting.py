from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

metrics_alerting = importlib.import_module("scripts.metrics_alerting")


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
    now = datetime(2026, 1, 1, 2, tzinfo=UTC)
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
    now = datetime(2026, 1, 1, 3, tzinfo=UTC)
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


def test_main_dedup_skips_issue_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_main_sends_slack_notification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert called["count"] == 1
    assert called["urls"] == [""]


def test_safe_numeric_coercions_reject_nonfinite_and_lossy_values() -> None:
    class OverflowingInt:
        def __int__(self) -> int:
            raise OverflowError

    assert metrics_alerting._safe_float(" 2.5 ") == 2.5
    for invalid in (
        None,
        "",
        True,
        "bad",
        "nan",
        "inf",
        float("-inf"),
        10**400,
        object(),
    ):
        assert metrics_alerting._safe_float(invalid) is None

    assert metrics_alerting._safe_int("4") == 4
    assert metrics_alerting._safe_int(4.0) == 4
    for invalid in (
        None,
        "",
        True,
        False,
        3.5,
        float("inf"),
        "3.5",
        object(),
        OverflowingInt(),
    ):
        assert metrics_alerting._safe_int(invalid) is None


def test_parse_timestamp_normalizes_supported_values_and_rejects_invalid_ones() -> None:
    aware = datetime(2026, 1, 2, tzinfo=UTC)
    naive = datetime(2026, 1, 2)

    assert metrics_alerting._parse_timestamp(aware) is aware
    assert metrics_alerting._parse_timestamp(naive) == aware
    assert metrics_alerting._parse_timestamp("2026-01-02T00:00:00Z") == aware
    assert metrics_alerting._parse_timestamp("2026-01-02T00:00:00") == aware
    assert metrics_alerting._parse_timestamp(None) is None
    assert metrics_alerting._parse_timestamp(42) is None
    assert metrics_alerting._parse_timestamp(" ") is None
    assert metrics_alerting._parse_timestamp("not-a-time") is None


def test_filter_recent_entries_uses_a_bounded_inclusive_window() -> None:
    now = datetime(2026, 1, 8, tzinfo=UTC)
    cutoff = now - timedelta(days=7)
    at_cutoff = {"timestamp": cutoff.isoformat(), "name": "cutoff"}
    at_now = {"timestamp": now.isoformat(), "name": "now"}
    entries = [
        {"timestamp": (cutoff - timedelta(seconds=1)).isoformat(), "name": "old"},
        at_cutoff,
        at_now,
        {"timestamp": (now + timedelta(seconds=1)).isoformat(), "name": "future"},
        {"timestamp": "invalid", "name": "invalid"},
    ]

    assert metrics_alerting._filter_recent_entries(entries, window_days=7, now=now) == [
        at_cutoff,
        at_now,
    ]


def test_extract_success_rate_accepts_each_supported_shape() -> None:
    assert metrics_alerting._extract_success_rate({"summary": {"passed": 3, "tests": 4}}) == (
        0.75,
        3,
        4,
    )
    assert metrics_alerting._extract_success_rate(
        {"summary": {"passed": None, "tests": 4, "successes": 2, "total": 5}}
    ) == (0.4, 2, 5)
    assert metrics_alerting._extract_success_rate({"summary": {"success_rate": 92}}) == (
        0.92,
        None,
        None,
    )
    assert metrics_alerting._extract_success_rate({"summary": {"success_rate": 0.8}}) == (
        0.8,
        None,
        None,
    )
    assert metrics_alerting._extract_success_rate(
        {"summary": {"success_rate": "invalid"}, "success_rate": 0.7}
    ) == (0.7, None, None)
    assert metrics_alerting._extract_success_rate({"success_rate": "0.8"}) == (
        0.8,
        None,
        None,
    )
    assert metrics_alerting._extract_success_rate({"successes": 4, "total": 5}) == (
        0.8,
        4,
        5,
    )
    assert metrics_alerting._extract_success_rate({"summary": "invalid"}) == (None, None, None)


def test_extract_duration_uses_documented_precedence_and_seconds_conversion() -> None:
    assert (
        metrics_alerting._extract_duration_ms({"duration_ms": 5, "summary": {"duration_ms": 10}})
        == 5
    )
    assert metrics_alerting._extract_duration_ms({"summary": {"duration_ms": "10"}}) == 10
    assert metrics_alerting._extract_duration_ms({"summary": {"duration_seconds": 1.5}}) == 1500
    assert metrics_alerting._extract_duration_ms({"duration_seconds": 2}) == 2000
    assert metrics_alerting._extract_duration_ms({}) is None


def test_extract_token_usage_handles_totals_components_and_scalars() -> None:
    assert (
        metrics_alerting._extract_token_usage({"summary": {"token_usage": {"total_tokens": "12"}}})
        == 12
    )
    assert (
        metrics_alerting._extract_token_usage(
            {
                "token_usage": {
                    "total_tokens": None,
                    "input_tokens": 3,
                    "output_tokens": 4,
                    "reasoning_tokens": 5,
                    "prompt_tokens": None,
                    "completion_tokens": "",
                }
            }
        )
        == 12
    )
    assert (
        metrics_alerting._extract_token_usage(
            {"token_usage": {"input_tokens": float("nan"), "output_tokens": 10}}
        )
        is None
    )
    assert (
        metrics_alerting._extract_token_usage(
            {"token_usage": {"input_tokens": 10**400, "output_tokens": 10}}
        )
        is None
    )
    assert (
        metrics_alerting._extract_token_usage(
            {"token_usage": {"input_tokens": 1e308, "output_tokens": 1e308}}
        )
        is None
    )
    assert (
        metrics_alerting._extract_token_usage(
            {"token_usage": {"total_tokens": "bad", "input_tokens": 3}}
        )
        is None
    )
    assert metrics_alerting._extract_token_usage({"token_usage_total": "7"}) == 7
    assert metrics_alerting._extract_token_usage({"token_usage": "8"}) == 8
    assert metrics_alerting._extract_token_usage({"token_usage": {"other": 1}}) is None
    assert metrics_alerting._extract_token_usage({}) is None


def test_compute_success_rate_covers_weighted_average_and_empty_inputs() -> None:
    weighted = metrics_alerting._compute_success_rate(
        [
            {"summary": {"passed": 2, "tests": 4}},
            {"summary": {"passed": 3, "tests": 6}},
        ]
    )
    averaged = metrics_alerting._compute_success_rate([{"success_rate": 0.5}, {"success_rate": 75}])

    assert weighted == (0.5, 2, {"aggregation": "weighted", "successes": 5, "total": 10})
    assert averaged == (0.625, 2, {"aggregation": "average", "samples": 2})
    assert metrics_alerting._compute_success_rate([{}]) == (None, 0, {})


def test_compute_percentile_skips_missing_values_and_handles_empty_input() -> None:
    entries = [{"value": None}, {"value": 10}, {"value": 30}]

    assert metrics_alerting._compute_percentile(
        entries,
        value_extractor=lambda entry: entry["value"],
        percentile_value=50,
    ) == (20, 2)
    assert metrics_alerting._compute_percentile(
        [],
        value_extractor=lambda entry: entry["value"],
        percentile_value=95,
    ) == (None, 0)


def test_evaluate_lower_is_bad_pins_sample_and_severity_boundaries() -> None:
    threshold = {"warning": 0.95, "critical": 0.9, "window_days": 7, "min_runs": 2}

    assert metrics_alerting._evaluate_lower_is_bad("success_rate", None, 2, threshold) is None
    assert metrics_alerting._evaluate_lower_is_bad("success_rate", 0.5, 1, threshold) is None
    assert metrics_alerting._evaluate_lower_is_bad("success_rate", 0.95, 2, threshold) is None
    warning = metrics_alerting._evaluate_lower_is_bad("success_rate", 0.94, 2, threshold)
    critical = metrics_alerting._evaluate_lower_is_bad("success_rate", 0.9, 2, threshold)

    assert warning is not None
    assert warning.severity == "warning"
    assert warning.threshold == 0.95
    assert critical is not None
    assert critical.severity == "critical"
    assert critical.threshold == 0.9


def test_evaluate_higher_is_bad_pins_sample_and_severity_boundaries() -> None:
    threshold = {
        "p95_warning": 800,
        "p95_critical": 900,
        "window_days": 7,
        "min_runs": 2,
    }

    assert (
        metrics_alerting._evaluate_higher_is_bad(
            "duration_ms", None, 2, threshold, value_label="p95"
        )
        is None
    )
    assert (
        metrics_alerting._evaluate_higher_is_bad(
            "duration_ms", 1000, 1, threshold, value_label="p95"
        )
        is None
    )
    assert (
        metrics_alerting._evaluate_higher_is_bad(
            "duration_ms", 799, 2, threshold, value_label="p95"
        )
        is None
    )
    warning = metrics_alerting._evaluate_higher_is_bad(
        "duration_ms", 800, 2, threshold, value_label="p95"
    )
    critical = metrics_alerting._evaluate_higher_is_bad(
        "duration_ms", 900, 2, threshold, value_label="p95"
    )

    assert warning is not None
    assert warning.severity == "warning"
    assert warning.details["value_label"] == "p95"
    assert critical is not None
    assert critical.severity == "critical"
    assert critical.threshold == 900


def test_build_alerts_emits_all_configured_metrics_in_stable_order() -> None:
    now = datetime(2026, 1, 1, 2, tzinfo=UTC)
    entries = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "summary": {"passed": 8, "tests": 10},
            "duration_ms": 1000,
            "token_usage": 2500,
        },
        {
            "timestamp": "2026-01-01T01:00:00Z",
            "summary": {"passed": 4, "tests": 5},
            "duration_ms": 1100,
            "token_usage": 3000,
        },
    ]

    alerts = metrics_alerting.build_alerts(entries, _build_thresholds(), now=now)

    assert [alert.metric for alert in alerts] == ["success_rate", "duration_ms", "token_usage"]
    assert [alert.severity for alert in alerts] == ["critical", "critical", "critical"]
    assert alerts[0].details["aggregation"] == "weighted"
    assert metrics_alerting.build_alerts(entries, {"thresholds": {}}, now=now) == []


def test_formatters_and_issue_body_render_metric_specific_evidence() -> None:
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    success = metrics_alerting.Alert(
        metric="success_rate",
        severity="warning",
        value=0.925,
        threshold=0.95,
        window_days=7,
        min_runs=2,
        sample_count=3,
        alert_key="metrics_alert:success_rate",
        details={
            "thresholds": {"warning": 0.95, "critical": 0.9},
            "successes": 37,
            "total": 40,
            "aggregation": "weighted",
        },
    )
    duration = metrics_alerting.Alert(
        metric="duration_ms",
        severity="critical",
        value=1234.4,
        threshold=1000,
        window_days=7,
        min_runs=2,
        sample_count=3,
        alert_key="metrics_alert:duration_ms",
        details={"thresholds": {"p95_critical": 1000}},
    )
    rate_only = metrics_alerting.Alert(
        metric="success_rate",
        severity="warning",
        value=0.9,
        threshold=0.95,
        window_days=7,
        min_runs=2,
        sample_count=3,
        alert_key="metrics_alert:success_rate",
        details={"thresholds": {"warning": 0.95}},
    )

    body = metrics_alerting._issue_body(success, now)
    rate_only_body = metrics_alerting._issue_body(rate_only, now)

    assert metrics_alerting._format_alert_value(success) == "92.50%"
    assert metrics_alerting._format_threshold(success) == "95.00%"
    assert metrics_alerting._format_alert_value(duration) == "1,234"
    assert metrics_alerting._format_number(12.345) == "12.35"
    assert metrics_alerting._issue_title(success) == "Metrics alert: success_rate warning"
    assert "Detected at: 2026-01-02T03:04:05Z" in body
    assert "Successes: 37 / 40" in body
    assert "Aggregation: weighted" in body
    assert '"critical": 0.9' in body
    assert "Successes:" not in metrics_alerting._issue_body(duration, now)
    assert "Successes:" not in rate_only_body
    assert "Aggregation:" not in rate_only_body


def test_find_existing_issue_forwards_exact_dedup_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}
    expected = metrics_alerting.duplicate_detection.SourceIssue(
        number=3,
        title="existing",
        body=None,
        url="https://example.invalid/issues/3",
    )

    def fake_find(repo, token, *, query, labels, pages):
        seen.update(repo=repo, token=token, query=query, labels=labels, pages=pages)
        return expected

    monkeypatch.setattr(metrics_alerting.duplicate_detection, "find_source_issue", fake_find)
    alert = metrics_alerting.Alert(
        "token_usage", "warning", 1200, 1000, 7, 2, 3, "metrics_alert:token_usage", {}
    )

    assert (
        metrics_alerting._find_existing_issue("octo/repo", "secret", alert, ["metrics"]) is expected
    )
    assert seen == {
        "repo": "octo/repo",
        "token": "secret",
        "query": "metrics_alert:token_usage",
        "labels": ["metrics"],
        "pages": metrics_alerting.DEFAULT_DEDUP_PAGES,
    }


def test_send_slack_notification_formats_payload_and_rejects_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = []

    class Response:
        def __init__(self, status_code: int, text: str = "") -> None:
            self.status_code = status_code
            self.text = text

    response = Response(204)

    def fake_post(url, *, json, timeout):
        seen.append((url, json, timeout))
        return response

    monkeypatch.setattr(metrics_alerting.requests, "post", fake_post)
    alerts = [
        metrics_alerting.Alert(
            "success_rate", "warning", 0.9, 0.95, 7, 2, 3, "metrics_alert:success_rate", {}
        ),
        metrics_alerting.Alert(
            "token_usage", "critical", 2500, 2000, 7, 2, 3, "metrics_alert:token_usage", {}
        ),
    ]

    metrics_alerting._send_slack_notification(
        "https://example.invalid/hook", alerts, ["https://example.invalid/issues/1", ""]
    )

    assert seen == [
        (
            "https://example.invalid/hook",
            {
                "text": (
                    "Metrics alerting summary:\n"
                    "- success_rate (warning): 90.00% -> https://example.invalid/issues/1\n"
                    "- token_usage (critical): 2,500 -> no issue"
                )
            },
            10,
        )
    ]

    response.status_code = 429
    response.text = "rate limited"
    with pytest.raises(RuntimeError, match="Slack webhook returned 429: rate limited"):
        metrics_alerting._send_slack_notification("https://example.invalid/hook", alerts, [""])


def test_parser_pins_defaults_and_explicit_overrides() -> None:
    defaults = metrics_alerting._build_parser().parse_args([])
    explicit = metrics_alerting._build_parser().parse_args(
        [
            "--metrics-path",
            "input.ndjson",
            "--thresholds-path",
            "thresholds.json",
            "--alert-history-path",
            "history.ndjson",
            "--repo",
            "octo/repo",
            "--token-env",
            "ALT_TOKEN",
            "--slack-webhook",
            "https://example.invalid/hook",
            "--dry-run",
        ]
    )

    assert defaults.metrics_path == metrics_alerting.DEFAULT_METRICS_PATH
    assert defaults.thresholds_path == metrics_alerting.DEFAULT_THRESHOLDS_PATH
    assert defaults.alert_history_path == metrics_alerting.DEFAULT_ALERT_HISTORY_PATH
    assert defaults.token_env == "GITHUB_TOKEN"
    assert defaults.dry_run is False
    assert vars(explicit) == {
        "metrics_path": "input.ndjson",
        "thresholds_path": "thresholds.json",
        "alert_history_path": "history.ndjson",
        "repo": "octo/repo",
        "token_env": "ALT_TOKEN",
        "slack_webhook": "https://example.invalid/hook",
        "dry_run": True,
    }


def test_main_reports_missing_inputs_and_no_alerts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_thresholds = tmp_path / "missing-thresholds.json"
    assert metrics_alerting.main(["--thresholds-path", str(missing_thresholds)]) == 1
    assert "thresholds file not found" in capsys.readouterr().err

    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps({"thresholds": {}}), encoding="utf-8")
    missing_metrics = tmp_path / "missing-metrics.ndjson"
    assert (
        metrics_alerting.main(
            ["--thresholds-path", str(thresholds_path), "--metrics-path", str(missing_metrics)]
        )
        == 1
    )
    assert "metrics file not found" in capsys.readouterr().err

    metrics_path = tmp_path / "metrics.ndjson"
    metrics_path.write_text("", encoding="utf-8")
    assert (
        metrics_alerting.main(
            ["--thresholds-path", str(thresholds_path), "--metrics-path", str(metrics_path)]
        )
        == 0
    )
    assert capsys.readouterr().out == "metrics_alerting: no alerts triggered.\n"


def test_main_dry_run_records_skipped_alert_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    thresholds = _build_thresholds()
    thresholds["issue_labels"] = "invalid"
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps(thresholds), encoding="utf-8")
    now = datetime.now(UTC)
    metrics_path = tmp_path / "metrics.ndjson"
    metrics_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "timestamp": now.isoformat().replace("+00:00", "Z"),
                    "summary": {"passed": 8, "tests": 10},
                }
            )
            for _ in range(2)
        )
        + "\n",
        encoding="utf-8",
    )
    history_path = tmp_path / "history.ndjson"
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        metrics_alerting.api_client,
        "create_issue",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected issue")),
    )

    exit_code = metrics_alerting.main(
        [
            "--metrics-path",
            str(metrics_path),
            "--thresholds-path",
            str(thresholds_path),
            "--alert-history-path",
            str(history_path),
            "--repo",
            "octo/repo",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    record = json.loads(history_path.read_text(encoding="utf-8"))
    assert record["issue"] == {"number": None, "status": "skipped", "url": None}


def test_main_requires_repo_and_token_when_alerts_fire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps(_build_thresholds()), encoding="utf-8")
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    metrics_path = tmp_path / "metrics.ndjson"
    metrics_path.write_text(
        "\n".join(
            json.dumps({"timestamp": now, "summary": {"passed": 8, "tests": 10}}) for _ in range(2)
        )
        + "\n",
        encoding="utf-8",
    )
    common = ["--metrics-path", str(metrics_path), "--thresholds-path", str(thresholds_path)]
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert metrics_alerting.main([*common, "--dry-run"]) == 1
    assert "repo not set" in capsys.readouterr().err
    assert metrics_alerting.main([*common, "--repo", "octo/repo"]) == 1
    assert "GitHub token not available" in capsys.readouterr().err


def test_main_reports_parse_errors_but_processes_valid_records(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps(_build_thresholds()), encoding="utf-8")
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    metrics_path = tmp_path / "metrics.ndjson"
    metrics_path.write_text(
        "not-json\n"
        + json.dumps({"timestamp": now, "summary": {"passed": 8, "tests": 10}})
        + "\n"
        + json.dumps({"timestamp": now, "summary": {"passed": 4, "tests": 5}})
        + "\n",
        encoding="utf-8",
    )
    history_path = tmp_path / "history.ndjson"

    assert (
        metrics_alerting.main(
            [
                "--metrics-path",
                str(metrics_path),
                "--thresholds-path",
                str(thresholds_path),
                "--alert-history-path",
                str(history_path),
                "--repo",
                "octo/repo",
                "--dry-run",
            ]
        )
        == 0
    )
    assert "parse errors found: 1" in capsys.readouterr().err
    assert json.loads(history_path.read_text(encoding="utf-8"))["metric"] == "success_rate"
