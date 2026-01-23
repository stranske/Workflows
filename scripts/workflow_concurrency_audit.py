"""Audit workflow concurrency configuration for high-frequency triggers."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from scripts import workflow_run_counts

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
    missing_or_incorrect: bool
    action_required: str
    recommended_group: str | None
    valid: bool
    error: str | None


@dataclass(frozen=True)
class DebouncedRunSummary:
    """Aggregate comparison for debounced runs between two snapshots."""

    before_total: int
    after_total: int
    debounced_total: int
    period_label: str | None


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
        name = _normalize_trigger_name(on_field)
        return (name,) if name else ()
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
    include_non_high_frequency: bool = True,
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
            action_required = _action_required(
                high_frequency=high_frequency,
                settings=concurrency,
                has_canceling_concurrency=has_canceling_concurrency,
                valid=valid,
                error=error,
            )
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
                    missing_or_incorrect=action_required != "none",
                    action_required=action_required,
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
    "missing_or_incorrect",
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
        "true" if item.missing_or_incorrect else "false",
        "true" if item.has_canceling_concurrency else "false",
        "true" if item.has_workflow_concurrency else "false",
        "true" if item.has_workflow_canceling_concurrency else "false",
        "true" if item.has_job_concurrency else "false",
        "true" if item.has_job_canceling_concurrency else "false",
        item.action_required,
        item.recommended_group or "",
        concurrency,
    ]


def _escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


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
        row = [_escape_markdown_cell(value) for value in _table_row(item)]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _format_missing_summary(results: list[WorkflowConcurrencyAudit]) -> str:
    missing = [item for item in results if item.missing_or_incorrect]
    if not missing:
        return ""
    lines = [f"missing_or_incorrect_total\t{len(missing)}"]
    for item in missing:
        recommended = item.recommended_group or ""
        lines.append(f"missing_or_incorrect\t{item.path}\t{item.action_required}\t{recommended}")
    return "\n".join(lines)


def calculate_debounced_runs(
    before_path: Path,
    after_path: Path,
    *,
    workflow_filters: Iterable[str] = (),
    period_label: str | None = None,
) -> DebouncedRunSummary:
    """Summarize debounced run totals from before/after snapshots."""
    before_runs = workflow_run_counts.load_runs(before_path)
    after_runs = workflow_run_counts.load_runs(after_path)
    before_counts = workflow_run_counts.build_counts(before_runs, workflow_filters=workflow_filters)
    after_counts = workflow_run_counts.build_counts(after_runs, workflow_filters=workflow_filters)
    comparison = workflow_run_counts.compare_counts(before_counts, after_counts)
    before_total = sum(entry.before for entry in comparison)
    after_total = sum(entry.after for entry in comparison)
    debounced_total = sum(max(0, entry.before - entry.after) for entry in comparison)
    return DebouncedRunSummary(
        before_total=before_total,
        after_total=after_total,
        debounced_total=debounced_total,
        period_label=period_label,
    )


def _format_debounced_summary(summary: DebouncedRunSummary) -> str:
    period = summary.period_label or "unspecified"
    return (
        f"debounced_runs_total\t{summary.debounced_total}\n"
        f"debounced_runs_before_total\t{summary.before_total}\n"
        f"debounced_runs_after_total\t{summary.after_total}\n"
        f"debounced_runs_period\t{period}"
    )


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
        default=None,
        help="Include workflows that do not match high-frequency triggers (default).",
    )
    parser.add_argument(
        "--high-frequency-only",
        action="store_true",
        help="Only include workflows that match high-frequency triggers.",
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
    parser.add_argument(
        "--before-runs",
        type=Path,
        help="JSON snapshot of workflow runs before debouncing.",
    )
    parser.add_argument(
        "--after-runs",
        type=Path,
        help="JSON snapshot of workflow runs after debouncing.",
    )
    parser.add_argument(
        "--debounce-workflow",
        dest="debounce_workflows",
        action="append",
        default=[],
        help="Workflow name or substring filter for debounced run totals (repeatable).",
    )
    parser.add_argument(
        "--debounce-period",
        help="Optional label describing the debouncing measurement period.",
    )
    args = parser.parse_args()

    if args.include_non_high_frequency and args.high_frequency_only:
        parser.error(
            "--include-non-high-frequency and --high-frequency-only are mutually exclusive"
        )

    include_non_high_frequency = True
    if args.high_frequency_only:
        include_non_high_frequency = False
    elif args.include_non_high_frequency is True:
        include_non_high_frequency = True

    triggers = tuple(args.high_frequency_triggers) or DEFAULT_HIGH_FREQUENCY_TRIGGERS
    results = audit_workflows(
        args.workflows_dir,
        high_frequency_triggers=triggers,
        include_non_high_frequency=include_non_high_frequency,
    )

    debounced_summary = None
    if args.before_runs or args.after_runs:
        if not (args.before_runs and args.after_runs):
            parser.error("--before-runs and --after-runs must be provided together")
        debounced_summary = calculate_debounced_runs(
            args.before_runs,
            args.after_runs,
            workflow_filters=args.debounce_workflows,
            period_label=args.debounce_period,
        )

    if args.format == "json":
        workflows_payload = [
            {
                "path": str(item.path),
                "triggers": list(item.triggers),
                "high_frequency": item.high_frequency,
                "valid": item.valid,
                "error": item.error,
                "missing_or_incorrect": item.missing_or_incorrect,
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
        if debounced_summary is None:
            print(json.dumps(workflows_payload, indent=2))
        else:
            payload = {
                "workflows": workflows_payload,
                "debounced_runs": {
                    "before_total": debounced_summary.before_total,
                    "after_total": debounced_summary.after_total,
                    "debounced_total": debounced_summary.debounced_total,
                    "period": debounced_summary.period_label,
                },
            }
            print(json.dumps(payload, indent=2))
    elif args.format == "markdown":
        print(format_markdown(results))
    else:
        print(format_table(results))
    missing_summary = _format_missing_summary(results)
    if missing_summary and args.format != "json":
        print()
        print(missing_summary)
    if debounced_summary is not None and args.format != "json":
        print()
        print(_format_debounced_summary(debounced_summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
