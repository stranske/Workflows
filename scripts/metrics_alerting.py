#!/usr/bin/env python3
"""Evaluate metrics thresholds and open alert issues."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from scripts import api_client, duplicate_detection
from src import percentile_calculator

DEFAULT_METRICS_PATH = "metrics-history.ndjson"
DEFAULT_THRESHOLDS_PATH = "config/alerting-thresholds.json"
DEFAULT_ALERT_HISTORY_PATH = "metrics-history.ndjson"
DEFAULT_DEDUP_PAGES = 2


@dataclass(frozen=True)
class Alert:
    metric: str
    severity: str
    value: float
    threshold: float
    window_days: int
    min_runs: int
    sample_count: int
    alert_key: str
    details: dict[str, Any]


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _read_ndjson(path: Path) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    errors = 0
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return entries, 1
    for line in content.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            errors += 1
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
        else:
            errors += 1
    return entries, errors


def _filter_recent_entries(
    entries: list[dict[str, Any]],
    *,
    window_days: int,
    now: datetime,
) -> list[dict[str, Any]]:
    cutoff = now - timedelta(days=window_days)
    recent: list[dict[str, Any]] = []
    for entry in entries:
        timestamp = _parse_timestamp(entry.get("timestamp"))
        if timestamp is None:
            continue
        if timestamp >= cutoff:
            recent.append(entry)
    return recent


def _extract_success_rate(entry: dict[str, Any]) -> tuple[float | None, int | None, int | None]:
    summary = entry.get("summary")
    if isinstance(summary, dict):
        passed = _safe_int(summary.get("passed"))
        tests = _safe_int(summary.get("tests"))
        if passed is not None and tests is not None and tests > 0:
            return passed / tests, passed, tests
        successes = _safe_int(summary.get("successes"))
        total = _safe_int(summary.get("total"))
        if successes is not None and total is not None and total > 0:
            return successes / total, successes, total
        rate = _safe_float(summary.get("success_rate"))
        if rate is not None:
            if rate > 1:
                rate = rate / 100
            return rate, None, None

    rate = _safe_float(entry.get("success_rate"))
    if rate is not None:
        if rate > 1:
            rate = rate / 100
        return rate, None, None
    successes = _safe_int(entry.get("successes"))
    total = _safe_int(entry.get("total"))
    if successes is not None and total is not None and total > 0:
        return successes / total, successes, total
    return None, None, None


def _extract_duration_ms(entry: dict[str, Any]) -> float | None:
    duration_ms = _safe_float(entry.get("duration_ms"))
    if duration_ms is not None:
        return duration_ms
    summary = entry.get("summary")
    if isinstance(summary, dict):
        summary_ms = _safe_float(summary.get("duration_ms"))
        if summary_ms is not None:
            return summary_ms
        summary_seconds = _safe_float(summary.get("duration_seconds"))
        if summary_seconds is not None:
            return summary_seconds * 1000
    duration_seconds = _safe_float(entry.get("duration_seconds"))
    if duration_seconds is not None:
        return duration_seconds * 1000
    return None


def _extract_token_usage(entry: dict[str, Any]) -> float | None:
    token_usage = entry.get("token_usage")
    if token_usage is None and isinstance(entry.get("summary"), dict):
        token_usage = entry["summary"].get("token_usage")
    if token_usage is None:
        token_usage = entry.get("token_usage_total")
    if isinstance(token_usage, dict):
        total_tokens = _safe_float(token_usage.get("total_tokens"))
        if total_tokens is not None:
            return total_tokens
        keys = (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "prompt_tokens",
            "completion_tokens",
        )
        values = [_safe_float(token_usage.get(key)) for key in keys]
        numbers = [value for value in values if value is not None]
        if numbers:
            return sum(numbers)
        return None
    return _safe_float(token_usage)


def _compute_success_rate(
    entries: list[dict[str, Any]],
) -> tuple[float | None, int, dict[str, Any]]:
    total_successes = 0
    total_runs = 0
    rates: list[float] = []
    sample_count = 0

    for entry in entries:
        rate, successes, total = _extract_success_rate(entry)
        if rate is None:
            continue
        sample_count += 1
        if successes is not None and total is not None:
            total_successes += successes
            total_runs += total
        else:
            rates.append(rate)

    if total_runs > 0:
        value = total_successes / total_runs
        details = {
            "aggregation": "weighted",
            "successes": total_successes,
            "total": total_runs,
        }
        return value, sample_count, details
    if rates:
        value = sum(rates) / len(rates)
        details = {
            "aggregation": "average",
            "samples": len(rates),
        }
        return value, sample_count, details
    return None, sample_count, {}


def _compute_percentile(
    entries: list[dict[str, Any]],
    *,
    value_extractor: Any,
    percentile_value: float,
) -> tuple[float | None, int]:
    values: list[float] = []
    for entry in entries:
        value = value_extractor(entry)
        if value is None:
            continue
        values.append(float(value))
    if not values:
        return None, 0
    values.sort()
    return percentile_calculator.percentile(values, percentile_value), len(values)


def _evaluate_lower_is_bad(
    metric: str,
    value: float | None,
    sample_count: int,
    threshold: dict[str, Any],
) -> Alert | None:
    if value is None or sample_count < int(threshold["min_runs"]):
        return None
    warning = float(threshold["warning"])
    critical = float(threshold["critical"])
    severity = None
    chosen_threshold = None
    if value <= critical:
        severity = "critical"
        chosen_threshold = critical
    elif value < warning:
        severity = "warning"
        chosen_threshold = warning
    if severity is None:
        return None
    alert_key = f"metrics_alert:{metric}"
    return Alert(
        metric=metric,
        severity=severity,
        value=value,
        threshold=chosen_threshold,
        window_days=int(threshold["window_days"]),
        min_runs=int(threshold["min_runs"]),
        sample_count=sample_count,
        alert_key=alert_key,
        details={"thresholds": {"warning": warning, "critical": critical}},
    )


def _evaluate_higher_is_bad(
    metric: str,
    value: float | None,
    sample_count: int,
    threshold: dict[str, Any],
    *,
    value_label: str,
) -> Alert | None:
    if value is None or sample_count < int(threshold["min_runs"]):
        return None
    warning = float(threshold["p95_warning"])
    critical = float(threshold["p95_critical"])
    severity = None
    chosen_threshold = None
    if value >= critical:
        severity = "critical"
        chosen_threshold = critical
    elif value >= warning:
        severity = "warning"
        chosen_threshold = warning
    if severity is None:
        return None
    alert_key = f"metrics_alert:{metric}"
    return Alert(
        metric=metric,
        severity=severity,
        value=value,
        threshold=chosen_threshold,
        window_days=int(threshold["window_days"]),
        min_runs=int(threshold["min_runs"]),
        sample_count=sample_count,
        alert_key=alert_key,
        details={
            "thresholds": {"p95_warning": warning, "p95_critical": critical},
            "value_label": value_label,
        },
    )


def build_alerts(
    entries: list[dict[str, Any]],
    thresholds: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[Alert]:
    now = now or datetime.now(UTC)
    alerts: list[Alert] = []
    threshold_set = thresholds.get("thresholds", {})

    success_config = threshold_set.get("success_rate", {})
    if success_config:
        success_entries = _filter_recent_entries(
            entries, window_days=int(success_config["window_days"]), now=now
        )
        success_rate, sample_count, details = _compute_success_rate(success_entries)
        alert = _evaluate_lower_is_bad(
            "success_rate",
            success_rate,
            sample_count,
            success_config,
        )
        if alert:
            alerts.append(Alert(**{**alert.__dict__, "details": {**alert.details, **details}}))

    duration_config = threshold_set.get("duration_ms", {})
    if duration_config:
        duration_entries = _filter_recent_entries(
            entries, window_days=int(duration_config["window_days"]), now=now
        )
        p95_duration, sample_count = _compute_percentile(
            duration_entries,
            value_extractor=_extract_duration_ms,
            percentile_value=95,
        )
        alert = _evaluate_higher_is_bad(
            "duration_ms",
            p95_duration,
            sample_count,
            duration_config,
            value_label="p95_duration_ms",
        )
        if alert:
            alerts.append(alert)

    token_config = threshold_set.get("token_usage", {})
    if token_config:
        token_entries = _filter_recent_entries(
            entries, window_days=int(token_config["window_days"]), now=now
        )
        p95_tokens, sample_count = _compute_percentile(
            token_entries,
            value_extractor=_extract_token_usage,
            percentile_value=95,
        )
        alert = _evaluate_higher_is_bad(
            "token_usage",
            p95_tokens,
            sample_count,
            token_config,
            value_label="p95_tokens",
        )
        if alert:
            alerts.append(alert)

    return alerts


def _format_success_rate(value: float) -> str:
    return f"{value * 100:.2f}%"


def _format_number(value: float) -> str:
    if value >= 1000:
        return f"{value:,.0f}"
    return f"{value:.2f}"


def _format_alert_value(alert: Alert) -> str:
    if alert.metric == "success_rate":
        return _format_success_rate(alert.value)
    return _format_number(alert.value)


def _format_threshold(alert: Alert) -> str:
    if alert.metric == "success_rate":
        return _format_success_rate(alert.threshold)
    return _format_number(alert.threshold)


def _issue_title(alert: Alert) -> str:
    return f"Metrics alert: {alert.metric} {alert.severity}"


def _issue_body(alert: Alert, now: datetime) -> str:
    details = alert.details
    lines = [
        f"Alert key: `{alert.alert_key}`",
        "",
        f"Metric: `{alert.metric}`",
        f"Severity: **{alert.severity.upper()}**",
        f"Window: last {alert.window_days} day(s)",
        f"Samples: {alert.sample_count} (min {alert.min_runs})",
        f"Observed value: {_format_alert_value(alert)}",
        f"Threshold: {_format_threshold(alert)}",
        f"Detected at: {now.isoformat().replace('+00:00', 'Z')}",
        "",
        "Thresholds:",
        "```json",
        json.dumps(details.get("thresholds", {}), indent=2, sort_keys=True),
        "```",
    ]
    if alert.metric == "success_rate":
        if "successes" in details and "total" in details:
            lines.append(f"Successes: {details['successes']} / {details['total']}")
        if "aggregation" in details:
            lines.append(f"Aggregation: {details['aggregation']}")
    return "\n".join(lines)


def _find_existing_issue(
    repo: str,
    token: str,
    alert: Alert,
    labels: list[str],
) -> duplicate_detection.SourceIssue | None:
    return duplicate_detection.find_source_issue(
        repo,
        token,
        query=alert.alert_key,
        labels=labels,
        pages=DEFAULT_DEDUP_PAGES,
    )


def _append_alert_history(
    path: Path,
    alert: Alert,
    *,
    issue_url: str | None,
    issue_number: int | None,
    issue_status: str,
    now: datetime,
) -> None:
    record = {
        "metric_type": "alert",
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "alert_key": alert.alert_key,
        "metric": alert.metric,
        "severity": alert.severity,
        "value": alert.value,
        "threshold": alert.threshold,
        "window_days": alert.window_days,
        "min_runs": alert.min_runs,
        "sample_count": alert.sample_count,
        "issue": {
            "status": issue_status,
            "number": issue_number,
            "url": issue_url,
        },
    }
    payload = json.dumps(record, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload + "\n")


def _send_slack_notification(webhook: str, alerts: list[Alert], issue_urls: list[str]) -> None:
    lines = ["Metrics alerting summary:"]
    for alert, issue_url in zip(alerts, issue_urls):
        issue_text = issue_url or "no issue"
        lines.append(
            f"- {alert.metric} ({alert.severity}): {_format_alert_value(alert)} -> {issue_text}"
        )
    payload = {"text": "\n".join(lines)}
    response = requests.post(webhook, json=payload, timeout=10)
    if response.status_code >= 400:
        raise RuntimeError(f"Slack webhook returned {response.status_code}: {response.text}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate metrics alerting thresholds.")
    parser.add_argument("--metrics-path", default=DEFAULT_METRICS_PATH, help="NDJSON metrics path")
    parser.add_argument(
        "--thresholds-path",
        default=DEFAULT_THRESHOLDS_PATH,
        help="Alerting thresholds config path",
    )
    parser.add_argument(
        "--alert-history-path",
        default=DEFAULT_ALERT_HISTORY_PATH,
        help="NDJSON metrics history output path",
    )
    parser.add_argument("--repo", help="GitHub repository (owner/name)")
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable containing GitHub token",
    )
    parser.add_argument(
        "--slack-webhook",
        help="Optional Slack webhook URL (overrides SLACK_WEBHOOK_URL env var)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip issue creation")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    thresholds_path = Path(args.thresholds_path)
    if not thresholds_path.is_file():
        print(f"metrics_alerting: thresholds file not found: {thresholds_path}", file=sys.stderr)
        return 1
    thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
    metrics_path = Path(args.metrics_path)
    if not metrics_path.exists():
        print(f"metrics_alerting: metrics file not found: {metrics_path}", file=sys.stderr)
        return 1

    entries, errors = _read_ndjson(metrics_path)
    if errors:
        print(f"metrics_alerting: parse errors found: {errors}", file=sys.stderr)

    now = datetime.now(UTC)
    alerts = build_alerts(entries, thresholds, now=now)
    if not alerts:
        print("metrics_alerting: no alerts triggered.")
        return 0

    repo = args.repo or os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get(args.token_env, "")
    labels = thresholds.get("issue_labels", [])
    if not isinstance(labels, list):
        labels = []

    if not repo:
        print("metrics_alerting: repo not set (use --repo or GITHUB_REPOSITORY).", file=sys.stderr)
        return 1

    issue_urls: list[str] = []
    for alert in alerts:
        issue_url = None
        issue_number = None
        issue_status = "skipped"
        if token and not args.dry_run:
            existing = _find_existing_issue(repo, token, alert, labels)
            if existing:
                issue_url = existing.url
                issue_number = existing.number
                issue_status = "existing"
            else:
                issue = api_client.create_issue(
                    repo,
                    token,
                    _issue_title(alert),
                    _issue_body(alert, now),
                    labels,
                )
                issue_url = issue.get("html_url")
                issue_number = issue.get("number")
                issue_status = "created"
        elif not args.dry_run:
            print("metrics_alerting: GitHub token not available.", file=sys.stderr)
            return 1

        _append_alert_history(
            Path(args.alert_history_path),
            alert,
            issue_url=issue_url,
            issue_number=issue_number,
            issue_status=issue_status,
            now=now,
        )
        issue_urls.append(issue_url or "")

    slack_webhook = args.slack_webhook or os.environ.get("SLACK_WEBHOOK_URL")
    if slack_webhook:
        _send_slack_notification(slack_webhook, alerts, issue_urls)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
