#!/usr/bin/env python3
"""Compare workflow run counts between two snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class WorkflowCount:
    name: str
    before: int
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before

    @property
    def pct_change(self) -> str:
        if self.before == 0 and self.after == 0:
            return "0.0%"
        if self.before == 0:
            return "new"
        pct = ((self.after - self.before) / self.before) * 100
        return f"{pct:+.1f}%"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Snapshot not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Snapshot is not valid JSON: {path}") from exc


def _extract_runs(payload: Any, *, source: Path) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        runs = payload
    elif isinstance(payload, dict):
        runs = payload.get("workflow_runs", payload.get("runs", []))
    else:
        raise ValueError(f"Snapshot has unexpected structure: {source}")
    if not isinstance(runs, list):
        raise ValueError(f"Snapshot contains invalid run list: {source}")
    return [run for run in runs if isinstance(run, dict)]


def load_runs(path: Path) -> list[dict[str, Any]]:
    """Load a workflow run snapshot from JSON."""
    payload = _load_json(path)
    return _extract_runs(payload, source=path)


def _workflow_name(run: dict[str, Any]) -> str:
    workflow = run.get("workflow")
    if isinstance(workflow, dict):
        name = workflow.get("name") or workflow.get("path")
        if isinstance(name, str) and name.strip():
            return name.strip()
    for key in ("name", "workflow_name", "path", "workflow_id"):
        value = run.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if key == "workflow_id" and isinstance(value, int):
            return f"workflow:{value}"
    return "unknown"


def _matches_filter(name: str, filters: Iterable[str]) -> bool:
    if not filters:
        return True
    lowered = name.lower()
    for raw in filters:
        if not raw:
            continue
        token = raw.lower()
        if lowered == token or token in lowered:
            return True
    return False


def build_counts(
    runs: Iterable[dict[str, Any]],
    *,
    workflow_filters: Iterable[str] = (),
) -> dict[str, int]:
    """Count runs per workflow name."""
    counts: dict[str, int] = {}
    for run in runs:
        name = _workflow_name(run)
        if not _matches_filter(name, workflow_filters):
            continue
        counts[name] = counts.get(name, 0) + 1
    return counts


def compare_counts(
    before: dict[str, int],
    after: dict[str, int],
) -> list[WorkflowCount]:
    names = sorted(set(before) | set(after))
    return [WorkflowCount(name, before.get(name, 0), after.get(name, 0)) for name in names]


def _format_table(counts: list[WorkflowCount]) -> str:
    name_width = max((len(entry.name) for entry in counts), default=8)
    header = f"{'Workflow':<{name_width}}  {'Before':>6}  {'After':>5}  {'Delta':>6}  {'Change':>7}"
    lines = [header, "-" * len(header)]
    for entry in counts:
        lines.append(
            f"{entry.name:<{name_width}}  {entry.before:>6}  {entry.after:>5}  {entry.delta:>6}  {entry.pct_change:>7}"
        )
    total_before = sum(entry.before for entry in counts)
    total_after = sum(entry.after for entry in counts)
    total = WorkflowCount("Total", total_before, total_after)
    lines.append("-" * len(header))
    lines.append(
        f"{total.name:<{name_width}}  {total.before:>6}  {total.after:>5}  {total.delta:>6}  {total.pct_change:>7}"
    )
    return "\n".join(lines)


def _format_json(counts: list[WorkflowCount]) -> str:
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "workflows": [
            {
                "name": entry.name,
                "before": entry.before,
                "after": entry.after,
                "delta": entry.delta,
                "pct_change": entry.pct_change,
            }
            for entry in counts
        ],
    }
    return json.dumps(payload, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare workflow run counts between two JSON snapshots."
    )
    parser.add_argument("--before", required=True, type=Path, help="JSON snapshot before debouncing")
    parser.add_argument("--after", required=True, type=Path, help="JSON snapshot after debouncing")
    parser.add_argument(
        "--workflow",
        dest="workflows",
        action="append",
        default=[],
        help="Workflow name or substring filter (repeatable)",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument("--output", type=Path, help="Optional output path")
    args = parser.parse_args(argv)

    try:
        before_runs = load_runs(args.before)
        after_runs = load_runs(args.after)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    before_counts = build_counts(before_runs, workflow_filters=args.workflows)
    after_counts = build_counts(after_runs, workflow_filters=args.workflows)
    comparison = compare_counts(before_counts, after_counts)

    output = _format_table(comparison) if args.format == "table" else _format_json(comparison)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
