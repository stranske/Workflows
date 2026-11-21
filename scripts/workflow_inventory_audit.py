"""Classify workflow files for Maint 66 monthly-audit inventory reviews."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml
from scripts.workflow_concurrency_audit import normalize_triggers


class WorkflowInventoryError(Exception):
    """Workflow inventory could not be loaded or classified."""


class _WorkflowLoader(yaml.SafeLoader):
    """Parse workflow YAML without coercing GitHub's `on` key to boolean True."""


_WorkflowLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in values if tag != "tag:yaml.org,2002:bool"]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_workflow_document(path: Path, *, text: str | None = None) -> dict:
    """Load a workflow dict, preserving the `on` trigger block."""
    if text is None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WorkflowInventoryError(f"cannot read {path}: {exc}") from exc
    try:
        data = yaml.load(text, Loader=_WorkflowLoader)
    except yaml.YAMLError as exc:
        raise WorkflowInventoryError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkflowInventoryError(f"workflow root must be a mapping: {path}")
    return data

AUDIT_CATEGORIES = (
    "reusable_call_only",
    "reusable_with_independent_trigger",
    "scheduled",
    "manual_utility",
    "event_driven",
    "unknown_trigger",
)


@dataclass(frozen=True)
class WorkflowInventoryRow:
    """One workflow file and its Maint 66 inventory classification."""

    stem: str
    display_name: str
    relative_path: str
    triggers: tuple[str, ...]
    excluded_from_not_run: bool
    audit_category: str
    has_run_name: bool


def excluded_from_not_run_inventory(triggers: tuple[str, ...]) -> bool:
    """Return True when Maint 66 should skip a workflow in the not-run section."""
    if "workflow_call" not in triggers:
        return False
    return all(trigger == "workflow_call" for trigger in triggers)


def _display_name(data: dict, stem: str) -> str:
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return stem


def classify_audit_category(triggers: tuple[str, ...], *, excluded_from_not_run: bool) -> str:
    """Map triggers to the November 2026 audit disposition buckets."""
    if excluded_from_not_run:
        return "reusable_call_only"
    if "workflow_call" in triggers:
        return "reusable_with_independent_trigger"
    if not triggers:
        return "unknown_trigger"
    if triggers == ("workflow_dispatch",):
        return "manual_utility"
    if "schedule" in triggers and "push" not in triggers and "pull_request" not in triggers:
        return "scheduled"
    if set(triggers) <= {"workflow_dispatch", "workflow_call"}:
        return "manual_utility"
    return "event_driven"


def inspect_workflow_file(path: Path) -> WorkflowInventoryRow:
    """Load one workflow and return its inventory row."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkflowInventoryError(f"cannot read {path}: {exc}") from exc
    data = load_workflow_document(path, text=text)
    stem = path.stem
    triggers = normalize_triggers(data.get("on"))
    excluded = excluded_from_not_run_inventory(triggers)
    return WorkflowInventoryRow(
        stem=stem,
        display_name=_display_name(data, stem),
        relative_path=f".github/workflows/{path.name}",
        triggers=triggers,
        excluded_from_not_run=excluded,
        audit_category=classify_audit_category(triggers, excluded_from_not_run=excluded),
        has_run_name="run-name:" in text,
    )


def iter_workflow_inventory(workflows_dir: Path) -> list[WorkflowInventoryRow]:
    """Return sorted inventory rows for every `*.yml` file in the workflows directory."""
    rows: list[WorkflowInventoryRow] = []
    errors: list[str] = []
    for path in sorted(workflows_dir.glob("*.yml")):
        try:
            rows.append(inspect_workflow_file(path))
        except WorkflowInventoryError as exc:
            errors.append(str(exc))
    if errors:
        raise WorkflowInventoryError("\n".join(errors))
    return rows


def not_run_candidates(rows: Iterable[WorkflowInventoryRow]) -> list[WorkflowInventoryRow]:
    """Rows that Maint 66 may list when no runs exist for the workflow path."""
    return [row for row in rows if not row.excluded_from_not_run]


def format_trigger_list(triggers: tuple[str, ...]) -> str:
    return ", ".join(triggers) if triggers else "(none parsed)"


def render_markdown_summary(rows: list[WorkflowInventoryRow]) -> str:
    """Render a Maint 66-style inventory appendix for documentation."""
    by_category: dict[str, list[WorkflowInventoryRow]] = {cat: [] for cat in AUDIT_CATEGORIES}
    for row in rows:
        by_category.setdefault(row.audit_category, []).append(row)

    lines = [
        "## Workflow inventory appendix (generated)",
        "",
        f"Total workflow files: **{len(rows)}**.",
        f"Excluded from not-run (`workflow_call` without independent trigger): "
        f"**{sum(1 for r in rows if r.excluded_from_not_run)}**.",
        f"Eligible for not-run listing when path absent from stats: "
        f"**{len(not_run_candidates(rows))}**.",
        "",
    ]
    category_blurbs = {
        "reusable_call_only": (
            "Maint 66 omits these from **Workflows Not Run**; zero direct runs is expected."
        ),
        "reusable_with_independent_trigger": (
            "Callable workflows that also declare an independent `on:` trigger "
            "(for example `workflow_dispatch`, `schedule`, `push`, or `issues`)."
        ),
        "scheduled": ("Cron-driven; may show as not-run in a quiet 30-day window."),
        "manual_utility": ("On-demand `workflow_dispatch` utilities."),
        "event_driven": (
            "Push, PR, issue, or `workflow_run` driven; a not-run row is usually a "
            "path-matching false positive (pre-November fix) or a new file."
        ),
        "unknown_trigger": ("Missing or unparsable `on:` block — review manually."),
    }
    for category in AUDIT_CATEGORIES:
        bucket = by_category.get(category, [])
        if not bucket:
            continue
        lines.append(f"### {category} ({len(bucket)})")
        lines.append("")
        lines.append(category_blurbs.get(category, ""))
        lines.append("")
        lines.append("| File | Triggers | `run-name` |")
        lines.append("| --- | --- | --- |")
        for row in bucket:
            run_name = "yes" if row.has_run_name else "no"
            lines.append(f"| `{row.stem}.yml` | {format_trigger_list(row.triggers)} | {run_name} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=Path(".github/workflows"),
        help="Directory containing workflow YAML files",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print a Markdown appendix suitable for audit documentation",
    )
    parser.add_argument(
        "--check-call-only-skip",
        metavar="STEM",
        help="Exit 0 when Maint 66 should omit STEM from not-run inventory",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.check_call_only_skip:
        path = args.workflows_dir.resolve() / f"{args.check_call_only_skip}.yml"
        try:
            row = inspect_workflow_file(path)
        except WorkflowInventoryError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0 if row.excluded_from_not_run else 1
    try:
        rows = iter_workflow_inventory(args.workflows_dir.resolve())
    except WorkflowInventoryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.markdown:
        print(render_markdown_summary(rows), end="")
        return 0
    for row in rows:
        print(
            f"{row.stem}\t{row.audit_category}\t"
            f"excluded={row.excluded_from_not_run}\t{format_trigger_list(row.triggers)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
