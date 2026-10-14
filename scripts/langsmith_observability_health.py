#!/usr/bin/env python3
"""Evaluate LangSmith observability freshness without mutating source branches."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

DEFAULT_ENDPOINT = "https://api.smith.langchain.com"
DEFAULT_PROJECT = "workflows-agents"
PAUSE_METADATA_FIELDS = (
    "paused_at",
    "pause_reason",
    "pause_owner",
    "resume_condition",
    "review_by",
)


def validate_endpoint(endpoint: str) -> str:
    """Accept only credential-free HTTPS endpoints for LangSmith API reads."""
    parsed = urlparse.urlparse(endpoint.strip())
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("LangSmith endpoint must be a credential-free HTTPS origin or path")
    return endpoint.strip().rstrip("/")


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO timestamp and normalize it to UTC."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_workflow_runs(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Load GitHub Actions workflow runs plus a fail-open fetch diagnostic."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"could not read {path.name}: {type(exc).__name__}"
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], None
    if not isinstance(payload, dict):
        return [], f"{path.name} must contain a JSON object or list"
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return [], f"{path.name} has no workflow_runs list"
    fetch_error = payload.get("fetch_error")
    return (
        [item for item in runs if isinstance(item, dict)],
        str(fetch_error) if fetch_error else None,
    )


def evaluate_workflow_runs(
    runs: list[dict[str, Any]],
    *,
    name: str,
    now: datetime,
    max_age_hours: int,
    failure_threshold: int,
    fetch_error: str | None = None,
) -> dict[str, Any]:
    """Classify workflow cadence by failure streak and last-success freshness."""
    ordered = sorted(
        runs,
        key=lambda run: parse_timestamp(run.get("created_at")) or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    completed = [run for run in ordered if run.get("status") in (None, "completed")]
    last_success = next((run for run in completed if run.get("conclusion") == "success"), None)
    last_success_at = parse_timestamp((last_success or {}).get("created_at"))

    consecutive_failures = 0
    for run in completed:
        if run.get("conclusion") == "success":
            break
        if run.get("conclusion"):
            consecutive_failures += 1

    reasons: list[str] = []
    if fetch_error:
        reasons.append(fetch_error)
    if not completed:
        reasons.append("no completed workflow runs were available")
    if last_success_at is None:
        reasons.append("no successful workflow run was found")
        hours_since_success = None
    else:
        hours_since_success = max(0.0, (now - last_success_at).total_seconds() / 3600)
        if hours_since_success > max_age_hours:
            reasons.append(
                f"last success is {hours_since_success:.1f}h old; threshold is {max_age_hours}h"
            )
    if consecutive_failures >= failure_threshold:
        reasons.append(
            f"{consecutive_failures} consecutive non-successful runs; "
            f"threshold is {failure_threshold}"
        )

    latest = ordered[0] if ordered else {}
    return {
        "name": name,
        "status": "degraded" if reasons else "healthy",
        "latest_run_at": (
            parse_timestamp(latest.get("created_at")).isoformat()
            if parse_timestamp(latest.get("created_at"))
            else None
        ),
        "latest_conclusion": latest.get("conclusion"),
        "last_success_at": last_success_at.isoformat() if last_success_at else None,
        "hours_since_success": (
            round(hours_since_success, 1) if hours_since_success is not None else None
        ),
        "consecutive_failures": consecutive_failures,
        "reasons": reasons,
    }


def evaluate_pauses(registry: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Require intentional pauses to remain owned, reviewable, and resumable."""
    paused_entries: list[dict[str, Any]] = []
    advisories: list[str] = []
    reasons: list[str] = []
    for entry in registry.get("repos", []):
        if not isinstance(entry, dict) or entry.get("rollout_status") != "paused":
            continue
        repo = str(entry.get("repo") or "unknown")
        normalized_metadata = {
            field: value.strip()
            for field in PAUSE_METADATA_FIELDS
            if isinstance((value := entry.get(field)), str) and value.strip()
        }
        missing = [field for field in PAUSE_METADATA_FIELDS if field not in normalized_metadata]
        if missing:
            reasons.append(f"{repo} pause is missing: {', '.join(missing)}")

        paused_at_raw = normalized_metadata.get("paused_at")
        paused_at = None
        if paused_at_raw:
            try:
                paused_at = datetime.fromisoformat(paused_at_raw.replace("Z", "+00:00"))
                if paused_at.tzinfo is None:
                    raise ValueError
                paused_at = paused_at.astimezone(UTC)
            except ValueError:
                reasons.append(f"{repo} paused_at is not a timezone-aware ISO timestamp")

        review_by_raw = normalized_metadata.get("review_by")
        review_by = None
        if review_by_raw:
            try:
                review_by = date.fromisoformat(review_by_raw)
            except ValueError:
                reasons.append(f"{repo} review_by is not an ISO date")
        if paused_at and review_by and review_by < paused_at.date():
            reasons.append(f"{repo} review_by cannot predate paused_at")
        if review_by and review_by < now.date():
            advisories.append(f"{repo} pause review was due {review_by.isoformat()}")
        paused_entries.append(
            {
                "repo": repo,
                "paused_at": entry.get("paused_at"),
                "pause_owner": entry.get("pause_owner"),
                "resume_condition": entry.get("resume_condition"),
                "review_by": entry.get("review_by"),
            }
        )
    return {
        "name": "intentional_pauses",
        "status": "degraded" if reasons else "healthy",
        "paused_entries": paused_entries,
        "advisories": advisories,
        "reasons": reasons,
    }


def evaluate_trace_freshness(
    latest_run: dict[str, Any] | None,
    *,
    now: datetime,
    max_age_hours: int,
    error: str | None = None,
) -> dict[str, Any]:
    """Classify whether the shared cloud tracing project is still flowing."""
    reasons: list[str] = []
    if error:
        reasons.append(error)
    started_at = parse_timestamp((latest_run or {}).get("start_time"))
    if started_at is None:
        reasons.append("no current LangSmith trace was available")
        age_hours = None
    else:
        age_hours = max(0.0, (now - started_at).total_seconds() / 3600)
        if age_hours > max_age_hours:
            reasons.append(f"latest trace is {age_hours:.1f}h old; threshold is {max_age_hours}h")
    return {
        "name": "langsmith_cloud_traces",
        "status": "degraded" if reasons else "healthy",
        "latest_trace_at": started_at.isoformat() if started_at else None,
        "latest_trace_id": (latest_run or {}).get("trace_id") or (latest_run or {}).get("id"),
        "hours_since_trace": round(age_hours, 1) if age_hours is not None else None,
        "reasons": reasons,
    }


def _request_json(
    method: str,
    url: str,
    *,
    api_key: str,
    body: dict[str, Any] | None = None,
) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urlrequest.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": api_key,
        },
    )
    try:
        # The request URL is built only from validate_endpoint() plus fixed API paths.
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urlrequest.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        raise RuntimeError(
            f"LangSmith HTTP {exc.code} for {method} {urlparse.urlparse(url).path}"
        ) from exc


def query_latest_trace(
    *,
    api_key: str,
    endpoint: str,
    project: str,
    now: datetime,
    search_hours: int,
) -> dict[str, Any] | None:
    """Read recent trace timestamps without logging secrets or trace payloads."""
    endpoint = validate_endpoint(endpoint)
    query = urlparse.urlencode({"limit": 10, "name": project, "include_stats": "false"})
    sessions = _request_json("GET", f"{endpoint}/sessions?{query}", api_key=api_key)
    exact = [item for item in sessions if isinstance(item, dict) and item.get("name") == project]
    if not exact:
        raise RuntimeError(f"LangSmith project {project} was not found")
    response = _request_json(
        "POST",
        f"{endpoint}/runs/query",
        api_key=api_key,
        body={
            "session": [str(exact[0]["id"])],
            "start_time": (now - timedelta(hours=search_hours)).isoformat(),
            "select": ["id", "trace_id", "start_time", "status"],
            "limit": 100,
        },
    )
    runs = response.get("runs", []) if isinstance(response, dict) else []
    usable = [
        run for run in runs if isinstance(run, dict) and parse_timestamp(run.get("start_time"))
    ]
    return max(usable, key=lambda run: parse_timestamp(run["start_time"])) if usable else None


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact operator-facing status report."""
    lines = [
        "# LangSmith Observability Health",
        "",
        f"- Overall status: **{report['status']}**",
        f"- Generated: {report['generated_at']}",
        "",
        "| Component | Status | Latest evidence | Details |",
        "|---|---|---|---|",
    ]
    for component in report["components"]:
        latest = component.get("latest_trace_at") or component.get("last_success_at") or "n/a"
        details = (
            "; ".join(component.get("reasons", []) + component.get("advisories", []))
            or "within freshness policy"
        )
        lines.append(f"| {component['name']} | {component['status']} | {latest} | {details} |")
    lines.extend(
        [
            "",
            "## State boundaries",
            "",
            "- Rollout intent, cloud trace flow, artifact conformance, and local Orchestrator import are independent states.",
            "- A paused artifact expectation does not mean cloud tracing is disabled.",
            "- Orchestrator keeps imported trace references and costs in its local durable store; full trace payloads remain governed by LangSmith retention.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    now = parse_timestamp(args.now) if args.now else datetime.now(UTC)
    if now is None:
        raise ValueError("--now must be an ISO timestamp")
    dashboard_runs, dashboard_error = load_workflow_runs(args.dashboard_runs)
    conformance_runs, conformance_error = load_workflow_runs(args.conformance_runs)
    registry = json.loads(args.registry.read_text(encoding="utf-8"))

    api_key = (os.environ.get("LANGSMITH_API_KEY") or "").strip()
    latest_trace = None
    trace_error = None
    if not api_key:
        trace_error = "LANGSMITH_API_KEY is unavailable; cloud trace freshness cannot be verified"
    else:
        try:
            latest_trace = query_latest_trace(
                api_key=api_key,
                endpoint=args.endpoint,
                project=args.project,
                now=now,
                search_hours=max(args.trace_max_age_hours * 4, 168),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            trace_error = str(exc)

    components = [
        evaluate_workflow_runs(
            dashboard_runs,
            name="dashboard_publication",
            now=now,
            max_age_hours=args.workflow_max_age_hours,
            failure_threshold=args.failure_threshold,
            fetch_error=dashboard_error,
        ),
        evaluate_workflow_runs(
            conformance_runs,
            name="fleet_conformance",
            now=now,
            max_age_hours=args.workflow_max_age_hours,
            failure_threshold=args.failure_threshold,
            fetch_error=conformance_error,
        ),
        evaluate_trace_freshness(
            latest_trace,
            now=now,
            max_age_hours=args.trace_max_age_hours,
            error=trace_error,
        ),
        evaluate_pauses(registry, now=now),
    ]
    return {
        "schema_version": "langsmith-observability-health/v1",
        "generated_at": now.isoformat(),
        "status": (
            "degraded"
            if any(component["status"] != "healthy" for component in components)
            else "healthy"
        ),
        "components": components,
        # A stale workflow or overdue review is owned by automation. Only the
        # unavailable cloud credential requires an external access action.
        "human_attention_required": not bool(api_key),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard-runs", type=Path, required=True)
    parser.add_argument("--conformance-runs", type=Path, required=True)
    parser.add_argument(
        "--registry", type=Path, default=Path("config/langsmith_fleet_registry.json")
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument(
        "--endpoint", default=os.environ.get("LANGSMITH_ENDPOINT", DEFAULT_ENDPOINT)
    )
    parser.add_argument("--workflow-max-age-hours", type=int, default=192)
    parser.add_argument("--trace-max-age-hours", type=int, default=24)
    parser.add_argument("--failure-threshold", type=int, default=2)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--now", help="ISO timestamp override for deterministic validation")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "json": str(args.json_output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
