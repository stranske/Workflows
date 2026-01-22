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
    cancel_is_expression: bool


@dataclass(frozen=True)
class WorkflowConcurrencyAudit:
    """Summary of concurrency configuration for a workflow."""

    path: Path
    triggers: tuple[str, ...]
    high_frequency: bool
    concurrency: tuple[ConcurrencySetting, ...]
    has_canceling_concurrency: bool
    has_workflow_concurrency: bool
    has_workflow_canceling_concurrency: bool
    has_job_concurrency: bool
    has_job_canceling_concurrency: bool
    action_required: str
    recommended_group: str | None
    valid: bool
    error: str | None


def load_workflow(path: Path) -> tuple[dict | None, str | None]:
    """Load a workflow YAML file and return the parsed content and error."""
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError:
        return None, "unreadable"
    try:
        data = yaml.safe_load(payload)
    except yaml.YAMLError:
        return None, "invalid-yaml"
    if not isinstance(data, dict):
        return None, "invalid-yaml"
    return data, None


def _normalize_trigger_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip()
    return name or None


def normalize_triggers(on_field: object) -> tuple[str, ...]:
    """Normalize workflow trigger declarations to a sorted tuple."""
    if on_field is None:
        return ()
    if isinstance(on_field, str):
        return (on_field,)
    triggers: list[str] = []
    if isinstance(on_field, list):
        for item in on_field:
            if isinstance(item, dict):
                for key in item:
                    name = _normalize_trigger_name(key)
                    if name:
                        triggers.append(name)
            else:
                name = _normalize_trigger_name(item)
                if name:
                    triggers.append(name)
    elif isinstance(on_field, dict):
        for key in on_field:
            name = _normalize_trigger_name(key)
            if name:
                triggers.append(name)
    else:
        return ()
    return tuple(sorted(set(triggers)))


def _normalize_cancel(value: object) -> tuple[bool | None, bool]:
    if isinstance(value, bool):
        return value, False
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true", False
        if lowered:
            return None, True
        return None, False
    if value is None:
        return None, False
    return None, True


def _parse_concurrency(value: object, location: str) -> ConcurrencySetting | None:
    if value is None:
        return None
    if isinstance(value, str):
        group = value.strip()
        return ConcurrencySetting(
            location=location,
            group=group or None,
            cancel_in_progress=None,
            cancel_is_expression=False,
        )
    if isinstance(value, dict):
        group = value.get("group")
        if group is not None:
            group = str(group).strip()
            if not group:
                group = None
        cancel, cancel_is_expression = _normalize_cancel(value.get("cancel-in-progress"))
        return ConcurrencySetting(
            location=location,
            group=group,
            cancel_in_progress=cancel,
            cancel_is_expression=cancel_is_expression,
        )
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
    return any(
        bool(setting.group) and (setting.cancel_in_progress is True or setting.cancel_is_expression)
        for setting in settings
    )


def _filter_concurrency(
    settings: tuple[ConcurrencySetting, ...], *, location: str
) -> tuple[ConcurrencySetting, ...]:
    return tuple(setting for setting in settings if setting.location == location)


def _action_required(
    *,
    high_frequency: bool,
    settings: tuple[ConcurrencySetting, ...],
    has_canceling_concurrency: bool,
    valid: bool,
    error: str | None,
) -> str:
    if not valid:
        return error or "invalid"
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
    if "issue_comment" in lowered or "issues" in lowered:
        if "pull_request" in lowered or "pull_request_target" in lowered:
            return (
                "${{ github.workflow }}-issue-${{ github.event.issue.number || "
                "github.event.pull_request.number || github.ref }}"
            )
        return "${{ github.workflow }}-issue-${{ github.event.issue.number || github.ref }}"
    if "pull_request" in lowered or "pull_request_target" in lowered:
        return "${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}"
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
        data, error = load_workflow(path)
        if data is None:
            triggers: tuple[str, ...] = ()
            concurrency: tuple[ConcurrencySetting, ...] = ()
            valid = False
        else:
            on_field = data.get("on")
            if on_field is None and True in data:
                on_field = data.get(True)
            triggers = tuple(sorted(normalize_triggers(on_field)))
            concurrency = collect_concurrency(data)
            valid = True
            error = None
        high_frequency = any(trigger.lower() in normalized_triggers for trigger in triggers)
        if high_frequency or include_non_high_frequency or not valid:
            workflow_concurrency = _filter_concurrency(concurrency, location="workflow")
            job_concurrency = tuple(
                setting for setting in concurrency if setting.location.startswith("job:")
            )
            has_canceling_concurrency = _has_canceling_concurrency(concurrency)
            has_workflow_concurrency = bool(workflow_concurrency)
            has_workflow_canceling_concurrency = _has_canceling_concurrency(workflow_concurrency)
            has_job_concurrency = bool(job_concurrency)
            has_job_canceling_concurrency = _has_canceling_concurrency(job_concurrency)
            results.append(
                WorkflowConcurrencyAudit(
                    path=path,
                    triggers=triggers,
                    high_frequency=high_frequency,
                    concurrency=concurrency,
                    has_canceling_concurrency=has_canceling_concurrency,
                    has_workflow_concurrency=has_workflow_concurrency,
                    has_workflow_canceling_concurrency=has_workflow_canceling_concurrency,
                    has_job_concurrency=has_job_concurrency,
                    has_job_canceling_concurrency=has_job_canceling_concurrency,
                    action_required=_action_required(
                        high_frequency=high_frequency,
                        settings=concurrency,
                        has_canceling_concurrency=has_canceling_concurrency,
                        valid=valid,
                        error=error,
                    ),
                    recommended_group=(
                        suggest_concurrency_group(triggers) if high_frequency else None
                    ),
                    valid=valid,
                    error=error,
                )
            )
    return results


TABLE_HEADERS = (
    "path",
    "triggers",
    "high_frequency",
    "valid",
    "error",
    "has_canceling_concurrency",
    "workflow_has_concurrency",
    "workflow_has_canceling_concurrency",
    "job_has_concurrency",
    "job_has_canceling_concurrency",
    "action_required",
    "recommended_group",
    "concurrency",
)


def _format_cancel(setting: ConcurrencySetting) -> str:
    if setting.cancel_in_progress is True:
        return "true"
    if setting.cancel_in_progress is False:
        return "false"
    if setting.cancel_is_expression:
        return "expr"
    return "unset"


def _table_row(item: WorkflowConcurrencyAudit) -> list[str]:
    concurrency = ";".join(
        f"{setting.location}:{setting.group or 'none'}:" f"{_format_cancel(setting)}"
        for setting in item.concurrency
    )
    return [
        str(item.path),
        ",".join(item.triggers),
        "true" if item.high_frequency else "false",
        "true" if item.valid else "false",
        item.error or "",
        "true" if item.has_canceling_concurrency else "false",
        "true" if item.has_workflow_concurrency else "false",
        "true" if item.has_workflow_canceling_concurrency else "false",
        "true" if item.has_job_concurrency else "false",
        "true" if item.has_job_canceling_concurrency else "false",
        item.action_required,
        item.recommended_group or "",
        concurrency,
    ]


def format_table(results: list[WorkflowConcurrencyAudit]) -> str:
    """Render a tab-delimited report for easy copy/paste."""
    lines = ["\t".join(TABLE_HEADERS)]
    lines.extend("\t".join(_table_row(item)) for item in results)
    return "\n".join(lines)


def format_markdown(results: list[WorkflowConcurrencyAudit]) -> str:
    """Render a Markdown table report."""
    lines = [
        "| " + " | ".join(TABLE_HEADERS) + " |",
        "| " + " | ".join(["---"] * len(TABLE_HEADERS)) + " |",
    ]
    for item in results:
        lines.append("| " + " | ".join(_table_row(item)) + " |")
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
        choices=("table", "markdown", "json"),
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
                "valid": item.valid,
                "error": item.error,
                "has_canceling_concurrency": item.has_canceling_concurrency,
                "has_workflow_concurrency": item.has_workflow_concurrency,
                "has_workflow_canceling_concurrency": item.has_workflow_canceling_concurrency,
                "has_job_concurrency": item.has_job_concurrency,
                "has_job_canceling_concurrency": item.has_job_canceling_concurrency,
                "action_required": item.action_required,
                "recommended_group": item.recommended_group,
                "concurrency": [
                    {
                        "location": setting.location,
                        "group": setting.group,
                        "cancel_in_progress": setting.cancel_in_progress,
                        "cancel_is_expression": setting.cancel_is_expression,
                    }
                    for setting in item.concurrency
                ],
            }
            for item in results
        ]
        print(json.dumps(payload, indent=2))
    elif args.format == "markdown":
        print(format_markdown(results))
    else:
        print(format_table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
