#!/usr/bin/env python3
"""Aggregate agent metrics NDJSON into a markdown summary."""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

_DEFAULT_METRICS_DIR = "agent-metrics"
_DEFAULT_OUTPUT = "agent-metrics-summary.md"
_DEFAULT_JSON_OUTPUT = "agent-metrics-summary.json"
_DEFAULT_DOWNLOAD_MANIFEST_PATH = "artifacts/metric-artifact-download-manifest.json"
_DEFAULT_UNSUPPORTED_VERIFIER_MODELS = {"gpt-5.2-codex"}
_DEFAULT_VERIFIER_MODEL_METADATA_REQUIRED_AFTER = ""
_EXACT_ARTIFACT_FAMILIES = {
    "keepalive-metrics",
    "agents-autofix-metrics",
    "agents-verifier-metrics",
    "agents-verifier-disposition-metrics",
    "codex-cli-freshness",
}
_PREFIXED_ARTIFACT_FAMILIES = (
    "autopilot-metrics-",
    "issue-optimizer-metrics-",
    "issue-intake-format-metrics-",
    "codex-cli-freshness-",
    "verifier-terminal-disposition-",
    "review-thread-terminal-disposition-",
)
_PATTERNED_ARTIFACT_FAMILIES = (
    (
        "bot-comment-auth-coverage-wrapper",
        re.compile(r"^bot-comment-auth-coverage-wrapper(?:-[A-Za-z0-9][A-Za-z0-9._-]*)?$"),
    ),
    (
        "bot-comment-auth-coverage-reusable",
        re.compile(r"^bot-comment-auth-coverage-reusable(?:-[A-Za-z0-9][A-Za-z0-9._-]*)?$"),
    ),
)
_MAX_PARSE_ERROR_ROWS = 25
_MAX_STORED_PARSE_ERROR_DETAILS = 250
_MAX_LEGACY_JSON_FALLBACK_LINES = 5000
_MAX_LEGACY_JSON_FALLBACK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ParseErrorDetail:
    path: str
    artifact: str
    artifact_family: str
    line: int | None
    reason: str
    count: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "artifact": self.artifact,
            "artifact_family": self.artifact_family,
            "line": self.line,
            "reason": self.reason,
            "count": self.count,
        }


@dataclass(frozen=True)
class MetricSource:
    path: str
    artifact: str
    artifact_family: str


def _parse_timestamp(value: Any) -> _dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return _dt.datetime.fromtimestamp(float(value), tz=_dt.UTC)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = _dt.datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_dt.UTC)
        return parsed
    return None


def _normalize_version_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    match = re.search(r"(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?)", text)
    return match.group(1) if match else text


def _normalize_cli_version(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        return ""
    version = _normalize_version_text(text)
    lower = text.lower().replace("_", "-")
    if version and re.search(r"\bcodex(?:-|\s+)cli\b|\bopenai/codex\b|\bcodex\b", lower):
        return f"codex-cli {version}".lower()
    return lower


def _normalize_counter_token(value: Any, fallback: str = "unknown") -> str:
    text = str(value).strip().lower().replace("_", "-") if value is not None else ""
    return text or fallback


def _gather_metrics_files(metrics_paths: list[str], metrics_dir: str) -> list[Path]:
    if metrics_paths:
        return [Path(path) for path in metrics_paths if path]

    root = Path(metrics_dir)
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.ndjson") if path.is_file())


def _artifact_family(artifact: str) -> str:
    if artifact in _EXACT_ARTIFACT_FAMILIES:
        return artifact
    for family, pattern in _PATTERNED_ARTIFACT_FAMILIES:
        if pattern.match(artifact):
            return family
    for prefix in _PREFIXED_ARTIFACT_FAMILIES:
        if artifact.startswith(prefix):
            return prefix.rstrip("-")
    return "unknown"


def _is_artifact_id_segment(value: str) -> bool:
    return bool(value) and value.isdigit()


def _infer_artifact_name(path: Path) -> str:
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "agent-metrics" and index > 0:
            candidate = parts[index - 1]
            if _is_artifact_id_segment(candidate) and index > 1:
                return parts[index - 2]
            return candidate
    parent = path.parent.name
    if _is_artifact_id_segment(parent) and path.parent.parent.name:
        return path.parent.parent.name
    if path.parent.name:
        return path.parent.name
    return "unknown"


def _metric_source(path: Path) -> MetricSource:
    artifact = _infer_artifact_name(path)
    return MetricSource(
        path=path.as_posix(),
        artifact=artifact,
        artifact_family=_artifact_family(artifact),
    )


def _attach_metric_source(entry: dict[str, Any], path: Path) -> dict[str, Any]:
    source = _metric_source(path)
    enriched = dict(entry)
    enriched.setdefault("artifact_name", source.artifact)
    enriched.setdefault("artifact_family", source.artifact_family)
    enriched.setdefault("metric_artifact", source.artifact)
    enriched.setdefault("metric_artifact_family", source.artifact_family)
    enriched.setdefault("metric_path", source.path)
    return enriched


def _parse_error_detail(path: Path, line: int | None, reason: str) -> ParseErrorDetail:
    source = _metric_source(path)
    return ParseErrorDetail(
        path=source.path,
        artifact=source.artifact,
        artifact_family=source.artifact_family,
        line=line,
        reason=reason,
    )


def _append_parse_error_detail(
    details: list[ParseErrorDetail],
    detail: ParseErrorDetail,
    *,
    detail_limit: int = _MAX_STORED_PARSE_ERROR_DETAILS,
) -> None:
    if detail_limit <= 0:
        return

    if len(details) < detail_limit:
        details.append(detail)
        return

    for index, existing in enumerate(details):
        if (
            existing.path == detail.path
            and existing.artifact == detail.artifact
            and existing.artifact_family == detail.artifact_family
            and existing.reason == detail.reason
        ):
            details[index] = replace(existing, line=None, count=existing.count + detail.count)
            return

    displaced = details[-1]
    for index, existing in enumerate(details[:-1]):
        if (
            existing.path == displaced.path
            and existing.artifact == displaced.artifact
            and existing.artifact_family == displaced.artifact_family
            and existing.reason == displaced.reason
        ):
            details[index] = replace(existing, line=None, count=existing.count + displaced.count)
            details[-1] = detail
            return

    overflow_reason = "additional-parse-errors-after-detail-limit"
    for index, existing in enumerate(details):
        if (
            existing.path == "__multiple__"
            and existing.artifact == "__multiple__"
            and existing.artifact_family == "__multiple__"
            and existing.reason == overflow_reason
            and existing.line is None
        ):
            details[index] = replace(existing, count=existing.count + detail.count)
            return

    details[-1] = ParseErrorDetail(
        path="__multiple__",
        artifact="__multiple__",
        artifact_family="__multiple__",
        line=None,
        reason=overflow_reason,
        count=displaced.count + detail.count,
    )


def _parse_error_count(parse_error_details: list[ParseErrorDetail]) -> int:
    return sum(detail.count for detail in parse_error_details)


def _parse_error_counter(parse_error_details: list[ParseErrorDetail], field: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for detail in parse_error_details:
        counts[str(getattr(detail, field))] += detail.count
    return counts


def _read_ndjson(files: Iterable[Path]) -> tuple[list[dict[str, Any]], list[ParseErrorDetail]]:
    entries: list[dict[str, Any]] = []
    errors: list[ParseErrorDetail] = []
    for path in files:
        try:
            handle = path.open("r", encoding="utf-8")
        except OSError:
            errors.append(_parse_error_detail(path, None, "unreadable-file"))
            continue
        file_entries: list[dict[str, Any]] = []
        file_errors: list[ParseErrorDetail] = []
        raw_lines_for_fallback: list[str] = []
        raw_fallback_bytes = 0
        raw_fallback_truncated = False
        with handle:
            for line_number, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                if not file_entries and not raw_fallback_truncated:
                    raw_bytes = len(raw.encode("utf-8")) + 1
                    fallback_within_limit = (
                        len(raw_lines_for_fallback) < _MAX_LEGACY_JSON_FALLBACK_LINES
                        and raw_fallback_bytes + raw_bytes <= _MAX_LEGACY_JSON_FALLBACK_BYTES
                    )
                    if fallback_within_limit:
                        raw_fallback_bytes += raw_bytes
                        raw_lines_for_fallback.append(raw)
                    else:
                        raw_fallback_truncated = True
                        raw_lines_for_fallback = []
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    _append_parse_error_detail(
                        file_errors,
                        _parse_error_detail(path, line_number, "invalid-json"),
                    )
                    continue
                if isinstance(parsed, dict):
                    file_entries.append(_attach_metric_source(parsed, path))
                    raw_lines_for_fallback = []
                else:
                    _append_parse_error_detail(
                        file_errors,
                        _parse_error_detail(path, line_number, "non-object-json"),
                    )
        if file_errors and not file_entries and raw_fallback_truncated:
            _append_parse_error_detail(
                file_errors,
                _parse_error_detail(path, None, "legacy-json-fallback-buffer-limit"),
            )
        if (
            file_errors
            and not file_entries
            and raw_lines_for_fallback
            and not raw_fallback_truncated
        ):
            try:
                parsed_file = json.loads("\n".join(raw_lines_for_fallback))
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed_file, dict):
                    file_entries.append(_attach_metric_source(parsed_file, path))
                    file_errors = []
                elif isinstance(parsed_file, list) and all(
                    isinstance(item, dict) for item in parsed_file
                ):
                    file_entries.extend(_attach_metric_source(item, path) for item in parsed_file)
                    file_errors = []
        entries.extend(file_entries)
        errors.extend(file_errors)
    return entries, errors


def _classify_entry(entry: dict[str, Any]) -> str:
    schema = entry.get("schema")
    if schema == "workflows-terminal-disposition/v1":
        return "terminal_disposition"
    if schema == "workflows-verifier-followup-ledger/v1":
        return "verifier_followup_ledger"
    if schema == "workflows-codex-cli-freshness/v1":
        return "codex_cli_freshness"
    explicit = entry.get("metric_type") or entry.get("type") or entry.get("workflow")
    if isinstance(explicit, str):
        lowered = explicit.lower()
        if "keepalive" in lowered:
            return "keepalive"
        if "autofix" in lowered:
            return "autofix"
        if "verifier" in lowered or "verify" in lowered:
            return "verifier"
        if lowered in ("step", "cycle", "escalation"):
            return "autopilot"
    if any(key in entry for key in ("iteration_count", "stop_reason", "tasks_total")):
        return "keepalive"
    if any(key in entry for key in ("attempt_number", "trigger_reason", "fix_applied")):
        return "autofix"
    if any(key in entry for key in ("verdict", "issues_created", "acceptance_criteria_count")):
        return "verifier"
    # Auto-pilot step/cycle records have step_name + duration_ms
    if "step_name" in entry and "duration_ms" in entry:
        return "autopilot"
    if "escalation_reason" in entry:
        return "autopilot"
    return "unknown"


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _unsupported_verifier_models() -> set[str]:
    raw = ""
    for env_name in (
        "UNSUPPORTED_VERIFIER_MODELS",
        "TERMINAL_DISPOSITION_UNSUPPORTED_CODEX_MODELS",
    ):
        candidate = os.environ.get(env_name, "")
        if candidate.strip():
            raw = candidate
            break
    if not raw:
        return set(_DEFAULT_UNSUPPORTED_VERIFIER_MODELS)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _verifier_model_metadata_required_after() -> _dt.datetime | None:
    raw = (
        os.environ.get("TERMINAL_DISPOSITION_VERIFIER_MODEL_METADATA_REQUIRED_AFTER")
        or os.environ.get("VERIFIER_MODEL_METADATA_REQUIRED_AFTER")
        or _DEFAULT_VERIFIER_MODEL_METADATA_REQUIRED_AFTER
    ).strip()
    if raw.lower() in {"", "0", "false", "none", "off", "disabled"}:
        return None
    return _parse_timestamp(raw)


def _verifier_model_metadata_required() -> bool:
    raw = (
        os.environ.get("TERMINAL_DISPOSITION_VERIFIER_MODEL_METADATA_REQUIRED_AFTER")
        or os.environ.get("VERIFIER_MODEL_METADATA_REQUIRED_AFTER")
        or _DEFAULT_VERIFIER_MODEL_METADATA_REQUIRED_AFTER
    ).strip()
    return raw.lower() not in {"", "0", "false", "none", "off", "disabled"}


def _is_pre_contract_verifier_model_record(
    entry: dict[str, Any], required_after: _dt.datetime | None
) -> bool:
    if required_after is None:
        return False
    for key in ("created_at", "timestamp", "run_started_at", "time"):
        timestamp = _parse_timestamp(entry.get(key))
        if timestamp is not None:
            return timestamp < required_after
    return False


def _is_verifier_terminal_entry(entry: dict[str, Any]) -> bool:
    if entry.get("schema") != "workflows-terminal-disposition/v1":
        return False
    artifact_family = str(entry.get("artifact_family") or "").strip().lower()
    workflow = str(entry.get("workflow") or "").strip().lower()
    verifier_mode = str(entry.get("verifier_mode") or "").strip().lower()
    return (
        artifact_family == "verifier-terminal-disposition"
        or bool(verifier_mode)
        or "verifier" in workflow
    )


def _summarise_keepalive(entries: list[dict[str, Any]]) -> dict[str, Any]:
    stop_reasons = Counter()
    actions = Counter()
    gate_results = Counter()
    iterations: list[int] = []
    prs: set[int] = set()
    tasks_complete = 0
    for entry in entries:
        stop_reason = entry.get("stop_reason")
        if stop_reason:
            stop_reasons[str(stop_reason)] += 1
        action = entry.get("action")
        if action:
            actions[str(action)] += 1
        gate = entry.get("gate_conclusion") or entry.get("gate_result")
        if gate:
            gate_results[str(gate)] += 1
        iteration = _safe_int(entry.get("iteration_count") or entry.get("iteration"))
        if iteration is not None:
            iterations.append(iteration)
        pr_number = _safe_int(entry.get("pr_number") or entry.get("pr"))
        if pr_number is not None:
            prs.add(pr_number)
        tasks_total = _safe_int(entry.get("tasks_total"))
        entry_tasks_complete = _safe_int(entry.get("tasks_complete"))
        derived_complete = (
            tasks_total is not None
            and tasks_total > 0
            and entry_tasks_complete is not None
            and entry_tasks_complete >= tasks_total
        )
        if stop_reason == "tasks-complete" or derived_complete:
            tasks_complete += 1
    avg_iterations = sum(iterations) / len(iterations) if iterations else 0.0
    return {
        "runs": len(entries),
        "prs": len(prs),
        "avg_iterations": avg_iterations,
        "stop_reasons": stop_reasons,
        "actions": actions,
        "gate_results": gate_results,
        "tasks_complete": tasks_complete,
    }


def _summarise_autofix(entries: list[dict[str, Any]]) -> dict[str, Any]:
    triggers = Counter()
    gate_results = Counter()
    prs: set[int] = set()
    fixes_applied = 0
    for entry in entries:
        trigger = entry.get("trigger_reason")
        if trigger:
            triggers[str(trigger)] += 1
        gate = entry.get("gate_result_after") or entry.get("gate_result")
        if gate:
            gate_results[str(gate)] += 1
        pr_number = _safe_int(entry.get("pr_number") or entry.get("pr"))
        if pr_number is not None:
            prs.add(pr_number)
        if entry.get("fix_applied") in (True, "true", "True", "1", 1):
            fixes_applied += 1
    return {
        "attempts": len(entries),
        "prs": len(prs),
        "fixes_applied": fixes_applied,
        "triggers": triggers,
        "gate_results": gate_results,
    }


def _summarise_verifier(
    entries: list[dict[str, Any]],
    ledger_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    verdicts = Counter()
    terminal_dispositions = Counter()
    terminal_sources = Counter()
    verifier_models = Counter()
    model_selection_reasons = Counter()
    verifier_cli_versions = Counter()
    unsupported_verifier_models = Counter()
    unsupported_model_dispositions = Counter()
    missing_verifier_model_metadata = Counter()
    unsupported_models = _unsupported_verifier_models()
    model_metadata_required = _verifier_model_metadata_required()
    model_metadata_required_after = _verifier_model_metadata_required_after()
    legacy_missing_verifier_model_metadata = Counter()
    verifier_modes = Counter()
    ledger_dispositions = Counter()
    ledger_followup_issues: set[int] = set()
    ledger_prs: set[int] = set()
    ledger_needs_human = 0
    ledger_chain_depths: list[int] = []
    ledger_policy_records = 0
    ledger_policy_actions = Counter()
    ledger_policy_triggers = Counter()
    ledger_policy_depth_limit_exceeded = 0
    verifier_run_keys: set[str] = set()
    prs: set[int] = set()
    issues_created = 0
    acceptance_counts: list[int] = []
    terminal_records = 0
    for index, entry in enumerate(entries):
        is_terminal_disposition = entry.get("schema") == "workflows-terminal-disposition/v1"
        is_verifier_terminal = _is_verifier_terminal_entry(entry)
        if not is_terminal_disposition:
            run_id = entry.get("run_id") or entry.get("workflow_run_id")
            run_attempt = entry.get("run_attempt")
            pr_number_for_key = _safe_int(entry.get("pr_number") or entry.get("pr"))
            if run_id:
                verifier_run_keys.add(f"run:{run_id}:attempt:{run_attempt or ''}")
            elif pr_number_for_key is not None:
                verifier_run_keys.add(f"pr:{pr_number_for_key}")
            else:
                verifier_run_keys.add(f"entry:{index}")

        verdict = entry.get("verdict")
        if verdict:
            verdicts[str(verdict)] += 1
        if is_terminal_disposition:
            terminal_records += 1
            disposition = entry.get("disposition") or entry.get("terminal_state") or "unknown"
            terminal_dispositions[str(disposition)] += 1
            source_type = entry.get("source_type") or "unknown"
            source_id = entry.get("source_id") or "unknown"
            terminal_sources[f"{source_type}:{source_id}"] += 1
        model = entry.get("codex_model") or entry.get("llm_model") or entry.get("model")
        model_text = str(model).strip() if model is not None else ""
        if model_text:
            normalized_model_text = model_text.lower()
            verifier_models[normalized_model_text] += 1
            if normalized_model_text in unsupported_models:
                unsupported_verifier_models[normalized_model_text] += 1
                disposition = entry.get("disposition") or entry.get("terminal_state") or "unknown"
                unsupported_model_dispositions[str(disposition)] += 1
        elif is_verifier_terminal and model_metadata_required:
            verifier_mode = str(entry.get("verifier_mode") or "").strip().lower()
            if verifier_mode != "evaluate":
                disposition = entry.get("disposition") or entry.get("terminal_state") or "unknown"
                if _is_pre_contract_verifier_model_record(entry, model_metadata_required_after):
                    legacy_missing_verifier_model_metadata[str(disposition)] += 1
                else:
                    missing_verifier_model_metadata[str(disposition)] += 1
        model_selection_reason = entry.get("codex_model_selection_reason") or entry.get(
            "model_selection_reason"
        )
        if model_selection_reason:
            model_selection_reasons[str(model_selection_reason)] += 1
        cli_version = (
            entry.get("codex_cli_version")
            or entry.get("llm_cli_version")
            or entry.get("cli_version")
        )
        cli_version_text = str(cli_version).strip() if cli_version is not None else ""
        if cli_version_text:
            verifier_cli_versions[_normalize_cli_version(cli_version_text)] += 1
        verifier_mode = str(entry.get("verifier_mode") or "").strip().lower()
        if verifier_mode:
            verifier_modes[verifier_mode] += 1
        pr_number = _safe_int(entry.get("pr_number") or entry.get("pr"))
        if pr_number is not None:
            prs.add(pr_number)
        created = _safe_int(entry.get("issues_created"))
        if created is not None:
            issues_created += created
        acceptance = _safe_int(entry.get("acceptance_criteria_count"))
        if acceptance is not None:
            acceptance_counts.append(acceptance)
    for entry in ledger_entries or []:
        disposition = str(entry.get("disposition") or "unknown")
        ledger_dispositions[disposition] += 1
        pr_number = _safe_int(entry.get("pr_number") or entry.get("pr"))
        if pr_number is not None:
            ledger_prs.add(pr_number)
        followup_issue = _safe_int(entry.get("followup_issue_number"))
        if followup_issue is not None:
            ledger_followup_issues.add(followup_issue)
        if bool(entry.get("needs_human")) or disposition == "needs-human":
            ledger_needs_human += 1
        chain_depth = _safe_int(entry.get("chain_depth"))
        if chain_depth is not None:
            ledger_chain_depths.append(chain_depth)
        policy = entry.get("followup_policy")
        if isinstance(policy, dict):
            ledger_policy_records += 1
            action = str(policy.get("action") or "unknown")
            trigger = str(policy.get("trigger") or "unknown")
            ledger_policy_actions[action] += 1
            ledger_policy_triggers[trigger] += 1
            if policy.get("depth_limit_exceeded") in (True, "true", "True", "1", 1):
                ledger_policy_depth_limit_exceeded += 1
    avg_acceptance = sum(acceptance_counts) / len(acceptance_counts) if acceptance_counts else 0.0
    avg_ledger_chain_depth = (
        sum(ledger_chain_depths) / len(ledger_chain_depths) if ledger_chain_depths else 0.0
    )
    return {
        "runs": len(verifier_run_keys),
        "prs": len(prs),
        "verdicts": verdicts,
        "issues_created": issues_created,
        "avg_acceptance": avg_acceptance,
        "terminal_records": terminal_records,
        "terminal_dispositions": terminal_dispositions,
        "terminal_sources": terminal_sources,
        "verifier_models": verifier_models,
        "verifier_cli_versions": verifier_cli_versions,
        "unsupported_verifier_models": unsupported_verifier_models,
        "unsupported_model_dispositions": unsupported_model_dispositions,
        "missing_verifier_model_metadata": missing_verifier_model_metadata,
        "legacy_missing_verifier_model_metadata": legacy_missing_verifier_model_metadata,
        "model_selection_reasons": model_selection_reasons,
        "verifier_modes": verifier_modes,
        "ledger_records": len(ledger_entries or []),
        "ledger_dispositions": ledger_dispositions,
        "ledger_prs": len(ledger_prs),
        "ledger_followup_issues": len(ledger_followup_issues),
        "ledger_needs_human": ledger_needs_human,
        "ledger_avg_chain_depth": avg_ledger_chain_depth,
        "ledger_max_chain_depth": max(ledger_chain_depths) if ledger_chain_depths else 0,
        "ledger_policy_records": ledger_policy_records,
        "ledger_policy_actions": ledger_policy_actions,
        "ledger_policy_triggers": ledger_policy_triggers,
        "ledger_policy_depth_limit_exceeded": ledger_policy_depth_limit_exceeded,
    }


def _summarise_autopilot(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise auto-pilot step/cycle/escalation records."""
    issues: set[int] = set()
    step_durations: dict[str, list[float]] = {}
    step_successes: dict[str, int] = {}
    step_failures: dict[str, int] = {}
    cycle_counts = Counter()
    failure_reasons = Counter()
    escalation_reasons = Counter()
    cycle_records = 0
    cycle_steps_attempted = 0
    cycle_steps_completed = 0
    escalation_count = 0
    needs_human_count = 0

    for entry in entries:
        issue_num = _safe_int(entry.get("issue_number") or entry.get("issue"))
        if issue_num is not None:
            issues.add(issue_num)

        metric_type = str(entry.get("metric_type", "")).lower()

        if metric_type == "escalation":
            escalation_count += 1
            reason = entry.get("escalation_reason", "unknown")
            escalation_reasons[str(reason)] += 1
            if "needs-human" in str(reason).lower() or "needs_human" in str(reason).lower():
                needs_human_count += 1
            continue

        if metric_type == "cycle":
            cycle_records += 1
            cycle_count = _safe_int(entry.get("cycle_count"))
            if cycle_count is not None:
                cycle_counts[str(cycle_count)] += 1
            steps_attempted = _safe_int(entry.get("steps_attempted"))
            if steps_attempted is not None:
                cycle_steps_attempted += steps_attempted
            steps_completed = _safe_int(entry.get("steps_completed"))
            if steps_completed is not None:
                cycle_steps_completed += steps_completed
            continue

        step_name = entry.get("step_name")
        if not step_name:
            continue

        duration = _safe_float(entry.get("duration_ms"))
        if duration is not None:
            step_durations.setdefault(step_name, []).append(duration)

        success = entry.get("success")
        if success in (True, "true", "True", "1", 1):
            step_successes[step_name] = step_successes.get(step_name, 0) + 1
        elif success in (False, "false", "False", "0", 0):
            step_failures[step_name] = step_failures.get(step_name, 0) + 1
            reason = entry.get("failure_reason", "unknown")
            if reason and reason != "none":
                failure_reasons[str(reason)] += 1

    # Compute per-step averages
    step_avg_duration: dict[str, float] = {}
    for step, durations in step_durations.items():
        step_avg_duration[step] = sum(durations) / len(durations) if durations else 0.0

    total_steps = sum(step_successes.values()) + sum(step_failures.values())

    return {
        "records": len(entries),
        "issues": len(issues),
        "total_steps": total_steps,
        "step_avg_duration_ms": step_avg_duration,
        "step_successes": step_successes,
        "step_failures": step_failures,
        "cycle_records": cycle_records,
        "cycle_counts": cycle_counts,
        "cycle_steps_attempted": cycle_steps_attempted,
        "cycle_steps_completed": cycle_steps_completed,
        "failure_reasons": failure_reasons,
        "escalation_count": escalation_count,
        "escalation_reasons": escalation_reasons,
        "needs_human_count": needs_human_count,
    }


def _summarise_codex_cli_freshness(entries: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter()
    packages = Counter()
    pinned_versions = Counter()
    latest_versions = Counter()
    max_major_delta = 0
    max_minor_delta = 0
    max_patch_delta = 0
    update_targets = Counter()
    for entry in entries:
        status = _normalize_counter_token(entry.get("status"))
        statuses[status] += 1
        package = str(entry.get("package") or "unknown").strip() or "unknown"
        packages[package] += 1
        pinned = _normalize_version_text(entry.get("pinned_version")) or "unknown"
        latest = _normalize_version_text(entry.get("latest_version")) or "unknown"
        pinned_versions[pinned] += 1
        latest_versions[latest] += 1
        delta = entry.get("version_delta")
        if isinstance(delta, dict):
            max_major_delta = max(max_major_delta, _safe_int(delta.get("major")) or 0)
            max_minor_delta = max(max_minor_delta, _safe_int(delta.get("minor")) or 0)
            max_patch_delta = max(max_patch_delta, _safe_int(delta.get("patch")) or 0)
        targets = entry.get("update_targets")
        if isinstance(targets, list):
            for target in targets:
                if not isinstance(target, dict):
                    continue
                path = str(target.get("path") or "").strip()
                if path:
                    update_targets[path] += 1
    return {
        "records": len(entries),
        "statuses": statuses,
        "packages": packages,
        "pinned_versions": pinned_versions,
        "latest_versions": latest_versions,
        "outdated_records": statuses.get("outdated", 0),
        "latest_unavailable_records": statuses.get("latest-unavailable", 0),
        "max_version_delta": {
            "major": max_major_delta,
            "minor": max_minor_delta,
            "patch": max_patch_delta,
        },
        "update_targets": update_targets,
    }


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "n/a"
    parts = [f"{key} ({count})" for key, count in counter.most_common()]
    return ", ".join(parts)


def _markdown_table_cell(value: Any) -> str:
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(part.strip() for part in text.split("\n"))
    return text.replace("|", "\\|")


def _format_rate(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "n/a"
    rate = (numerator / denominator) * 100
    return f"{rate:.1f}% ({numerator}/{denominator})"


def _json_contract_value(value: Any) -> Any:
    if isinstance(value, Counter):
        return dict(sorted(value.items()))
    if isinstance(value, dict):
        return {str(key): _json_contract_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_json_contract_value(item) for item in value]
    return value


def _bucket_entries(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "keepalive": [],
        "autofix": [],
        "verifier": [],
        "terminal_disposition": [],
        "verifier_followup_ledger": [],
        "codex_cli_freshness": [],
        "autopilot": [],
        "unknown": [],
    }
    for entry in entries:
        bucket = _classify_entry(entry)
        buckets.setdefault(bucket, []).append(entry)
    return buckets


def _summary_metrics_contract(buckets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return _json_contract_value(
        {
            "keepalive": _summarise_keepalive(buckets["keepalive"]),
            "autofix": _summarise_autofix(buckets["autofix"]),
            "verifier": _summarise_verifier(
                buckets["verifier"] + buckets["terminal_disposition"],
                buckets["verifier_followup_ledger"],
            ),
            "autopilot": _summarise_autopilot(buckets["autopilot"]),
            "codex_cli_freshness": _summarise_codex_cli_freshness(buckets["codex_cli_freshness"]),
            "unknown": {"records": len(buckets["unknown"])},
        }
    )


def _format_parse_error_details(parse_error_details: list[ParseErrorDetail]) -> list[str]:
    if not parse_error_details:
        return []
    family_counts = _parse_error_counter(parse_error_details, "artifact_family")
    artifact_counts = _parse_error_counter(parse_error_details, "artifact")
    lines = [
        "",
        "## Parse Error Details",
        f"- By artifact family: {_format_counter(family_counts)}",
        f"- By artifact: {_format_counter(artifact_counts)}",
        "",
        "| Artifact family | Artifact | File | Line | Reason | Count |",
        "|-----------------|----------|------|------|--------|-------|",
    ]
    displayed_count = 0
    for detail in parse_error_details[:_MAX_PARSE_ERROR_ROWS]:
        line = str(detail.line) if detail.line is not None else "n/a"
        displayed_count += detail.count
        lines.append(
            "| "
            f"{_markdown_table_cell(detail.artifact_family)} | "
            f"{_markdown_table_cell(detail.artifact)} | "
            f"{_markdown_table_cell(detail.path)} | "
            f"{_markdown_table_cell(line)} | "
            f"{_markdown_table_cell(detail.reason)} | "
            f"{detail.count} |"
        )
    remaining = _parse_error_count(parse_error_details) - displayed_count
    if remaining > 0:
        lines.append("")
        lines.append(f"- Additional parse errors omitted from table: {remaining}")
    return lines


def _parse_error_contract(parse_error_details: list[ParseErrorDetail]) -> dict[str, Any]:
    family_counts = _parse_error_counter(parse_error_details, "artifact_family")
    artifact_counts = _parse_error_counter(parse_error_details, "artifact")
    reason_counts = _parse_error_counter(parse_error_details, "reason")
    details = [detail.as_dict() for detail in parse_error_details[:_MAX_PARSE_ERROR_ROWS]]
    detail_count = _parse_error_count(parse_error_details)
    emitted_count = sum(detail["count"] for detail in details)
    omitted_count = max(0, detail_count - emitted_count)
    return {
        "count": detail_count,
        "stored_detail_count": len(parse_error_details),
        "by_artifact_family": dict(sorted(family_counts.items())),
        "by_artifact": dict(sorted(artifact_counts.items())),
        "by_reason": dict(sorted(reason_counts.items())),
        "details": details,
        "details_truncated": omitted_count > 0,
        "omitted_count": omitted_count,
    }


def _metric_source_contract(entries: list[dict[str, Any]]) -> dict[str, Any]:
    family_counts = Counter(
        str(entry.get("metric_artifact_family") or entry.get("artifact_family") or "unknown")
        for entry in entries
    )
    artifact_counts = Counter(
        str(entry.get("metric_artifact") or entry.get("artifact_name") or "unknown")
        for entry in entries
    )
    file_counts = Counter(str(entry.get("metric_path") or "unknown") for entry in entries)
    return {
        "by_artifact_family": dict(sorted(family_counts.items())),
        "by_artifact": dict(sorted(artifact_counts.items())),
        "by_file": dict(sorted(file_counts.items())),
    }


def _artifact_download_contract(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    artifacts = manifest.get("artifacts")
    failed_artifacts: list[dict[str, Any]] = []
    pending_artifacts: list[dict[str, Any]] = []
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            download_status = str((artifact.get("download") or {}).get("status") or "pending")
            unzip_status = str((artifact.get("unzip") or {}).get("status") or "pending")
            entry = {
                "id": artifact.get("id"),
                "name": artifact.get("name") or "unknown",
                "family": artifact.get("family") or "unknown",
                "artifact_dir": artifact.get("artifact_dir") or "",
                "download_status": download_status,
                "unzip_status": unzip_status,
                "download_error": (artifact.get("download") or {}).get("error") or "",
                "unzip_error": (artifact.get("unzip") or {}).get("error") or "",
            }
            if download_status == "failed" or unzip_status == "failed":
                failed_artifacts.append(entry)
            elif download_status == "pending" or unzip_status == "pending":
                pending_artifacts.append(entry)
    return {
        "schema": manifest.get("schema") or "unknown",
        "path": manifest_path.as_posix(),
        "status": manifest.get("status") or "unknown",
        "selection": manifest.get("selection") or {},
        "stats": manifest.get("stats") or {},
        "failed_artifacts": failed_artifacts,
        "pending_artifacts": pending_artifacts,
    }


def _read_artifact_download_contract(manifest_path: Path) -> dict[str, Any] | None:
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema": "workflows-weekly-metrics-artifact-download-manifest/v1",
            "path": manifest_path.as_posix(),
            "status": "error",
            "error_message": str(exc),
            "selection": {},
            "stats": {},
            "failed_artifacts": [],
            "pending_artifacts": [],
        }
    if not isinstance(manifest, dict):
        return {
            "schema": "workflows-weekly-metrics-artifact-download-manifest/v1",
            "path": manifest_path.as_posix(),
            "status": "error",
            "error_message": "manifest-not-object",
            "selection": {},
            "stats": {},
            "failed_artifacts": [],
            "pending_artifacts": [],
        }
    return _artifact_download_contract(manifest, manifest_path)


def build_summary(
    entries: list[dict[str, Any]],
    errors: int,
    parse_error_details: list[ParseErrorDetail] | None = None,
) -> str:
    buckets = _bucket_entries(entries)
    timestamps: list[_dt.datetime] = []

    for entry in entries:
        for key in ("timestamp", "created_at", "time", "run_started_at"):
            ts = _parse_timestamp(entry.get(key))
            if ts is not None:
                timestamps.append(ts)
                break

    keepalive = _summarise_keepalive(buckets["keepalive"])
    autofix = _summarise_autofix(buckets["autofix"])
    verifier = _summarise_verifier(
        buckets["verifier"] + buckets["terminal_disposition"],
        buckets["verifier_followup_ledger"],
    )
    autopilot = _summarise_autopilot(buckets["autopilot"])
    codex_cli_freshness = _summarise_codex_cli_freshness(buckets["codex_cli_freshness"])

    now = _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "# Agent Metrics Summary",
        "",
        f"Generated: {now}",
        (
            f"Records: {len(entries)} "
            f"(keepalive {keepalive['runs']}, autofix {autofix['attempts']}, "
            f"verifier {verifier['runs']}, "
            f"terminal dispositions {verifier['terminal_records']}, "
            f"verifier follow-up ledgers {verifier['ledger_records']}, "
            f"codex CLI freshness {codex_cli_freshness['records']}, "
            f"autopilot {autopilot['records']}, "
            f"unknown {len(buckets['unknown'])})"
        ),
        f"Parse errors: {errors}",
    ]

    if timestamps:
        earliest = min(timestamps).isoformat().replace("+00:00", "Z")
        latest = max(timestamps).isoformat().replace("+00:00", "Z")
        lines.append(f"Range: {earliest} to {latest}")

    if parse_error_details:
        lines.extend(_format_parse_error_details(parse_error_details))

    lines.extend(
        [
            "",
            "## Keepalive",
            f"- Runs: {keepalive['runs']}",
            f"- PRs: {keepalive['prs']}",
            f"- Avg iterations: {keepalive['avg_iterations']:.1f}",
            f"- Stop reasons: {_format_counter(keepalive['stop_reasons'])}",
            f"- Actions: {_format_counter(keepalive['actions'])}",
            f"- Gate conclusions: {_format_counter(keepalive['gate_results'])}",
            f"- Tasks complete rate: {_format_rate(keepalive['tasks_complete'], keepalive['runs'])}",
            "",
            "## Autofix",
            f"- Attempts: {autofix['attempts']}",
            f"- PRs: {autofix['prs']}",
            f"- Fixes applied: {_format_rate(autofix['fixes_applied'], autofix['attempts'])}",
            f"- Trigger reasons: {_format_counter(autofix['triggers'])}",
            f"- Gate results after: {_format_counter(autofix['gate_results'])}",
            "",
            "## Verifier",
            f"- Runs: {verifier['runs']}",
            f"- PRs: {verifier['prs']}",
            f"- Verdicts: {_format_counter(verifier['verdicts'])}",
            f"- Issues created: {verifier['issues_created']}",
            f"- Avg acceptance criteria: {verifier['avg_acceptance']:.1f}",
            f"- Terminal disposition records: {verifier['terminal_records']}",
            f"- Terminal dispositions: {_format_counter(verifier['terminal_dispositions'])}",
            f"- Terminal disposition sources: {_format_counter(verifier['terminal_sources'])}",
            f"- Verifier follow-up ledger records: {verifier['ledger_records']}",
            f"- Verifier follow-up ledger dispositions: {_format_counter(verifier['ledger_dispositions'])}",
            f"- Verifier follow-up ledger PRs: {verifier['ledger_prs']}",
            f"- Verifier follow-up issues linked: {verifier['ledger_followup_issues']}",
            f"- Verifier follow-up needs-human records: {verifier['ledger_needs_human']}",
            f"- Verifier follow-up avg chain depth: {verifier['ledger_avg_chain_depth']:.1f}",
            f"- Verifier follow-up max chain depth: {verifier['ledger_max_chain_depth']}",
            f"- Verifier follow-up policy records: {verifier['ledger_policy_records']}",
            f"- Verifier follow-up policy actions: {_format_counter(verifier['ledger_policy_actions'])}",
            (
                "- Verifier follow-up policy triggers: "
                f"{_format_counter(verifier['ledger_policy_triggers'])}"
            ),
            (
                "- Verifier follow-up depth-limit records: "
                f"{verifier['ledger_policy_depth_limit_exceeded']}"
            ),
            f"- Verifier models: {_format_counter(verifier['verifier_models'])}",
            f"- Verifier CLI versions: {_format_counter(verifier['verifier_cli_versions'])}",
            f"- Unsupported verifier models: {_format_counter(verifier['unsupported_verifier_models'])}",
            (
                "- Unsupported model dispositions: "
                f"{_format_counter(verifier['unsupported_model_dispositions'])}"
            ),
            (
                "- Missing verifier model metadata: "
                f"{_format_counter(verifier['missing_verifier_model_metadata'])}"
            ),
            (
                "- Legacy missing verifier model metadata: "
                f"{_format_counter(verifier['legacy_missing_verifier_model_metadata'])}"
            ),
            f"- Model selection reasons: {_format_counter(verifier['model_selection_reasons'])}",
            f"- Verifier modes: {_format_counter(verifier['verifier_modes'])}",
            "",
            "## Codex CLI Freshness",
            f"- Records: {codex_cli_freshness['records']}",
            f"- Statuses: {_format_counter(codex_cli_freshness['statuses'])}",
            f"- Packages: {_format_counter(codex_cli_freshness['packages'])}",
            f"- Pinned versions: {_format_counter(codex_cli_freshness['pinned_versions'])}",
            f"- Latest versions: {_format_counter(codex_cli_freshness['latest_versions'])}",
            f"- Outdated records: {codex_cli_freshness['outdated_records']}",
            (
                "- Latest unavailable records: "
                f"{codex_cli_freshness['latest_unavailable_records']}"
            ),
            (
                "- Max version delta: "
                f"major {codex_cli_freshness['max_version_delta']['major']}, "
                f"minor {codex_cli_freshness['max_version_delta']['minor']}, "
                f"patch {codex_cli_freshness['max_version_delta']['patch']}"
            ),
            f"- Update targets: {_format_counter(codex_cli_freshness['update_targets'])}",
        ]
    )

    # ── Auto-pilot pipeline section ──────────────────────────────────
    if autopilot["records"] > 0:
        lines.extend(
            [
                "",
                "## Auto-Pilot Pipeline",
                f"- Records: {autopilot['records']}",
                f"- Issues: {autopilot['issues']}",
                f"- Total step executions: {autopilot['total_steps']}",
                f"- Cycle records: {autopilot['cycle_records']}",
                f"- Cycle count distribution: {_format_counter(autopilot['cycle_counts'])}",
                (
                    "- Cycle step completion: "
                    f"{_format_rate(autopilot['cycle_steps_completed'], autopilot['cycle_steps_attempted'])}"
                ),
                f"- Escalations: {autopilot['escalation_count']}",
                f"- Needs-human escalation rate: {_format_rate(autopilot['needs_human_count'], autopilot['escalation_count'])}",
                f"- Escalation reasons: {_format_counter(autopilot['escalation_reasons'])}",
                f"- Failure reasons: {_format_counter(autopilot['failure_reasons'])}",
            ]
        )

        if autopilot["step_avg_duration_ms"]:
            lines.append("")
            lines.append("### Step Average Durations")
            for step, avg_ms in sorted(autopilot["step_avg_duration_ms"].items()):
                avg_s = avg_ms / 1000.0
                successes = autopilot["step_successes"].get(step, 0)
                failures = autopilot["step_failures"].get(step, 0)
                total = successes + failures
                lines.append(
                    f"- {step}: {avg_s:.1f}s avg ({_format_rate(successes, total)} success)"
                )

    return "\n".join(lines) + "\n"


def build_summary_contract(
    entries: list[dict[str, Any]],
    parse_error_details: list[ParseErrorDetail],
    artifact_downloads: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry_buckets = _bucket_entries(entries)
    buckets: dict[str, int] = Counter(
        name for name, bucket_entries in entry_buckets.items() for _ in bucket_entries
    )
    timestamps: list[_dt.datetime] = []
    for entry in entries:
        for key in ("timestamp", "created_at", "time", "run_started_at"):
            ts = _parse_timestamp(entry.get(key))
            if ts is not None:
                timestamps.append(ts)
                break
    generated_at = (
        _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    contract: dict[str, Any] = {
        "schema": "workflows-agent-metrics-summary/v1",
        "generated_at": generated_at,
        "record_count": len(entries),
        "record_buckets": dict(sorted(buckets.items())),
        "metric_sources": _metric_source_contract(entries),
        "parse_errors": _parse_error_contract(parse_error_details),
        "summaries": _summary_metrics_contract(entry_buckets),
    }
    if artifact_downloads is not None:
        contract["artifact_downloads"] = artifact_downloads
    if timestamps:
        contract["range"] = {
            "earliest": min(timestamps).isoformat().replace("+00:00", "Z"),
            "latest": max(timestamps).isoformat().replace("+00:00", "Z"),
        }
    return contract


def main() -> int:
    metrics_paths_raw = os.environ.get("METRICS_PATHS", "")
    metrics_paths = [item.strip() for item in metrics_paths_raw.split(",") if item.strip()]
    metrics_dir = os.environ.get("METRICS_DIR", _DEFAULT_METRICS_DIR)
    output_path = Path(os.environ.get("OUTPUT_PATH", _DEFAULT_OUTPUT))
    output_json_path = Path(os.environ.get("OUTPUT_JSON_PATH", _DEFAULT_JSON_OUTPUT))
    download_manifest_path = Path(
        os.environ.get("METRICS_ARTIFACT_DOWNLOAD_MANIFEST_JSON", _DEFAULT_DOWNLOAD_MANIFEST_PATH)
    )
    artifact_downloads = _read_artifact_download_contract(download_manifest_path)

    files = _gather_metrics_files(metrics_paths, metrics_dir)
    if not files:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("No metrics files found to aggregate.\n", encoding="utf-8")
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(
            json.dumps(
                build_summary_contract([], [], artifact_downloads),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print("No metrics files found to aggregate.", file=sys.stderr)
        return 0

    entries, parse_error_details = _read_ndjson(files)
    summary = build_summary(entries, _parse_error_count(parse_error_details), parse_error_details)
    summary_contract = build_summary_contract(entries, parse_error_details, artifact_downloads)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary, encoding="utf-8")
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(summary_contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote metrics summary to {output_path}")
    print(f"Wrote metrics summary JSON to {output_json_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
