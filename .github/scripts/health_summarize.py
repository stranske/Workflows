#!/usr/bin/env python3
"""Generate unified summaries for Health guardrail workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

# Add the root directory to Python path to enable tools import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.test_failure_signature import build_signature_hash


def _read_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def _escape_table(text: str) -> str:
    return text.replace("|", "&#124;")


def _doc_url() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    ref_name = os.environ.get("GITHUB_REF_NAME")
    base_ref = os.environ.get("GITHUB_BASE_REF")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")

    ref = base_ref if event_name == "pull_request" and base_ref else ref_name or "main"

    if not repo:
        return "https://github.com/stranske/Workflows/blob/main/docs/ci/WORKFLOWS.md#ci-signature-guard-fixtures"

    return f"{server}/{repo}/blob/{ref}/docs/ci/WORKFLOWS.md#ci-signature-guard-fixtures"


def _signature_row(jobs_path: Path, expected_path: Path) -> Mapping[str, str]:
    jobs_data = _load_json(jobs_path)
    if not isinstance(jobs_data, list):
        return {
            "check": "Health 43 CI Signature Guard",
            "status": "❌ Fixture unreadable",
            "details": _escape_table(f"Unable to load signature jobs fixture at {jobs_path}"),
            "conclusion": "failure",
        }

    expected = expected_path.read_text(encoding="utf-8").strip()
    actual = build_signature_hash(jobs_data)
    matches = actual == expected

    if matches:
        status = "✅ Hash matches expected"
        conclusion = "success"
    else:
        status = "❌ Hash drift detected"
        conclusion = "failure"

    details_lines = [
        f"Fixture: `{jobs_path}`",
        f"Expected: `{expected}`",
        f"Computed: `{actual}`",
        f"Docs: [CI signature guard docs]({_doc_url()})",
    ]

    if not matches:
        details_lines.append("Update `.github/signature-fixtures` when intentional changes occur.")

    return {
        "check": "Health 43 CI Signature Guard",
        "status": status,
        "details": _escape_table("<br>".join(details_lines)),
        "conclusion": conclusion,
    }


def _extract_contexts(section: object) -> list[str]:
    raw_contexts = section.get("contexts") if isinstance(section, Mapping) else section

    if isinstance(raw_contexts, str):
        contexts = [raw_contexts]
    elif isinstance(raw_contexts, Iterable) and not isinstance(raw_contexts, (str, bytes)):
        contexts = [str(item).strip() for item in raw_contexts]
    else:
        contexts = []
    return [context for context in contexts if context]


def _format_require_up_to_date(snapshot: Mapping[str, Any]) -> str:
    current = None
    target = None

    current_section = snapshot.get("current")
    if isinstance(current_section, Mapping):
        current = current_section.get("strict")

    for key in ("after", "desired"):
        candidate = snapshot.get(key)
        if isinstance(candidate, Mapping):
            target = candidate.get("strict")
            if target is not None:
                break

    def _bool_label(value: object) -> str:
        if value is True:
            return "✅ True"
        if value is False:
            return "❌ False"
        if value is None:
            return "⚠️ Unknown"
        return str(value)

    if target is None or target == current:
        reference = current if current is not None else target
        return _bool_label(reference)

    return f"{_bool_label(current)} → {_bool_label(target)}"


def _select_previous_section(snapshot: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for key in ("after", "desired", "current"):
        candidate = snapshot.get(key)
        if isinstance(candidate, Mapping):
            return candidate
    return None


def _format_delta(
    current_snapshot: Mapping[str, Any] | None,
    previous_snapshot: Mapping[str, Any] | None,
) -> str:
    if not isinstance(previous_snapshot, Mapping):
        return "No previous snapshot"
    if not isinstance(current_snapshot, Mapping):
        return "–"

    current_section = current_snapshot.get("current")
    if not isinstance(current_section, Mapping):
        return "–"

    previous_section = _select_previous_section(previous_snapshot)
    if previous_section is None:
        return "–"

    current_contexts = _extract_contexts(current_section)
    previous_contexts = _extract_contexts(previous_section)

    added = [context for context in current_contexts if context not in previous_contexts]
    removed = [context for context in previous_contexts if context not in current_contexts]

    parts: list[str] = []
    if added:
        parts.append("+" + ", ".join(added))
    if removed:
        parts.append("−" + ", ".join(removed))

    current_strict = current_section.get("strict") if isinstance(current_section, Mapping) else None
    previous_strict = (
        previous_section.get("strict") if isinstance(previous_section, Mapping) else None
    )

    if current_strict != previous_strict:

        def _bool_status(value: object) -> str:
            if value is True:
                return "✅ True"
            if value is False:
                return "❌ False"
            if value is None:
                return "⚠️ Unknown"
            return str(value)

        parts.append(
            f"Require up to date: {_bool_status(previous_strict)} → {_bool_status(current_strict)}"
        )

    return "; ".join(parts) if parts else "No change"


def _snapshot_detail(
    label: str,
    snapshot: Mapping[str, Any] | None,
    previous_snapshot: Mapping[str, Any] | None,
    *,
    has_token: bool,
) -> tuple[str, str]:
    if snapshot is None:
        if label == "Enforcement" and not has_token:
            return (
                _escape_table(
                    f"{label}: Skipped (token not configured; running in observer mode)."
                ),
                "info",
            )
        return (
            _escape_table(f"{label}: Snapshot missing."),
            "warning",
        )

    if snapshot.get("error"):
        return (
            _escape_table(f"{label}: ❌ {snapshot.get('error')}"),
            "failure",
        )

    changes_required = snapshot.get("changes_required")
    require_up_to_date = _format_require_up_to_date(snapshot)
    current_contexts = ", ".join(_extract_contexts(snapshot.get("current"))) or "–"
    target_contexts = (
        ", ".join(
            _extract_contexts(snapshot.get("after")) or _extract_contexts(snapshot.get("desired"))
        )
        or "–"
    )
    delta = _format_delta(snapshot, previous_snapshot)

    status_bits: list[str] = []
    severity = "success"
    if changes_required:
        status_bits.append("⚠️ Drift detected")
        severity = "warning"
    else:
        status_bits.append("✅ In sync")

    if snapshot.get("changes_applied"):
        status_bits.append("✅ Changes applied")

    if snapshot.get("strict_unknown"):
        flag = (
            "⚠️ Require up to date unknown (treated as drift)"
            if snapshot.get("require_strict")
            else "⚠️ Require up to date unknown"
        )
        status_bits.append(flag)
        severity = "warning"

    if snapshot.get("no_clean"):
        status_bits.append("ℹ️ Cleanup disabled")

    detail = (
        f"{label}: {'; '.join(status_bits)}; "
        f"Require up to date: {require_up_to_date}; "
        f"Current: {current_contexts}; Target: {target_contexts}; Δ: {delta}"
    )
    return _escape_table(detail), severity


def _branch_row(
    snapshot_dir: Path,
    *,
    has_token: bool,
    pairs: Iterable[tuple[str, Mapping[str, Any] | None, Mapping[str, Any] | None]] | None = None,
) -> Mapping[str, str]:
    enforcement = _load_json(snapshot_dir / "enforcement.json")
    verification = _load_json(snapshot_dir / "verification.json")

    previous_dir = snapshot_dir / "previous"
    previous_enforcement = _load_json(previous_dir / "enforcement.json")
    previous_verification = _load_json(previous_dir / "verification.json")

    details: list[str] = []
    severities: list[str] = []

    if pairs is None:
        scenario_pairs = [
            ("Enforcement", enforcement, previous_enforcement),
            ("Verification", verification, previous_verification),
        ]
    else:
        scenario_pairs = list(pairs)

    for label, snapshot, previous in scenario_pairs:
        detail, severity = _snapshot_detail(label, snapshot, previous, has_token=has_token)
        details.append(detail)
        severities.append(severity)

    if not has_token:
        details.append(
            _escape_table(
                "Observer mode: configure `BRANCH_PROTECTION_TOKEN` with admin scope to enable enforcement."
            )
        )

    severity_rank = {"success": 0, "info": 1, "warning": 2, "failure": 3}
    worst = "success"
    for severity in severities:
        if severity_rank[severity] > severity_rank[worst]:
            worst = severity

    if worst == "failure":
        status = "❌ Branch protection error"
        conclusion = "failure"
    elif worst == "warning":
        status = "⚠️ Branch protection attention"
        conclusion = "warning"
    else:
        status = "✅ Branch protection in sync"
        conclusion = "success"

    if not details:
        details.append(
            _escape_table(
                "No branch protection snapshots were produced. Check prior steps for failures."
            )
        )
        if worst != "failure":
            status = "⚠️ Branch protection attention"
            conclusion = "warning"

    return {
        "check": "Health 44 Gate Branch Protection",
        "status": status,
        "details": "<br>".join(details),
        "conclusion": conclusion,
    }


def _write_json(path: Path, rows: list[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2)
        handle.write("\n")


def _write_summary(path: Path, rows: list[Mapping[str, str]]) -> None:
    if not rows:
        return

    with path.open("a", encoding="utf-8") as handle:
        handle.write("### Health guardrail summary\n\n")
        handle.write("| Check | Status | Details |\n")
        handle.write("| --- | --- | --- |\n")
        for row in rows:
            check = row.get("check", "–")
            status = row.get("status", "–")
            details = row.get("details", "–") or "–"
            handle.write(f"| {check} | {status} | {details} |\n")
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signature-jobs", type=Path)
    parser.add_argument("--signature-expected", type=Path)
    parser.add_argument("--snapshot-dir", type=Path)
    parser.add_argument("--has-enforce-token", dest="has_enforce_token")
    parser.add_argument("--write-json", type=Path)
    parser.add_argument("--write-summary", type=Path)

    args = parser.parse_args(argv)

    rows: list[Mapping[str, str]] = []

    if args.signature_jobs and args.signature_expected:
        rows.append(_signature_row(args.signature_jobs, args.signature_expected))

    if args.snapshot_dir:
        rows.append(
            _branch_row(
                args.snapshot_dir,
                has_token=_read_bool(args.has_enforce_token),
            )
        )

    if args.write_json:
        _write_json(args.write_json, rows)

    if args.write_summary:
        _write_summary(args.write_summary, rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
