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


def build_conformance_report(
    artifact_paths: Mapping[str, Path],
    *,
    registry: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return one conformance row per registry entry."""
    now = now or datetime.now(UTC)
    stale_after_hours = int(registry.get("stale_after_hours", 168))
    schema = langsmith_fleet.load_record_schema()
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {"missing": 0, "invalid": 0, "stale": 0, "valid": 0}

    for entry in sorted(registry["repos"], key=lambda item: (item["repo"], item["surface"])):
        repo = entry["repo"]
        surface = entry["surface"]
        artifact_name = entry["artifact_name"]
        artifact_path = artifact_paths.get(repo)
        first_error: str | None = None
        latest_recorded_at: datetime | None = None
        record_count = 0

        if artifact_path is None or not artifact_path.exists():
            status = "missing"
        else:
            records, parse_errors = langsmith_fleet.load_ndjson(artifact_path)
            record_count = len(records)
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
                latest_recorded_at = langsmith_fleet._latest_recorded_at(records)
                if (
                    latest_recorded_at
                    and (now - latest_recorded_at).total_seconds() > stale_after_hours * 3600
                ):
                    status = "stale"
                else:
                    status = "valid"

        counts[status] += 1
        rows.append(
            {
                "repo": repo,
                "surface": surface,
                "issue": entry["issue"],
                "artifact_name": artifact_name,
                "artifact_path": str(artifact_path) if artifact_path else None,
                "record_count": record_count,
                "latest_recorded_at": (
                    latest_recorded_at.isoformat() if latest_recorded_at else None
                ),
                "status": status,
                "first_error": first_error,
            }
        )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "status_counts": counts,
        "total_registry_entries": len(rows),
        "rows": rows,
    }


def format_conformance_markdown(report: dict[str, Any]) -> str:
    """Render a compact Markdown conformance report."""
    counts = report.get("status_counts", {})
    lines = [
        "# LangSmith Fleet Conformance",
        "",
        f"- Registry entries: {report.get('total_registry_entries', 0)}",
        f"- Valid: {counts.get('valid', 0)}",
        f"- Missing: {counts.get('missing', 0)}",
        f"- Stale: {counts.get('stale', 0)}",
        f"- Invalid: {counts.get('invalid', 0)}",
        "",
        "| Repo | Surface | Status | Records | Latest | First Error |",
        "|------|---------|--------|---------|--------|-------------|",
    ]
    for row in report.get("rows", []):
        lines.append(
            "| {repo} | {surface} | {status} | {record_count} | {latest} | {error} |".format(
                repo=row["repo"],
                surface=row["surface"],
                status=row["status"],
                record_count=row["record_count"],
                latest=row.get("latest_recorded_at") or "",
                error=row.get("first_error") or "",
            )
        )
    return "\n".join(lines) + "\n"


def artifact_paths_from_root(records_root: Path, registry: dict[str, Any]) -> dict[str, Path]:
    """Build repo -> artifact path mapping from the conventional records root."""
    paths: dict[str, Path] = {}
    for entry in registry["repos"]:
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
