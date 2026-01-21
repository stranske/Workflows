"""Audit workflow concurrency configuration for high-frequency triggers."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_HIGH_FREQUENCY_TRIGGERS = (
    "issue_comment",
    "issues",
    "merge_group",
    "pull_request",
    "pull_request_target",
    "push",
    "workflow_run",
)


@dataclass(frozen=True)
class ConcurrencySetting:
    """Normalized concurrency configuration."""

    location: str
    group: str | None
    cancel_in_progress: bool | None


@dataclass(frozen=True)
class WorkflowConcurrencyAudit:
    """Summary of concurrency configuration for a workflow."""

    path: Path
    triggers: tuple[str, ...]
    high_frequency: bool
    concurrency: tuple[ConcurrencySetting, ...]
    has_canceling_concurrency: bool
    action_required: str
    recommended_group: str | None


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
        return tuple(str(key) for key in on_field)
    return ()


def _normalize_cancel(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
    return None


def _parse_concurrency(value: object, location: str) -> ConcurrencySetting | None:
    if value is None:
        return None
    if isinstance(value, str):
        return ConcurrencySetting(location=location, group=value, cancel_in_progress=None)
    if isinstance(value, dict):
        group = value.get("group")
        if group is not None:
            group = str(group)
        cancel = _normalize_cancel(value.get("cancel-in-progress"))
        return ConcurrencySetting(location=location, group=group, cancel_in_progress=cancel)
    return None


def collect_concurrency(data: dict) -> tuple[ConcurrencySetting, ...]:
    """Collect concurrency settings from top-level and jobs."""
    settings: list[ConcurrencySetting] = []
    top = _parse_concurrency(data.get("concurrency"), "workflow")
    if top is not None:
        settings.append(top)
    for job_id, job in (data.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        parsed = _parse_concurrency(job.get("concurrency"), f"job:{job_id}")
        if parsed is not None:
            settings.append(parsed)
    return tuple(settings)


def _has_canceling_concurrency(settings: tuple[ConcurrencySetting, ...]) -> bool:
    return any(setting.cancel_in_progress is True and bool(setting.group) for setting in settings)


def _action_required(
    *,
    high_frequency: bool,
    settings: tuple[ConcurrencySetting, ...],
    has_canceling_concurrency: bool,
) -> str:
    if not high_frequency:
        return "none"
    if has_canceling_concurrency:
        return "none"
    if not any(setting.group for setting in settings):
        return "add_concurrency"
    return "set_cancel_in_progress_true"


def suggest_concurrency_group(triggers: tuple[str, ...]) -> str | None:
    """Recommend a concurrency group expression based on workflow triggers."""
    lowered = {trigger.lower() for trigger in triggers}
    if "pull_request" in lowered or "pull_request_target" in lowered:
        return "${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}"
    if "issue_comment" in lowered or "issues" in lowered:
        return "${{ github.workflow }}-issue-${{ github.event.issue.number || github.ref }}"
    if "workflow_run" in lowered:
        return (
            "${{ github.workflow }}-workflow-run-${{ "
            "github.event.workflow_run.pull_requests[0].number || "
            "github.event.workflow_run.id || "
            "github.run_id }}"
        )
    if "merge_group" in lowered:
        return (
            "${{ github.workflow }}-merge-group-${{ "
            "github.event.merge_group.head_sha || github.sha }}"
        )
    if "push" in lowered:
        return "${{ github.workflow }}-${{ github.ref }}"
    return None


def audit_workflows(
    workflows_dir: Path,
    high_frequency_triggers: tuple[str, ...] = DEFAULT_HIGH_FREQUENCY_TRIGGERS,
    include_non_high_frequency: bool = False,
) -> list[WorkflowConcurrencyAudit]:
    """Audit workflows in a directory for concurrency coverage."""
    normalized_triggers = {trigger.lower() for trigger in high_frequency_triggers}
    results: list[WorkflowConcurrencyAudit] = []
    for path in sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml")):
        data = load_workflow(path)
        if data is None:
            triggers: tuple[str, ...] = ()
            concurrency: tuple[ConcurrencySetting, ...] = ()
        else:
            on_field = data.get("on")
            if on_field is None and True in data:
                on_field = data.get(True)
            triggers = tuple(sorted(normalize_triggers(on_field)))
            concurrency = collect_concurrency(data)
        high_frequency = any(trigger.lower() in normalized_triggers for trigger in triggers)
        if high_frequency or include_non_high_frequency:
            has_canceling_concurrency = _has_canceling_concurrency(concurrency)
            results.append(
                WorkflowConcurrencyAudit(
                    path=path,
                    triggers=triggers,
                    high_frequency=high_frequency,
                    concurrency=concurrency,
                    has_canceling_concurrency=has_canceling_concurrency,
                    action_required=_action_required(
                        high_frequency=high_frequency,
                        settings=concurrency,
                        has_canceling_concurrency=has_canceling_concurrency,
                    ),
                    recommended_group=(
                        suggest_concurrency_group(triggers) if high_frequency else None
                    ),
                )
            )
    return results


def format_table(results: list[WorkflowConcurrencyAudit]) -> str:
    """Render a tab-delimited report for easy copy/paste."""
    lines = [
        "path\ttriggers\thigh_frequency\thas_canceling_concurrency"
        "\taction_required\trecommended_group\tconcurrency"
    ]
    for item in results:
        concurrency = ";".join(
            f"{setting.location}:{setting.group or 'none'}:"
            f"{setting.cancel_in_progress if setting.cancel_in_progress is not None else 'unset'}"
            for setting in item.concurrency
        )
        lines.append(
            "\t".join(
                [
                    str(item.path),
                    ",".join(item.triggers),
                    "true" if item.high_frequency else "false",
                    "true" if item.has_canceling_concurrency else "false",
                    item.action_required,
                    item.recommended_group or "",
                    concurrency,
                ]
            )
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit workflow concurrency settings for high-frequency triggers."
    )
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=Path(".github/workflows"),
        help="Directory containing workflow YAML files.",
    )
    parser.add_argument(
        "--include-non-high-frequency",
        action="store_true",
        help="Include workflows that do not match high-frequency triggers.",
    )
    parser.add_argument(
        "--high-frequency-trigger",
        action="append",
        dest="high_frequency_triggers",
        default=[],
        help="Trigger to treat as high frequency (repeatable).",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format.",
    )
    args = parser.parse_args()

    triggers = tuple(args.high_frequency_triggers) or DEFAULT_HIGH_FREQUENCY_TRIGGERS
    results = audit_workflows(
        args.workflows_dir,
        high_frequency_triggers=triggers,
        include_non_high_frequency=args.include_non_high_frequency,
    )

    if args.format == "json":
        payload = [
            {
                "path": str(item.path),
                "triggers": list(item.triggers),
                "high_frequency": item.high_frequency,
                "has_canceling_concurrency": item.has_canceling_concurrency,
                "action_required": item.action_required,
                "recommended_group": item.recommended_group,
                "concurrency": [
                    {
                        "location": setting.location,
                        "group": setting.group,
                        "cancel_in_progress": setting.cancel_in_progress,
                    }
                    for setting in item.concurrency
                ],
            }
            for item in results
        ]
        print(json.dumps(payload, indent=2))
    else:
        print(format_table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
