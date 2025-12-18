"""Helpers for building the consolidated post-CI run summary.

Originally wired to the legacy post-CI follower, the helper now powers the
inline `summary` job in `pr-00-gate.yml`. Unit tests keep coverage without
requiring the full workflow to run on GitHub.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, MutableSequence, Sequence, TypedDict


@dataclass(frozen=True)
class JobRecord:
    name: str
    state: str | None
    url: str | None
    highlight: bool


@dataclass(frozen=True)
class RunRecord:
    key: str
    display_name: str
    present: bool
    state: str | None
    attempt: int | None
    label: str
    url: str | None


class RequiredJobGroup(TypedDict):
    label: str
    patterns: List[str]


DEFAULT_REQUIRED_JOB_GROUPS: List[RequiredJobGroup] = [
    {
        "label": "python ci (3.11)",
        "patterns": [r"(python\s*ci|core\s*(tests?)?).*(3\.11|py\.?311)"],
    },
    {
        "label": "python ci (3.12)",
        "patterns": [r"(python\s*ci|core\s*(tests?)?).*(3\.12|py\.?312)"],
    },
    {"label": "docker smoke", "patterns": [r"docker.*smoke|smoke.*docker"]},
    {"label": "gate", "patterns": [r"gate"]},
]


REQUIRED_CONTEXTS_PATH = Path(".github/config/required-contexts.json")


def _copy_required_groups(
    groups: Sequence[RequiredJobGroup],
) -> List[RequiredJobGroup]:
    return [{"label": group["label"], "patterns": list(group["patterns"])} for group in groups]


def _badge(state: str | None) -> str:
    if not state:
        return "⏳"
    normalized = state.lower()
    if normalized == "success":
        return "✅"
    if normalized in {"failure", "cancelled", "timed_out", "action_required"}:
        return "❌"
    if normalized == "skipped":
        return "⏭️"
    if normalized in {"in_progress", "queued", "waiting", "requested"}:
        return "⏳"
    return "⏳"


def _display_state(state: str | None) -> str:
    if not state:
        return "pending"
    text = str(state).strip()
    if not text:
        return "pending"
    return text.replace("_", " ").lower()


def _priority(state: str | None) -> int:
    normalized = (state or "").lower()
    if normalized in {"failure", "cancelled", "timed_out", "action_required"}:
        return 0
    if normalized in {"in_progress", "queued", "waiting", "requested"}:
        return 1
    if normalized == "success":
        return 2
    if normalized == "skipped":
        return 3
    return 4


def _combine_states(states: Iterable[str | None]) -> str:
    lowered: List[str] = [s.lower() for s in states if isinstance(s, str) and s]
    if not lowered:
        return "missing"
    for candidate in ("failure", "cancelled", "timed_out", "action_required"):
        if candidate in lowered:
            return candidate
    for candidate in ("in_progress", "queued", "waiting", "requested"):
        if candidate in lowered:
            return candidate
    if all(state == "skipped" for state in lowered):
        return "skipped"
    if "success" in lowered:
        return "success"
    return lowered[0]


def _slugify(value: str) -> str:
    collapsed = re.sub(r"[^a-z0-9]+", "-", value.casefold())
    return re.sub(r"-+", "-", collapsed).strip("-")


class RequiredJobRule(TypedDict):
    key: str
    label: str
    slug_variants: List[List[str]]
    fallback_patterns: List[str]


REQUIRED_JOB_RULES: List[RequiredJobRule] = [
    {
        "key": "core311",
        "label": "core tests (3.11)",
        "slug_variants": [
            ["core", "3-11"],
            ["core", "311"],
            ["py311"],
            ["3-11", "tests"],
        ],
        "fallback_patterns": [r"core\s*(tests?)?.*(3\.11|py\.?311)"],
    },
    {
        "key": "core312",
        "label": "core tests (3.12)",
        "slug_variants": [
            ["core", "3-12"],
            ["core", "312"],
            ["py312"],
            ["3-12", "tests"],
        ],
        "fallback_patterns": [r"core\s*(tests?)?.*(3\.12|py\.?312)"],
    },
    {
        "key": "docker",
        "label": "docker smoke",
        "slug_variants": [["docker", "smoke"], ["smoke", "docker"]],
        "fallback_patterns": [r"docker.*smoke|smoke.*docker"],
    },
    {
        "key": "gate",
        "label": "gate",
        "slug_variants": [["gate"], ["aggregator", "gate"]],
        "fallback_patterns": [r"gate"],
    },
]


DOC_ONLY_JOB_KEYS: tuple[str, ...] = ("core311", "core312", "docker")


def _matches_slug(slug: str, variants: Sequence[Sequence[str]]) -> bool:
    return any(all(token in slug for token in option) for option in variants)


def _classify_job_key(name: str) -> str | None:
    slug = _slugify(name)
    for rule in REQUIRED_JOB_RULES:
        if _matches_slug(slug, rule["slug_variants"]):
            return rule["key"]
    return None


def _derive_required_groups_from_runs(
    runs: Sequence[Mapping[str, object]],
) -> List[RequiredJobGroup]:
    job_names: list[tuple[str, str]] = []
    for run in runs:
        if not isinstance(run, Mapping):
            continue
        jobs = run.get("jobs")
        if not isinstance(jobs, Sequence):
            continue
        for job in jobs:
            if not isinstance(job, Mapping):
                continue
            name_value = job.get("name")
            if not isinstance(name_value, str):
                continue
            name = name_value.strip()
            if not name:
                continue
            job_names.append((name, _slugify(name)))

    groups: List[RequiredJobGroup] = []
    used: set[str] = set()
    for rule in REQUIRED_JOB_RULES:
        matches: List[str] = []
        for original, slug in job_names:
            if _matches_slug(slug, rule["slug_variants"]):
                lowered = original.casefold()
                if lowered in used:
                    continue
                used.add(lowered)
                matches.append(original)
        if matches:
            patterns = [rf"^{re.escape(match)}$" for match in matches]
            groups.append({"label": matches[0], "patterns": patterns})
        else:
            groups.append(
                {
                    "label": rule["label"],
                    "patterns": list(rule["fallback_patterns"]),
                }
            )
    return groups


def _collect_category_states(
    runs: Sequence[Mapping[str, object]],
) -> dict[str, tuple[str, str | None]]:
    states: dict[str, tuple[str, str | None]] = {}
    for run in runs:
        if not isinstance(run, Mapping) or not run.get("present"):
            continue
        display = str(
            run.get("displayName") or run.get("display_name") or run.get("key") or "workflow"
        )
        jobs = run.get("jobs")
        if not isinstance(jobs, Sequence):
            continue
        for job in jobs:
            if not isinstance(job, Mapping):
                continue
            name_value = job.get("name")
            if not isinstance(name_value, str):
                continue
            name = name_value.strip()
            if not name:
                continue
            key = _classify_job_key(name)
            if not key:
                continue
            state_value = job.get("conclusion") or job.get("status")
            state_str = str(state_value) if state_value is not None else None
            label = f"{display} / {name}" if display else name
            existing = states.get(key)
            if existing is None or _priority(state_str) < _priority(existing[1]):
                states[key] = (label, state_str)
    return states


def _is_docs_only_fast_pass(
    category_states: Mapping[str, tuple[str, str | None]],
) -> bool:
    seen_skipped = False
    for key in DOC_ONLY_JOB_KEYS:
        record = category_states.get(key)
        if record is None:
            return False
        state = record[1] or ""
        normalized = state.lower()
        if normalized != "skipped":
            return False
        seen_skipped = True
    return seen_skipped


def _load_required_groups(
    env_value: str | None, runs: Sequence[Mapping[str, object]]
) -> List[RequiredJobGroup]:
    if not env_value:
        derived = _derive_required_groups_from_runs(runs)
        if derived:
            return derived
        return _copy_required_groups(DEFAULT_REQUIRED_JOB_GROUPS)
    try:
        parsed = json.loads(env_value)
    except json.JSONDecodeError:
        derived = _derive_required_groups_from_runs(runs)
        if derived:
            return derived
        return _copy_required_groups(DEFAULT_REQUIRED_JOB_GROUPS)
    if not isinstance(parsed, list):
        derived = _derive_required_groups_from_runs(runs)
        if derived:
            return derived
        return _copy_required_groups(DEFAULT_REQUIRED_JOB_GROUPS)
    result: List[RequiredJobGroup] = []
    for item in parsed:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or item.get("name") or "").strip()
        patterns = item.get("patterns")
        if not label or not isinstance(patterns, Sequence) or isinstance(patterns, (str, bytes)):
            continue
        cleaned: List[str] = [p for p in patterns if isinstance(p, str) and p]
        if not cleaned:
            continue
        result.append({"label": label, "patterns": cleaned})
    if result:
        return result
    derived = _derive_required_groups_from_runs(runs)
    if derived:
        return derived
    return _copy_required_groups(DEFAULT_REQUIRED_JOB_GROUPS)


def _load_required_contexts(
    config_path: str | os.PathLike[str] | None = None,
) -> List[str]:
    candidate = Path(config_path or os.getenv("REQUIRED_CONTEXTS_FILE") or REQUIRED_CONTEXTS_PATH)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

    if isinstance(payload, Mapping):
        contexts_value = payload.get("required_contexts") or payload.get("contexts")
    else:
        contexts_value = payload

    contexts: List[str] = []
    if isinstance(contexts_value, Iterable) and not isinstance(contexts_value, (str, bytes)):
        for item in contexts_value:
            if isinstance(item, str):
                value = item.strip()
                if value:
                    contexts.append(value)
    return contexts


def _dedupe_runs(runs: Sequence[Mapping[str, object]]) -> List[Mapping[str, object]]:
    deduped: List[Mapping[str, object]] = []
    index_by_key: dict[str, int] = {}

    for run in runs:
        if not isinstance(run, Mapping):
            continue

        key_value = run.get("key")
        key_str: str | None
        if isinstance(key_value, str):
            key_str = key_value.strip() or None
        elif key_value is None:
            key_str = None
        else:
            key_str = str(key_value)

        if not key_str:
            deduped.append(run)
            continue

        existing_index = index_by_key.get(key_str)
        if existing_index is None:
            index_by_key[key_str] = len(deduped)
            deduped.append(run)
            continue

        existing = deduped[existing_index]
        existing_present = bool(existing.get("present"))
        candidate_present = bool(run.get("present"))

        if candidate_present and not existing_present:
            deduped[existing_index] = run
            continue

        if candidate_present == existing_present:
            existing_state_value = existing.get("conclusion") or existing.get("status")
            candidate_state_value = run.get("conclusion") or run.get("status")

            existing_state = str(existing_state_value) if existing_state_value is not None else None
            candidate_state = (
                str(candidate_state_value) if candidate_state_value is not None else None
            )

            if (candidate_state and not existing_state) or (
                _priority(candidate_state) < _priority(existing_state)
            ):
                deduped[existing_index] = run

    return deduped


def _build_job_rows(runs: Sequence[Mapping[str, object]]) -> List[JobRecord]:
    rows: List[JobRecord] = []
    for run in runs:
        if not isinstance(run, Mapping):
            continue
        present = bool(run.get("present"))
        if not present:
            continue
        display = str(
            run.get("displayName") or run.get("display_name") or run.get("key") or "workflow"
        )
        jobs = run.get("jobs")
        if not isinstance(jobs, Sequence):
            continue
        for job in jobs:
            if not isinstance(job, Mapping):
                continue
            name = str(job.get("name") or "").strip()
            if not name:
                continue
            state = job.get("conclusion") or job.get("status")
            state_str = str(state) if state is not None else None
            highlight = bool(
                state_str
                and state_str.lower() in {"failure", "cancelled", "timed_out", "action_required"}
            )
            label = f"{display} / {name}"
            if highlight:
                label = f"**{label}**"
            rows.append(
                JobRecord(
                    name=label,
                    state=state_str,
                    url=str(job.get("html_url")) if job.get("html_url") else None,
                    highlight=highlight,
                )
            )
    rows.sort(key=lambda record: (_priority(record.state), record.name))
    return rows


def _format_jobs_table(rows: Sequence[JobRecord]) -> List[str]:
    header = [
        "| Workflow / Job | Result | Logs |",
        "|----------------|--------|------|",
    ]
    if not rows:
        return header + ["| _(no jobs reported)_ | ⏳ pending | — |"]
    body = []
    for record in rows:
        state_display = _display_state(record.state)
        link = f"[logs]({record.url})" if record.url else "—"
        body.append(f"| {record.name} | {_badge(record.state)} {state_display} | {link} |")
    return header + body


def _format_percent(value: Any) -> str | None:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return None


def _format_delta_pp(value: Any, *, signed: bool = True) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not signed:
        return f"{abs(number):.2f} pp"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f} pp"


def _collect_required_segments(
    runs: Sequence[Mapping[str, object]],
    groups: Sequence[RequiredJobGroup],
) -> List[str]:
    import re

    segments: List[str] = []
    job_sources: List[Mapping[str, object]] = []
    for run in runs:
        if not isinstance(run, Mapping) or not run.get("present"):
            continue
        jobs = run.get("jobs")
        if isinstance(jobs, Sequence):
            job_sources.append(run)

    for group in groups:
        label = group.get("label", "").strip()
        patterns = group.get("patterns", [])
        if not label or not isinstance(patterns, Sequence):
            continue

        regexes = []
        for pattern in patterns:
            if not isinstance(pattern, str):
                continue
            try:
                regexes.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                continue
        if not regexes:
            continue

        matched_states: List[str | None] = []
        matched_names: List[str] = []
        for run in job_sources:
            jobs = run.get("jobs")
            if not isinstance(jobs, Sequence):
                continue
            for job in jobs:
                if not isinstance(job, Mapping):
                    continue
                name = str(job.get("name") or "")
                if not name:
                    continue
                if any(regex.search(name) for regex in regexes):
                    matched_names.append(name)
                    state_value = job.get("conclusion") or job.get("status")
                    matched_states.append(str(state_value) if state_value is not None else None)

        if matched_states:
            state = _combine_states(matched_states)
        else:
            state = None
        canonical_name: str | None = None
        if matched_names:
            seen: set[str] = set()
            for candidate in matched_names:
                lowered = candidate.casefold()
                if lowered in seen:
                    continue
                seen.add(lowered)
                canonical_name = candidate
                break
        display_label = canonical_name or label or "Job group"
        segments.append(f"{display_label}: {_badge(state)} {_display_state(state)}")

    return segments


def _format_latest_runs(runs: Sequence[Mapping[str, object]]) -> str:
    parts: List[str] = []
    for run in runs:
        if not isinstance(run, Mapping):
            continue
        display = (
            str(
                run.get("displayName") or run.get("display_name") or run.get("key") or "workflow"
            ).strip()
            or "workflow"
        )

        state = run.get("conclusion") or run.get("status")
        state_str = str(state) if state is not None else None
        badge = _badge(state_str)
        state_display = _display_state(state_str)

        if not run.get("present"):
            parts.append(f"{badge} {state_display} — {display}")
            continue

        run_id = run.get("id")
        attempt = run.get("run_attempt")
        attempt_suffix = f" (attempt {attempt})" if isinstance(attempt, int) and attempt > 1 else ""
        label = f"{display} (#{run_id}{attempt_suffix})" if run_id else display
        url = run.get("html_url")
        if url:
            label = f"[{label}]({url})"

        parts.append(f"{badge} {state_display} — {label}")
    return " · ".join(parts)


def _format_coverage_lines(stats: Mapping[str, object] | None) -> List[str]:
    if not isinstance(stats, Mapping):
        return []

    lines: List[str] = []
    avg_latest = _format_percent(stats.get("avg_latest"))
    avg_delta = _format_delta_pp(stats.get("avg_delta"))
    avg_parts = [part for part in (avg_latest, f"Δ {avg_delta}" if avg_delta else None) if part]
    if avg_parts:
        lines.append(f"- Coverage (jobs): {' | '.join(avg_parts)}")

    worst_latest = _format_percent(stats.get("worst_latest"))
    worst_delta = _format_delta_pp(stats.get("worst_delta"))
    worst_parts = [
        part for part in (worst_latest, f"Δ {worst_delta}" if worst_delta else None) if part
    ]
    if worst_parts:
        lines.append(f"- Coverage (worst job): {' | '.join(worst_parts)}")

    history_len = stats.get("history_len")
    if isinstance(history_len, int):
        lines.append(f"- Coverage history entries: {history_len}")
    return lines


def _format_coverage_delta_lines(
    delta: Mapping[str, object] | None,
) -> List[str]:
    if not isinstance(delta, Mapping):
        return []

    head_value = _format_percent(delta.get("current"))
    baseline_value = _format_percent(delta.get("baseline"))
    delta_value = _format_delta_pp(delta.get("delta"))
    drop_value = _format_delta_pp(delta.get("drop"), signed=False)
    threshold_value = _format_delta_pp(delta.get("threshold"), signed=False)

    parts: List[str] = []
    if head_value:
        parts.append(f"head {head_value}")
    if baseline_value:
        parts.append(f"base {baseline_value}")
    elif str(delta.get("status")) == "no-baseline":
        parts.append("base — (no baseline)")
    if delta_value:
        parts.append(f"Δ {delta_value}")
    if drop_value:
        parts.append(f"drop {drop_value}")
    if threshold_value:
        parts.append(f"threshold {threshold_value}")

    status = str(delta.get("status") or "").strip()
    if status:
        parts.append(f"status {status}")

    return [f"- Coverage delta: {' | '.join(parts)}"] if parts else []


def build_summary_comment(
    *,
    runs: Sequence[Mapping[str, object]],
    head_sha: str | None,
    coverage_stats: Mapping[str, object] | None,
    coverage_section: str | None,
    coverage_delta: Mapping[str, object] | None,
    required_groups_env: str | None,
) -> str:
    deduped_runs = _dedupe_runs(runs)
    category_states = _collect_category_states(deduped_runs)
    docs_only_fast_pass = _is_docs_only_fast_pass(category_states)
    rows = _build_job_rows(deduped_runs)
    job_table_lines = _format_jobs_table(rows)
    groups = _load_required_groups(required_groups_env, deduped_runs)
    required_segments = _collect_required_segments(deduped_runs, groups)
    contexts = _load_required_contexts(None)
    latest_runs_line = _format_latest_runs(deduped_runs)
    coverage_lines = _format_coverage_lines(coverage_stats)
    coverage_delta_lines = _format_coverage_delta_lines(coverage_delta)
    coverage_table = ""
    if isinstance(coverage_stats, Mapping):
        table_value = coverage_stats.get("coverage_table_markdown")
        if isinstance(table_value, str):
            coverage_table = table_value.strip()

    coverage_block: List[str] = []
    coverage_section_clean = (coverage_section or "").strip()
    if coverage_lines or coverage_delta_lines:
        coverage_block.append("### Coverage Overview")
    if coverage_delta_lines:
        coverage_block.append("\n".join(coverage_delta_lines))
    if coverage_lines:
        coverage_block.append("\n".join(coverage_lines))
    if coverage_table:
        if not coverage_block:
            coverage_block.append("### Coverage Overview")
        coverage_block.append(coverage_table)
    if coverage_section_clean:
        if not coverage_block:
            coverage_block.append("### Coverage Overview")
        coverage_block.append(coverage_section_clean)
    if docs_only_fast_pass:
        note = "Docs-only fast-pass: coverage artifacts were not refreshed for this run."
        if coverage_block:
            coverage_block.append(note)
        else:
            coverage_block.extend(["### Coverage Overview", note])

    body_parts: MutableSequence[str] = ["## Automated Status Summary"]
    if head_sha:
        body_parts.append(f"**Head SHA:** {head_sha}")
    if latest_runs_line:
        body_parts.append(f"**Latest Runs:** {latest_runs_line}")
    if contexts:
        body_parts.append(f"**Required contexts:** {', '.join(contexts)}")
    if required_segments:
        body_parts.append(f"**Required:** {', '.join(required_segments)}")
    body_parts.append("")
    body_parts.extend(job_table_lines)
    body_parts.append("")
    if docs_only_fast_pass:
        body_parts.append("Docs-only change detected; heavy checks skipped.")
        body_parts.append("")
    body_parts.extend(part for part in coverage_block if part)
    if coverage_block:
        body_parts.append("")
    body_parts.append("_Updated automatically; will refresh on subsequent CI/Docker completions._")

    return "\n".join(part for part in body_parts if part is not None)


def _load_json_from_env(value: str | None) -> Mapping[str, object] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, Mapping) else None


def main() -> None:
    runs_value = os.environ.get("RUNS_JSON", "[]")
    try:
        runs = json.loads(runs_value)
    except json.JSONDecodeError:
        runs = []
    if not isinstance(runs, list):
        runs = []

    head_sha = os.environ.get("HEAD_SHA") or None
    coverage_stats = _load_json_from_env(os.environ.get("COVERAGE_STATS"))
    coverage_section = os.environ.get("COVERAGE_SECTION")
    coverage_delta = _load_json_from_env(os.environ.get("COVERAGE_DELTA"))
    required_groups_env = os.environ.get("REQUIRED_JOB_GROUPS_JSON")

    body = build_summary_comment(
        runs=runs,
        head_sha=head_sha,
        coverage_stats=coverage_stats,
        coverage_section=coverage_section,
        coverage_delta=coverage_delta,
        required_groups_env=required_groups_env,
    )

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        handle_path = Path(output_path)
        with handle_path.open("a", encoding="utf-8") as handle:
            handle.write(f"body<<EOF\n{body}\nEOF\n")
    else:
        print(body)


if __name__ == "__main__":
    main()
