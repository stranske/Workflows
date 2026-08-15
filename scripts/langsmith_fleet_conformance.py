#!/usr/bin/env python3
"""Build a per-repo LangSmith fleet conformance report from downloaded artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import langsmith_fleet  # noqa: E402

REPORT_SCHEMA_VERSION = "langsmith-fleet-conformance/v1"


def artifact_path_for_repo(records_root: Path, repo: str, artifact_name: str) -> Path:
    """Return the conventional downloaded artifact path for a repo."""
    owner, name = repo.split("/", 1)
    return records_root / f"{owner}__{name}" / artifact_name


def row_from_summary(
    summary: Mapping[str, Any],
    *,
    repo: str,
    surface: str,
) -> dict[str, Any] | None:
    """Return one summary row matching repo/surface."""
    rows = summary.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("repo")) == repo and str(row.get("surface")) == surface:
            return row
    return None


def build_conformance_report(
    artifact_paths: Mapping[str, Path],
    *,
    registry: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return one conformance row per registry entry."""
    now = now or datetime.now(UTC)
    schema = langsmith_fleet.load_record_schema()
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {
        "missing": 0,
        "invalid": 0,
        "stale": 0,
        "valid": 0,
        "direct": 0,
        "not-applicable": 0,
    }

    for entry in sorted(registry["repos"], key=lambda item: (item["repo"], item["surface"])):
        repo = entry["repo"]
        surface = entry["surface"]
        artifact_name = entry["artifact_name"]
        evidence_mode = str(entry.get("evidence_mode") or "artifact")
        artifact_path = artifact_paths.get(repo)
        first_error: str | None = None
        latest_recorded_at: datetime | None = None
        record_count = 0

        if evidence_mode == "langsmith-direct":
            status = "direct"
            first_error = None
            artifact_path = None
        elif artifact_path is None or not artifact_path.exists():
            status = "missing"
        else:
            records, parse_errors = langsmith_fleet.load_ndjson(artifact_path)
            record_count = len(records)
            summary = langsmith_fleet.summarize_fleet_records(records, registry=registry, now=now)
            summary_row = row_from_summary(summary, repo=repo, surface=surface)
            if summary_row:
                record_count = int(summary_row.get("record_count") or record_count)
                first_error = (
                    str(summary_row.get("first_error")) if summary_row.get("first_error") else None
                )
                latest_raw = summary_row.get("latest_recorded_at")
                if isinstance(latest_raw, str) and latest_raw.strip():
                    try:
                        latest_recorded_at = datetime.fromisoformat(
                            latest_raw.replace("Z", "+00:00")
                        )
                    except ValueError:
                        latest_recorded_at = None
            validation_errors = parse_errors + langsmith_fleet.validate_records(
                records,
                registry=registry,
                schema=schema,
            )
            if not records and not parse_errors:
                validation_errors.append(
                    langsmith_fleet.ValidationError(0, "artifact contains no records")
                )
            if validation_errors:
                status = "invalid"
                first_error = validation_errors[0].message
            else:
                # Parse status/first_error from canonical summary rows.
                status = str(summary_row.get("status")) if summary_row else "missing"
                if status not in {"missing", "invalid", "stale", "valid"}:
                    status = "invalid"
                    first_error = first_error or "summary row returned unknown status"

        counts[status] += 1
        rows.append(
            {
                "repo": repo,
                "surface": surface,
                "issue": entry["issue"],
                "artifact_name": artifact_name,
                "evidence_mode": evidence_mode,
                "artifact_path": str(artifact_path) if artifact_path else None,
                "record_count": record_count,
                "latest_recorded_at": (
                    latest_recorded_at.isoformat() if latest_recorded_at else None
                ),
                "status": status,
                "first_error": first_error,
                "reason": (
                    "Evidence is ingested from the central LangSmith project; "
                    "this artifact report does not validate that external path."
                    if status == "direct"
                    else None
                ),
            }
        )

    allowlist = registry.get("_allowlist") or {}
    allowlist_entries = allowlist.get("repos", []) if isinstance(allowlist, dict) else []
    for entry in sorted(allowlist_entries, key=lambda item: str(item.get("repo", ""))):
        counts["not-applicable"] += 1
        rows.append(
            {
                "repo": entry["repo"],
                "surface": "",
                "issue": None,
                "artifact_name": None,
                "evidence_mode": "none",
                "artifact_path": None,
                "record_count": 0,
                "latest_recorded_at": None,
                "status": "not-applicable",
                "first_error": None,
                "reason": entry["reason"],
                "registry_activation_condition": entry["registry_activation_condition"],
            }
        )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "status_counts": counts,
        "total_registry_entries": len(registry["repos"]),
        "total_allowlisted_repos": len(allowlist_entries),
        "rows": rows,
    }


def format_conformance_markdown(report: dict[str, Any]) -> str:
    """Render a compact Markdown conformance report."""
    counts = report.get("status_counts", {})
    lines = [
        "# LangSmith Fleet Conformance",
        "",
        f"- Registry entries: {report.get('total_registry_entries', 0)}",
        f"- Allowlisted repositories: {report.get('total_allowlisted_repos', 0)}",
        f"- Valid: {counts.get('valid', 0)}",
        f"- Missing: {counts.get('missing', 0)}",
        f"- Stale: {counts.get('stale', 0)}",
        f"- Invalid: {counts.get('invalid', 0)}",
        f"- Direct evidence: {counts.get('direct', 0)}",
        f"- Not applicable: {counts.get('not-applicable', 0)}",
        "",
        "| Repo | Surface | Evidence | Status | Records | Latest | Detail |",
        "|------|---------|----------|--------|---------|--------|--------|",
    ]
    for row in report.get("rows", []):
        lines.append(
            "| {repo} | {surface} | {evidence} | {status} | {record_count} | {latest} | {detail} |".format(
                repo=row["repo"],
                surface=row["surface"],
                evidence=row.get("evidence_mode") or "",
                status=row["status"],
                record_count=row["record_count"],
                latest=row.get("latest_recorded_at") or "",
                detail=row.get("first_error") or row.get("reason") or "",
            )
        )
    return "\n".join(lines) + "\n"


def artifact_paths_from_root(records_root: Path, registry: dict[str, Any]) -> dict[str, Path]:
    """Build repo -> artifact path mapping from the conventional records root."""
    paths: dict[str, Path] = {}
    for entry in registry["repos"]:
        if entry.get("evidence_mode") == "langsmith-direct":
            continue
        paths[entry["repo"]] = artifact_path_for_repo(
            records_root,
            entry["repo"],
            entry["artifact_name"],
        )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("config/langsmith_fleet_registry.json"),
        help="Fleet registry JSON path",
    )
    parser.add_argument(
        "--records-root",
        type=Path,
        required=True,
        help="Root containing owner__repo/<artifact_name> files",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Report output format",
    )
    args = parser.parse_args()

    registry = langsmith_fleet.load_registry(args.registry)
    report = build_conformance_report(
        artifact_paths_from_root(args.records_root, registry),
        registry=registry,
    )
    if args.format == "markdown":
        print(format_conformance_markdown(report), end="")
    else:
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
