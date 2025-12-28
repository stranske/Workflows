"""Generate a Markdown summary for autofix runs."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MARKER = "<!-- AUTOFIX REPORT -->"


def load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def format_timestamp(timestamp: str | None) -> str:
    if timestamp is None:
        return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return timestamp


def format_spark(value: Any) -> str:
    if not value:
        return "∅"
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        rendered = "".join(str(v) for v in value)
        return rendered or "∅"
    return str(value)


def _top_code_lines(codes: dict | None) -> tuple[str, ...]:
    if not codes:
        return ()
    lines = ["", "Top residual codes", ""]
    for code, details in sorted(codes.items()):
        latest = details.get("latest", 0)
        lines.append(f"- `{code}`: {latest}")
    return tuple(lines)


def _snapshot_code_lines(snapshot: dict | None) -> tuple[str, ...]:
    if not snapshot:
        return ()
    lines = ["", "Current per-code counts", ""]
    for code, count in sorted(snapshot.items()):
        lines.append(f"- `{code}`: {count}")
    return tuple(lines)


def _status_line(report: dict | None) -> str:
    classification = (report or {}).get("classification", {}) if isinstance(report, dict) else {}
    new_count = coerce_int(classification.get("new"), 0)
    changed = coerce_bool((report or {}).get("changed"), False)
    if changed:
        return "Status | ✅ autofix updates applied"
    if new_count > 0:
        return "Status | ⚠️ new diagnostics detected"
    return "Status | ✅ no new diagnostics"


def build_comment(
    *,
    report_path: Path,
    trend_path: Path,
    history_path: Path | None = None,
    pr_number: str | None = None,
) -> str:
    report = load_json(report_path) or {}
    trend = load_json(trend_path) or {}
    history = load_json(history_path) if history_path else None

    lines = [
        MARKER,
        _status_line(report),
        f"History points | {len(history) if isinstance(history, list) else 0}",
    ]

    classification = report.get("classification", {}) if isinstance(report, dict) else {}
    timestamp = classification.get("timestamp")
    lines.append(f"Timestamp | {format_timestamp(timestamp)}")

    report_label = pr_number or "manual"
    lines.append(f"Report artifact | `autofix-report-pr-{report_label}`")

    remaining = trend.get("remaining_latest")
    new_latest = trend.get("new_latest")
    lines.append(f"Remaining | {remaining if remaining is not None else '∅'}")
    lines.append(f"New | {new_latest if new_latest is not None else '∅'}")

    codes = trend.get("codes") if isinstance(trend, dict) else {}
    lines.extend(_top_code_lines(codes))

    snapshot = classification.get("by_code") if isinstance(classification, dict) else None
    lines.extend(_snapshot_code_lines(snapshot))

    if not codes and not snapshot:
        lines.append("No additional artifacts")

    lines.append(MARKER)
    return "\n".join(lines)


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--trend", type=Path, required=True)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pr-number")
    parsed = parser.parse_args(args)

    comment = build_comment(
        report_path=parsed.report,
        trend_path=parsed.trend,
        history_path=parsed.history,
        pr_number=parsed.pr_number,
    )
    parsed.out.parent.mkdir(parents=True, exist_ok=True)
    parsed.out.write_text(comment, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
