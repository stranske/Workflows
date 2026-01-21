"""Audit workflows that read PR context to inform consolidation design."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

PR_CONTEXT_PATHS = (
    "github.event.pull_request",
    "github.event.issue.pull_request",
    "github.event.issue.number",
    "context.payload.issue.pull_request",
    "context.payload.issue.number",
    "context.payload.pull_request",
    "event.source.issue.pull_request",
    "event.source.issue.number",
    "workflow_run.pull_requests",
)


def build_path_pattern(path: str) -> re.Pattern[str]:
    """Build a regex that matches dotted or bracketed access paths."""
    segments = path.split(".")
    if not segments:
        return re.compile("")
    pattern = re.escape(segments[0])
    for segment in segments[1:]:
        escaped = re.escape(segment)
        pattern += rf"(?:\??\.(?:{escaped})|(?:\??\.)?\[['\"]{escaped}['\"]\])"
    return re.compile(pattern)


PR_CONTEXT_PATTERNS = {path: build_path_pattern(path) for path in PR_CONTEXT_PATHS}
PR_CONTEXT_PATTERNS["pull_request_number"] = re.compile(r"\bpull_request_number\b")


@dataclass(frozen=True)
class WorkflowAudit:
    """Summary of PR context usage for a workflow file."""

    path: Path
    triggers: tuple[str, ...]
    pr_context_markers: tuple[str, ...]
    valid: bool
    error: str | None


@dataclass(frozen=True)
class TriggerSummary:
    """Group workflows by trigger set for consolidation planning."""

    triggers: tuple[str, ...]
    workflows: tuple[str, ...]
    pr_context_markers: tuple[str, ...]


def load_workflow(path: Path, text: str | None = None) -> dict | None:
    """Load a workflow YAML file and return the parsed content."""
    try:
        content = text if text is not None else path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def normalize_triggers(on_field: object) -> tuple[str, ...]:
    """Normalize workflow trigger declarations to a sorted tuple."""
    if on_field is None:
        return ()
    if isinstance(on_field, str):
        return (on_field,)
    if isinstance(on_field, list):
        return tuple(str(item) for item in on_field)
    if isinstance(on_field, dict):
        return tuple(str(key) for key in on_field)
    return ()


def detect_pr_context_markers(text: str) -> tuple[str, ...]:
    """Identify PR context markers present in raw workflow text."""
    markers = [name for name, pattern in PR_CONTEXT_PATTERNS.items() if pattern.search(text)]
    return tuple(sorted(markers))


def audit_workflows(workflows_dir: Path) -> list[WorkflowAudit]:
    """Audit workflows in a directory for PR context usage."""
    results: list[WorkflowAudit] = []
    for path in sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            results.append(
                WorkflowAudit(
                    path=path,
                    triggers=(),
                    pr_context_markers=(),
                    valid=False,
                    error="unreadable",
                )
            )
            continue
        data = load_workflow(path, text=text)
        if data is None:
            triggers: tuple[str, ...] = ()
            valid = False
            error = "invalid-yaml"
        else:
            on_field = data.get("on")
            if on_field is None and True in data:
                on_field = data.get(True)
            triggers = tuple(sorted(normalize_triggers(on_field)))
            valid = True
            error = None
        markers = detect_pr_context_markers(text)
        results.append(
            WorkflowAudit(
                path=path,
                triggers=triggers,
                pr_context_markers=markers,
                valid=valid,
                error=error,
            )
        )
    return results


def format_table(results: list[WorkflowAudit]) -> str:
    """Render a tab-delimited report for easy copy/paste."""
    lines = ["path\ttriggers\tpr_context_markers\tvalid\terror"]
    for item in results:
        lines.append(
            "\t".join(
                [
                    str(item.path),
                    ",".join(item.triggers),
                    ",".join(item.pr_context_markers),
                    "true" if item.valid else "false",
                    item.error or "",
                ]
            )
        )
    return "\n".join(lines)


def summarize_by_triggers(results: Iterable[WorkflowAudit]) -> list[TriggerSummary]:
    """Group workflows by trigger set with aggregated PR markers."""
    groups: dict[tuple[str, ...], list[WorkflowAudit]] = {}
    for item in results:
        groups.setdefault(item.triggers, []).append(item)

    summaries: list[TriggerSummary] = []
    for triggers, items in sorted(groups.items(), key=lambda pair: pair[0]):
        markers = sorted({marker for item in items for marker in item.pr_context_markers})
        workflows = sorted(str(item.path) for item in items)
        summaries.append(
            TriggerSummary(
                triggers=triggers,
                workflows=tuple(workflows),
                pr_context_markers=tuple(markers),
            )
        )
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit workflows that read PR context for consolidation planning."
    )
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=Path(".github/workflows"),
        help="Directory containing workflow YAML files.",
    )
    parser.add_argument(
        "--only-pr-context",
        action="store_true",
        help="Only include workflows that reference PR context markers.",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json", "summary"),
        default="table",
        help="Output format.",
    )
    args = parser.parse_args()

    results = audit_workflows(args.workflows_dir)
    if args.only_pr_context:
        results = [item for item in results if item.pr_context_markers]

    if args.format == "json":
        payload = [
            {
                "path": str(item.path),
                "triggers": list(item.triggers),
                "pr_context_markers": list(item.pr_context_markers),
                "valid": item.valid,
                "error": item.error,
            }
            for item in results
        ]
        print(json.dumps(payload, indent=2))
    elif args.format == "summary":
        payload = [
            {
                "triggers": list(item.triggers),
                "workflows": list(item.workflows),
                "pr_context_markers": list(item.pr_context_markers),
            }
            for item in summarize_by_triggers(results)
        ]
        print(json.dumps(payload, indent=2))
    else:
        print(format_table(results))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
