from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SummaryContext:
    doc_only: bool
    run_core: bool
    reason: str
    python_result: str
    docker_result: str
    docker_changed: bool
    artifacts_root: Path
    summary_path: Path | None
    output_path: Path | None


@dataclass(slots=True)
class SummaryResult:
    lines: list[str]
    state: str
    description: str
    cosmetic_failure: bool = False
    failure_checks: tuple[str, ...] = ()
    format_failure: bool = False


PRIORITY: dict[str, int] = {
    "failure": 0,
    "timed_out": 1,
    "cancelled": 2,
    "success": 3,
    "skipped": 4,
    "pending": 5,
}


def _normalize(value: str | None, default: str = "unknown") -> str:
    if value is None:
        return default
    stripped = value.strip().lower()
    return stripped or default


def _emoji(outcome: str) -> str:
    return {
        "success": "✅",
        "skipped": "⏭️",
        "failure": "❌",
        "cancelled": "⏹️",
        "timed_out": "⏱️",
        "pending": "⏳",
    }.get(outcome, "❔")


def _friendly(outcome: str) -> str:
    return outcome.replace("_", " ") if outcome else "unknown"


def _pick_best(outcomes: Iterable[str]) -> str:
    best = "pending"
    for outcome in outcomes:
        candidate = outcome or "pending"
        if PRIORITY.get(candidate, 99) < PRIORITY.get(best, 99):
            best = candidate
    return best


def _aggregate(entries: Iterable[tuple[str, str]]) -> tuple[str, str]:
    pairs = list(entries)
    best = _pick_best([outcome for _, outcome in pairs])
    detail = ", ".join(f"{runtime}: {_friendly(outcome)}" for runtime, outcome in sorted(pairs))
    return best, detail or "no runs"


def _normalize_check_outcome(section: Mapping[str, object] | None) -> str:
    if isinstance(section, Mapping):
        outcome = section.get("outcome")
        if isinstance(outcome, str):
            return _normalize(outcome)
    return "unknown"


def _load_summary_records(artifacts_root: Path) -> list[dict]:
    records: list[dict] = []
    base = artifacts_root / "downloads"
    if not base.exists():
        return records

    for path in sorted(base.rglob("**/summary.json")):
        try:
            job_name = path.relative_to(artifacts_root).parts[1]
        except (IndexError, ValueError):
            job_name = "unknown"

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict):
            data.setdefault("job_name", job_name)
            records.append(data)

    return records


def _detect_cosmetic_failure(
    records: Iterable[Mapping[str, object]],
) -> tuple[bool, tuple[str, ...]]:
    allowed_failures = {"format", "lint"}
    benign_outcomes = {"success", "skipped", "pending"}
    cosmetic_hits: set[str] = set()
    has_records = False

    for record in records:
        if not isinstance(record, Mapping):
            continue
        has_records = True
        checks = record.get("checks")
        if not isinstance(checks, Mapping):
            return False, ()

        for name, section in checks.items():
            outcome = _normalize_check_outcome(section if isinstance(section, Mapping) else None)
            if outcome in benign_outcomes:
                continue
            if name in allowed_failures and outcome == "failure":
                cosmetic_hits.add(str(name))
                continue
            return False, ()

    if not has_records or not cosmetic_hits:
        return False, ()

    return True, tuple(sorted(cosmetic_hits))


def _collect_table(records: Iterable[Mapping[str, object]]) -> tuple[
    list[str],
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[str],
    dict[str, list[str]],
]:
    table = [
        "| Runtime | Lint | Type | Tests | Coverage min | Coverage % |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lint_entries: list[tuple[str, str]] = []
    type_entries: list[tuple[str, str]] = []
    test_entries: list[tuple[str, str]] = []
    coverage_entries: list[tuple[str, str]] = []
    coverage_percents: list[str] = []
    job_results: dict[str, list[str]] = {}

    for record in sorted(records, key=lambda item: str(item.get("python_version", ""))):
        runtime = str(record.get("python_version", "unknown"))
        job_name = str(record.get("job_name") or runtime)
        checks = record.get("checks") if isinstance(record.get("checks"), Mapping) else {}

        def _check(name: str, checks_map=checks) -> str:
            return _normalize_check_outcome(
                checks_map.get(name) if isinstance(checks_map, Mapping) else None
            )

        lint = _check("lint")
        typing = _check("type_check")
        tests = _check("tests")
        coverage_min = _check("coverage_minimum")

        lint_entries.append((runtime, lint))
        type_entries.append((runtime, typing))
        test_entries.append((runtime, tests))
        coverage_entries.append((runtime, coverage_min))
        job_results.setdefault(job_name, []).extend([lint, typing, tests, coverage_min])

        coverage_info = (
            record.get("coverage") if isinstance(record.get("coverage"), Mapping) else {}
        )
        percent = coverage_info.get("percent") if isinstance(coverage_info, Mapping) else None
        if isinstance(percent, (int, float)):
            coverage_percents.append(f"{runtime}: {percent:.2f}%")
            percent_display = f"{percent:.2f}%"
        else:
            percent_display = "—"

        table.append(
            f"| {runtime} | {_emoji(lint)} {_friendly(lint)} | {_emoji(typing)} {_friendly(typing)} | {_emoji(tests)} {_friendly(tests)} | {_emoji(coverage_min)} {_friendly(coverage_min)} | {percent_display} |"
        )

    return (
        table,
        lint_entries,
        type_entries,
        test_entries,
        coverage_entries,
        coverage_percents,
        job_results,
    )


def _doc_only_lines(reason: str) -> list[str]:
    if not reason:
        reason = "docs_only"
    note = (
        "Docs-only change detected; heavy checks skipped."
        if reason == "docs_only"
        else f"Docs-only change detected; heavy checks skipped ({reason})."
    )
    lines = [
        "### Gate status",
        note,
        "Docs-only fast-pass engaged; heavy jobs were skipped.",
        "| Job | Result |",
        "| --- | --- |",
        "| docs-only | success |",
    ]
    return lines


def _append_job_table(
    lines: list[str], job_results: Mapping[str, Iterable[str]], docker_result: str
) -> None:
    lines.append("")
    lines.append("| Job | Result |")
    lines.append("| --- | --- |")
    for job_name, outcomes in sorted(job_results.items()):
        result = _pick_best(outcomes)
        lines.append(f"| {job_name} | {_friendly(result)} |")
    lines.append(f"| docker-smoke | {_friendly(docker_result)} |")


def _active_lines(
    table: list[str],
    lint_entries: Iterable[tuple[str, str]],
    type_entries: Iterable[tuple[str, str]],
    test_entries: Iterable[tuple[str, str]],
    coverage_entries: Iterable[tuple[str, str]],
    coverage_percents: Iterable[str],
    job_results: Mapping[str, list[str]],
    docker_result: str,
) -> list[str]:
    lines = ["### Gate status", *table]
    _append_job_table(lines, job_results, docker_result)

    lint_status, lint_detail = _aggregate(lint_entries)
    type_status, type_detail = _aggregate(type_entries)
    test_status, test_detail = _aggregate(test_entries)
    coverage_status, coverage_detail = _aggregate(coverage_entries)

    lines.append("")
    lines.append(f"- Lint: {_emoji(lint_status)} {_friendly(lint_status)} ({lint_detail})")
    lines.append(f"- Type check: {_emoji(type_status)} {_friendly(type_status)} ({type_detail})")
    lines.append(f"- Tests: {_emoji(test_status)} {_friendly(test_status)} ({test_detail})")
    lines.append(
        f"- Coverage minimum: {_emoji(coverage_status)} {_friendly(coverage_status)} ({coverage_detail})"
    )
    coverage_summary = list(coverage_percents)
    if coverage_summary:
        lines.append(f"- Reported coverage: {', '.join(coverage_summary)}")

    return lines


def summarize(context: SummaryContext) -> SummaryResult:
    if context.doc_only or not context.run_core:
        lines = _doc_only_lines(context.reason)
        description = (
            "Gate fast-pass: docs-only change detected; heavy checks skipped."
            if context.reason == "docs_only"
            else f"Docs-only change; heavy checks skipped ({context.reason or 'docs_only'})."
        )
        return SummaryResult(lines=lines, state="success", description=description)

    records = _load_summary_records(context.artifacts_root)

    (
        table,
        lint_entries,
        type_entries,
        test_entries,
        coverage_entries,
        coverage_percents,
        job_results,
    ) = _collect_table(records)

    lines = _active_lines(
        table,
        lint_entries,
        type_entries,
        test_entries,
        coverage_entries,
        coverage_percents,
        job_results,
        context.docker_result,
    )

    state = "success"
    description = "All Gate checks succeeded."

    python_result = _normalize(context.python_result or "success")
    docker_result_norm = _normalize(context.docker_result or "skipped")
    cosmetic_failure = False
    failure_checks: tuple[str, ...] = ()
    format_failure = False

    # Python CI skipped is OK if run_core is false (doc/workflow-only changes)
    if python_result not in ("success", "skipped") or (
        python_result == "skipped" and context.run_core
    ):
        state = "failure"
        description = f"Python CI result: {python_result}."
        cosmetic_failure, failure_checks = _detect_cosmetic_failure(records)
        format_failure = "format" in failure_checks
    elif context.docker_changed and docker_result_norm != "success":
        state = "failure"
        description = f"Docker smoke result: {docker_result_norm}."
    elif not context.docker_changed:
        lines.append("- Docker smoke skipped: no Docker-related changes detected.")

    adjusted_lines = []
    for line in lines:
        if line.startswith("| docker-smoke"):
            adjusted_lines.append(f"| docker-smoke | {_friendly(docker_result_norm)} |")
        else:
            adjusted_lines.append(line)

    return SummaryResult(
        lines=adjusted_lines,
        state=state,
        description=description,
        cosmetic_failure=cosmetic_failure,
        failure_checks=failure_checks,
        format_failure=format_failure,
    )


def _resolve_path(env_var: str) -> Path | None:
    value = os.environ.get(env_var)
    if not value:
        return None
    return Path(value)


def build_context() -> SummaryContext:
    doc_only = _normalize(os.environ.get("DOC_ONLY"), "false") == "true"
    run_core = _normalize(os.environ.get("RUN_CORE"), "true") == "true"
    reason = os.environ.get("REASON") or ""
    python_result = os.environ.get("PYTHON_RESULT") or "skipped"
    docker_result = os.environ.get("DOCKER_RESULT") or "skipped"
    docker_changed = _normalize(os.environ.get("DOCKER_CHANGED"), "false") == "true"
    artifacts_root = Path(os.environ.get("GATE_ARTIFACTS_ROOT", "gate_artifacts"))
    summary_path = _resolve_path("GITHUB_STEP_SUMMARY")
    output_path = _resolve_path("GITHUB_OUTPUT")

    return SummaryContext(
        doc_only=doc_only,
        run_core=run_core,
        reason=reason,
        python_result=python_result,
        docker_result=docker_result,
        docker_changed=docker_changed,
        artifacts_root=artifacts_root,
        summary_path=summary_path,
        output_path=output_path,
    )


def _write_summary(result: SummaryResult, summary_path: Path | None) -> None:
    if summary_path is None:
        return
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(result.lines) + "\n")


def _write_outputs(result: SummaryResult, output_path: Path | None) -> None:
    if output_path is None:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"state={result.state}\n")
        handle.write(f"description={result.description}\n")
        handle.write(f"cosmetic_failure={'true' if result.cosmetic_failure else 'false'}\n")
        if result.failure_checks:
            handle.write("failure_checks=" + ",".join(result.failure_checks) + "\n")
        else:
            handle.write("failure_checks=\n")
        handle.write(f"format_failure={'true' if result.format_failure else 'false'}\n")


def main() -> int:
    context = build_context()
    result = summarize(context)
    _write_summary(result, context.summary_path)
    _write_outputs(result, context.output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
