"""Audit workflows that read PR context to inform consolidation design."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

PR_CONTEXT_PATTERNS = {
    "github.event.pull_request": re.compile(r"github\.event\.pull_request"),
    "github.event.issue.pull_request": re.compile(r"github\.event\.issue\.pull_request"),
    "context.payload.pull_request": re.compile(r"context\.payload\.pull_request"),
    "workflow_run.pull_requests": re.compile(r"workflow_run\.pull_requests"),
    "pull_request_number": re.compile(r"\bpull_request_number\b"),
}


@dataclass(frozen=True)
class WorkflowAudit:
    """Summary of PR context usage for a workflow file."""

    path: Path
    triggers: tuple[str, ...]
    pr_context_markers: tuple[str, ...]
    valid: bool


def load_workflow(path: Path) -> dict | None:
    """Load a workflow YAML file and return the parsed content."""
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


def normalize_triggers(on_field: object) -> tuple[str, ...]:
    """Normalize workflow trigger declarations to a sorted tuple."""
    if on_field is None:
        return ()
    if isinstance(on_field, str):
        return (on_field,)
    if isinstance(on_field, list):
        return tuple(str(item) for item in on_field)
    if isinstance(on_field, dict):
        return tuple(str(key) for key in on_field.keys())
    return ()


def detect_pr_context_markers(text: str) -> tuple[str, ...]:
    """Identify PR context markers present in raw workflow text."""
    markers = [name for name, pattern in PR_CONTEXT_PATTERNS.items() if pattern.search(text)]
    return tuple(sorted(markers))


def audit_workflows(workflows_dir: Path) -> list[WorkflowAudit]:
    """Audit workflows in a directory for PR context usage."""
    results: list[WorkflowAudit] = []
    for path in sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        data = load_workflow(path)
        if data is None:
            triggers: tuple[str, ...] = ()
            valid = False
        else:
            on_field = data.get("on")
            if on_field is None and True in data:
                on_field = data.get(True)
            triggers = tuple(sorted(normalize_triggers(on_field)))
            valid = True
        markers = detect_pr_context_markers(text)
        results.append(
            WorkflowAudit(
                path=path,
                triggers=triggers,
                pr_context_markers=markers,
                valid=valid,
            )
        )
    return results


def format_table(results: list[WorkflowAudit]) -> str:
    """Render a tab-delimited report for easy copy/paste."""
    lines = ["path\ttriggers\tpr_context_markers\tvalid"]
    for item in results:
        lines.append(
            "\t".join(
                [
                    str(item.path),
                    ",".join(item.triggers),
                    ",".join(item.pr_context_markers),
                    "true" if item.valid else "false",
                ]
            )
        )
    return "\n".join(lines)


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
        choices=("table", "json"),
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
            }
            for item in results
        ]
        print(json.dumps(payload, indent=2))
    else:
        print(format_table(results))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
