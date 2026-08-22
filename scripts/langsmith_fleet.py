#!/usr/bin/env python3
"""Validate and summarize LangSmith fleet NDJSON records."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_VERSION = "langsmith-fleet/v1"
SCHEMA_PATH = Path("docs/contracts/schemas/langsmith-fleet-v1.schema.json")
REGISTRY_SCHEMA_VERSION = "langsmith-fleet-registry/v1"
ALLOWLIST_SCHEMA_VERSION = "langsmith-fleet-allowlist/v1"
ALLOWLIST_PATH = Path("config/langsmith_fleet_allowlist.json")
PARENT_WORKFLOWS_ISSUE = "stranske/Workflows#2150"
AGENT_CAPACITY_WINDOWS = {"5h", "weekly", "daily"}
VALID_EVIDENCE_MODES = {"artifact", "langsmith-direct"}
PAUSE_METADATA_FIELDS = (
    "paused_at",
    "pause_reason",
    "pause_owner",
    "resume_condition",
    "review_by",
)
MANAGED_CONSUMER_REPOS = {
    "stranske/Travel-Plan-Permission",
    "stranske/Template",
    "stranske/Counter_Risk",
    "stranske/Pension-Data",
    "stranske/Inv-Man-Intake",
    "stranske/Ready",
    "stranske/trip-planner",
    "stranske/Manager-Database",
    "stranske/Portable-Alpha-Extension-Model",
    "stranske/Trend_Model_Project",
    "stranske/Collab-Admin",
    "stranske/learning-management-system",
    "stranske/Fine-Art-Archive",
    "stranske/Orchestrator",
}
REQUIRED_ACTIVE_REPO_ISSUES = {
    "stranske/trip-planner": 1208,
    "stranske/Pension-Data": 445,
    "stranske/Manager-Database": 1048,
    "stranske/Counter_Risk": 610,
    "stranske/Inv-Man-Intake": 438,
    "stranske/Trend_Model_Project": 5311,
    "stranske/Portable-Alpha-Extension-Model": 1802,
}

REQUIRED_SHARED_FIELDS = (
    "schema_version",
    "repo",
    "surface",
    "operation",
    "run_id",
    "status",
    "github_issue",
    "domain",
)

OPTIONAL_SHARED_FIELDS = (
    "trace_id",
    "trace_url",
    "provider",
    "model",
    "latency_ms",
    "cost_usd",
    "input_hash",
    "output_hash",
    "github_pr",
    "recorded_at",
    "artifact_ref",
    "error_category",
)

VALID_STATUSES = {"success", "error", "fallback", "no_secret", "skipped"}


def load_record_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    """Load the JSON schema for LangSmith fleet records."""
    schema = json.loads(path.read_text())
    if not isinstance(schema, dict):
        raise ValueError("record schema must be a JSON object")
    return schema


@dataclass(frozen=True)
class ValidationError:
    """A single validation error for a fleet record."""

    line: int
    message: str


class FleetRecord(dict[str, Any]):
    """A loaded NDJSON record that preserves its source line number."""

    source_line: int

    def __init__(self, data: dict[str, Any], *, source_line: int) -> None:
        super().__init__(data)
        self.source_line = source_line


def load_ndjson(path: Path) -> tuple[list[dict[str, Any]], list[ValidationError]]:
    """Load NDJSON objects and return parse errors separately."""
    records: list[dict[str, Any]] = []
    errors: list[ValidationError] = []
    if not path.exists():
        return records, [ValidationError(0, f"{path} does not exist")]

    for line_number, raw_line in enumerate(path.read_text().splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(ValidationError(line_number, f"invalid JSON: {exc.msg}"))
            continue
        if not isinstance(parsed, dict):
            errors.append(ValidationError(line_number, "record must be a JSON object"))
            continue
        records.append(FleetRecord(parsed, source_line=line_number))
    return records, errors


def load_allowlist(path: Path = ALLOWLIST_PATH) -> dict[str, Any]:
    """Load and validate repositories where LangSmith is explicitly not applicable."""
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("allowlist must be a JSON object")
    validate_allowlist(data)
    return data


def load_registry(
    path: Path,
    *,
    allowlist_path: Path | None = ALLOWLIST_PATH,
) -> dict[str, Any]:
    """Load the fleet registry JSON."""
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("registry must be a JSON object")
    allowlist = None
    if allowlist_path is not None and allowlist_path.exists():
        allowlist = load_allowlist(allowlist_path)
        data["_allowlist"] = allowlist
    validate_registry(data, allowlist=allowlist)
    return data


def registry_surfaces(registry: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Index registry entries by (repo, surface)."""
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in registry.get("repos", []):
        if not isinstance(entry, dict):
            continue
        repo = str(entry.get("repo", "")).strip()
        surface = str(entry.get("surface", "")).strip()
        if repo and surface:
            indexed[(repo, surface)] = entry
    return indexed


def validate_allowlist(allowlist: dict[str, Any]) -> None:
    """Validate explicit non-applicable repository coverage."""
    if allowlist.get("schema_version") != ALLOWLIST_SCHEMA_VERSION:
        raise ValueError(f"allowlist schema_version must be {ALLOWLIST_SCHEMA_VERSION}")
    entries = allowlist.get("repos")
    if not isinstance(entries, list) or not entries:
        raise ValueError("allowlist repos must be a non-empty list")
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"allowlist repos[{index}] must be an object")
        repo = entry.get("repo")
        if not isinstance(repo, str) or not repo.strip():
            raise ValueError(f"allowlist repos[{index}].repo must be a non-empty string")
        normalized = repo.strip()
        if normalized in seen:
            raise ValueError(f"allowlist has duplicate repo {normalized}")
        seen.add(normalized)
        if entry.get("status") != "not-applicable":
            raise ValueError(f"allowlist repos[{index}].status must be not-applicable")
        for field in ("reason", "registry_activation_condition"):
            if not isinstance(entry.get(field), str) or not str(entry[field]).strip():
                raise ValueError(f"allowlist repos[{index}].{field} must be a non-empty string")


def validate_registry(
    registry: dict[str, Any],
    *,
    allowlist: dict[str, Any] | None = None,
) -> None:
    """Validate registry structure and required mappings."""
    if "agents" in registry and "repos" not in registry:
        validate_agent_registry_capacity(registry)
        return

    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError(f"registry schema_version must be {REGISTRY_SCHEMA_VERSION}")

    if allowlist is None:
        embedded_allowlist = registry.get("_allowlist")
        if isinstance(embedded_allowlist, dict):
            allowlist = embedded_allowlist

    stale_after_hours = registry.get("stale_after_hours")
    if isinstance(stale_after_hours, bool) or not isinstance(stale_after_hours, int):
        raise ValueError("registry stale_after_hours must be an integer")
    if stale_after_hours <= 0:
        raise ValueError("registry stale_after_hours must be positive")

    entries = registry.get("repos")
    if not isinstance(entries, list) or not entries:
        raise ValueError("registry repos must be a non-empty list")

    seen_keys: set[tuple[str, str]] = set()
    seen_repo_issues: dict[str, int] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"registry repos[{index}] must be an object")

        repo = entry.get("repo")
        issue = entry.get("issue")
        issue_number = entry.get("issue_number")
        parent_issue = entry.get("parent_issue")
        surface = entry.get("surface")
        operations = entry.get("operations")
        required_domain_fields = entry.get("required_domain_fields")
        artifact_name = entry.get("artifact_name")
        evidence_mode = entry.get("evidence_mode")
        rollout_status = entry.get("rollout_status")

        if not isinstance(repo, str) or not repo.strip():
            raise ValueError(f"registry repos[{index}].repo must be a non-empty string")
        if not isinstance(surface, str) or not surface.strip():
            raise ValueError(f"registry repos[{index}].surface must be a non-empty string")
        key = (repo.strip(), surface.strip())
        if key in seen_keys:
            raise ValueError(
                f"registry has duplicate repo/surface mapping for {repo.strip()}/{surface.strip()}"
            )
        seen_keys.add(key)

        if isinstance(issue_number, bool) or not isinstance(issue_number, int):
            raise ValueError(f"registry repos[{index}].issue_number must be an integer")
        if issue_number <= 0:
            raise ValueError(f"registry repos[{index}].issue_number must be positive")
        if not isinstance(issue, str) or not issue.strip():
            raise ValueError(f"registry repos[{index}].issue must be a non-empty string")
        expected_issue = f"{repo.strip()}#{issue_number}"
        if issue.strip() != expected_issue:
            raise ValueError(
                f"registry repos[{index}].issue must match repo#issue_number ({expected_issue})"
            )
        normalized_repo = repo.strip()
        if (
            normalized_repo in seen_repo_issues
            and seen_repo_issues[normalized_repo] != issue_number
        ):
            raise ValueError(
                f"registry repo {normalized_repo} has conflicting issue_number values "
                f"({seen_repo_issues[normalized_repo]} vs {issue_number})"
            )
        seen_repo_issues[normalized_repo] = issue_number
        if not isinstance(parent_issue, str) or not parent_issue.strip():
            raise ValueError(f"registry repos[{index}].parent_issue must be a non-empty string")
        if parent_issue.strip() != PARENT_WORKFLOWS_ISSUE:
            raise ValueError(
                f"registry repos[{index}].parent_issue must be {PARENT_WORKFLOWS_ISSUE}"
            )

        if not isinstance(artifact_name, str) or not artifact_name.strip():
            raise ValueError(f"registry repos[{index}].artifact_name must be a non-empty string")
        if evidence_mode not in VALID_EVIDENCE_MODES:
            allowed = ", ".join(sorted(VALID_EVIDENCE_MODES))
            raise ValueError(f"registry repos[{index}].evidence_mode must be one of {allowed}")
        if not isinstance(rollout_status, str) or not rollout_status.strip():
            raise ValueError(f"registry repos[{index}].rollout_status must be a non-empty string")
        if rollout_status == "paused":
            for field in PAUSE_METADATA_FIELDS:
                if not isinstance(entry.get(field), str) or not str(entry[field]).strip():
                    raise ValueError(
                        f"registry repos[{index}].{field} must be a non-empty string "
                        "when rollout_status is paused"
                    )
            try:
                paused_at = datetime.fromisoformat(entry["paused_at"].replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(
                    f"registry repos[{index}].paused_at must be an ISO timestamp"
                ) from exc
            if paused_at.tzinfo is None:
                raise ValueError(f"registry repos[{index}].paused_at must include a timezone")
            try:
                review_by = date.fromisoformat(entry["review_by"])
            except ValueError as exc:
                raise ValueError(f"registry repos[{index}].review_by must be an ISO date") from exc
            if review_by < paused_at.date():
                raise ValueError(f"registry repos[{index}].review_by cannot predate paused_at")

        if not isinstance(operations, list) or not operations:
            raise ValueError(f"registry repos[{index}].operations must be a non-empty list")
        if any(not isinstance(item, str) or not item.strip() for item in operations):
            raise ValueError(f"registry repos[{index}].operations must contain non-empty strings")

        if not isinstance(required_domain_fields, list) or not required_domain_fields:
            raise ValueError(
                f"registry repos[{index}].required_domain_fields must be a non-empty list"
            )
        if any(not isinstance(item, str) or not item.strip() for item in required_domain_fields):
            raise ValueError(
                f"registry repos[{index}].required_domain_fields must contain non-empty strings"
            )

    missing_required = [
        f"{repo}#{issue_number}"
        for repo, issue_number in REQUIRED_ACTIVE_REPO_ISSUES.items()
        if seen_repo_issues.get(repo) != issue_number
    ]
    if missing_required:
        raise ValueError(
            "registry missing required active repo issue mappings: "
            + ", ".join(sorted(missing_required))
        )

    allowlist_entries = (allowlist or {}).get("repos", [])
    allowlisted_repos = {
        str(entry.get("repo", "")).strip()
        for entry in allowlist_entries
        if isinstance(entry, dict) and str(entry.get("repo", "")).strip()
    }
    overlap = sorted(set(seen_repo_issues) & allowlisted_repos)
    if overlap:
        raise ValueError(
            "repositories cannot be both registered and allowlisted: " + ", ".join(overlap)
        )
    covered_consumers = set(seen_repo_issues) | allowlisted_repos
    unclassified = sorted(MANAGED_CONSUMER_REPOS - covered_consumers)
    if unclassified:
        raise ValueError(
            "managed consumer repos missing registry or allowlist status: "
            + ", ".join(unclassified)
        )


def validate_agent_registry_capacity(registry: dict[str, Any]) -> None:
    """Validate capacity blocks in the YAML agent registry."""
    agents = registry.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise ValueError("agent registry agents must be a non-empty mapping")

    for agent_key, agent_config in agents.items():
        if not isinstance(agent_key, str) or not agent_key.strip():
            raise ValueError("agent registry keys must be non-empty strings")
        if not isinstance(agent_config, dict):
            raise ValueError(f"agent registry {agent_key} must be an object")

        capacity = agent_config.get("capacity")
        if not isinstance(capacity, dict):
            raise ValueError(f"agent registry {agent_key}.capacity must be an object")

        window = capacity.get("window")
        if window not in AGENT_CAPACITY_WINDOWS:
            allowed = ", ".join(sorted(AGENT_CAPACITY_WINDOWS))
            raise ValueError(f"agent registry {agent_key}.capacity.window must be one of {allowed}")

        limit = capacity.get("limit")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError(
                f"agent registry {agent_key}.capacity.limit must be a positive integer"
            )


def _is_hash_or_ref(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    return (
        text.startswith("sha256:")
        or text.startswith("hash:")
        or text.startswith("artifact:")
        or text.startswith("ref:")
    )


def _validate_number(record: dict[str, Any], field: str, line: int) -> list[ValidationError]:
    value = record.get(field)
    if value is None:
        return []
    if isinstance(value, bool) or not isinstance(value, int | float):
        return [ValidationError(line, f"{field} must be a number when present")]
    if value < 0:
        return [ValidationError(line, f"{field} must be non-negative")]
    return []


def _validate_recorded_at(value: Any, line: int) -> list[ValidationError]:
    if value in (None, ""):
        return []
    if not isinstance(value, str):
        return [ValidationError(line, "recorded_at must be an ISO timestamp")]
    normalized = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return [ValidationError(line, "recorded_at must be an ISO timestamp")]
    return []


def validate_record(
    record: dict[str, Any],
    *,
    line: int = 1,
    registry: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None,
) -> list[ValidationError]:
    """Validate a single LangSmith fleet record."""
    errors: list[ValidationError] = []
    if schema:
        for schema_error in Draft202012Validator(schema).iter_errors(record):
            path_text = ".".join(str(part) for part in schema_error.path)
            prefix = f"{path_text}: " if path_text else ""
            errors.append(
                ValidationError(line, f"schema violation: {prefix}{schema_error.message}")
            )

    for field in REQUIRED_SHARED_FIELDS:
        if field not in record:
            errors.append(ValidationError(line, f"missing required field: {field}"))

    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append(ValidationError(line, f"schema_version must be {SCHEMA_VERSION}"))

    status = record.get("status")
    if status not in VALID_STATUSES:
        errors.append(
            ValidationError(line, f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
        )

    domain = record.get("domain")
    if not isinstance(domain, dict) or not domain:
        errors.append(ValidationError(line, "domain must be a non-empty object"))

    for field in ("repo", "surface", "operation", "run_id", "github_issue"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(ValidationError(line, f"{field} must be a non-empty string"))

    for field in ("latency_ms", "cost_usd"):
        errors.extend(_validate_number(record, field, line))

    errors.extend(_validate_recorded_at(record.get("recorded_at"), line))

    for field in ("input_hash", "output_hash"):
        if not _is_hash_or_ref(record.get(field)):
            errors.append(ValidationError(line, f"{field} must be a hash or artifact reference"))

    trace_id = record.get("trace_id")
    trace_url = record.get("trace_url")
    if trace_url and not isinstance(trace_url, str):
        errors.append(ValidationError(line, "trace_url must be a string when present"))
    if trace_id and not isinstance(trace_id, str):
        errors.append(ValidationError(line, "trace_id must be a string when present"))

    if registry:
        entries = registry_surfaces(registry)
        repo = str(record.get("repo", "")).strip()
        surface = str(record.get("surface", "")).strip()
        entry = entries.get((repo, surface))
        if not entry:
            errors.append(ValidationError(line, f"{repo}/{surface} is not in registry"))
        elif isinstance(domain, dict):
            operations = entry.get("operations", [])
            operation = str(record.get("operation", "")).strip()
            if operations and operation not in operations:
                allowed = ", ".join(sorted(str(item) for item in operations))
                errors.append(
                    ValidationError(
                        line,
                        f"operation must be one of registry operations for {repo}/{surface}: {allowed}",
                    )
                )
            for field in entry.get("required_domain_fields", []):
                if field not in domain:
                    errors.append(ValidationError(line, f"domain missing required field: {field}"))

    return errors


def validate_records(
    records: list[dict[str, Any]],
    *,
    registry: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None,
) -> list[ValidationError]:
    """Validate loaded records."""
    errors: list[ValidationError] = []
    for index, record in enumerate(records, 1):
        line = int(getattr(record, "source_line", index))
        errors.extend(validate_record(record, line=line, registry=registry, schema=schema))
    return errors


def summarize_fleet_records(
    records: list[dict[str, Any]],
    *,
    registry: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Summarize record coverage against the registry."""
    now = now or datetime.now(UTC)
    by_repo_surface: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (str(record.get("repo", "")), str(record.get("surface", "")))
        by_repo_surface.setdefault(key, []).append(record)

    registry_entries = registry_surfaces(registry)
    statuses: dict[str, int] = Counter()
    rows: list[dict[str, Any]] = []

    stale_after_hours = int(registry.get("stale_after_hours", 168))
    for key, entry in sorted(registry_entries.items()):
        repo, surface = key
        matching = by_repo_surface.get(key, [])
        evidence_mode = str(entry.get("evidence_mode") or "artifact")
        if evidence_mode == "langsmith-direct":
            validation_errors: list[ValidationError] = []
            latest_recorded_at = None
            status = "direct"
            reason = (
                "Evidence is ingested from the central LangSmith project; "
                "a repo-local fleet artifact is not required or validated here."
            )
        else:
            validation_errors = validate_records(matching, registry=registry) if matching else []
            latest_recorded_at = _latest_recorded_at(matching)
            reason = None
            if not matching:
                status = "missing"
            elif validation_errors:
                status = "invalid"
            elif (
                latest_recorded_at
                and (now - latest_recorded_at).total_seconds() > stale_after_hours * 3600
            ):
                status = "stale"
            else:
                status = "valid"
        statuses[status] += 1
        rows.append(
            {
                "repo": repo,
                "surface": surface,
                "issue": entry.get("issue"),
                "artifact_name": entry.get("artifact_name"),
                "evidence_mode": evidence_mode,
                "rollout_status": entry.get("rollout_status"),
                "record_count": len(matching),
                "latest_recorded_at": (
                    latest_recorded_at.isoformat() if latest_recorded_at else None
                ),
                "status": status,
                "first_error": validation_errors[0].message if validation_errors else None,
                "reason": reason,
            }
        )

    allowlist = registry.get("_allowlist") or {}
    allowlist_entries = allowlist.get("repos", []) if isinstance(allowlist, dict) else []
    for entry in sorted(allowlist_entries, key=lambda item: str(item.get("repo", ""))):
        statuses["not-applicable"] += 1
        rows.append(
            {
                "repo": entry["repo"],
                "surface": "",
                "issue": None,
                "artifact_name": None,
                "evidence_mode": "none",
                "rollout_status": "not-applicable",
                "record_count": 0,
                "latest_recorded_at": None,
                "status": "not-applicable",
                "first_error": None,
                "reason": entry["reason"],
                "registry_activation_condition": entry["registry_activation_condition"],
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "total_registry_entries": len(registry_entries),
        "total_allowlisted_repos": len(allowlist_entries),
        "status_counts": dict(sorted(statuses.items())),
        "rows": rows,
    }


def _latest_recorded_at(records: list[dict[str, Any]]) -> datetime | None:
    latest: datetime | None = None
    for record in records:
        raw_value = record.get("recorded_at")
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        try:
            value = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        if latest is None or value > latest:
            latest = value
    return latest


def format_fleet_summary(summary: dict[str, Any]) -> str:
    """Render a dashboard-friendly markdown summary."""
    lines = ["# LangSmith Fleet Artifact Status", ""]
    counts = summary.get("status_counts", {})
    lines.append(f"- Registry entries: {summary.get('total_registry_entries', 0)}")
    lines.append(f"- Allowlisted repositories: {summary.get('total_allowlisted_repos', 0)}")
    lines.append(f"- Valid: {counts.get('valid', 0)}")
    lines.append(f"- Missing: {counts.get('missing', 0)}")
    lines.append(f"- Stale: {counts.get('stale', 0)}")
    lines.append(f"- Invalid: {counts.get('invalid', 0)}")
    lines.append(f"- Direct evidence: {counts.get('direct', 0)}")
    lines.append(f"- Not applicable: {counts.get('not-applicable', 0)}")
    lines.append("")
    lines.append("| Repo | Surface | Evidence | Issue | Status | Records | Latest | Detail |")
    lines.append("|------|---------|----------|-------|--------|---------|--------|--------|")
    for row in summary.get("rows", []):
        lines.append(
            "| {repo} | {surface} | {evidence} | {issue} | {status} | {record_count} | {latest} | {detail} |".format(
                repo=row["repo"],
                surface=row["surface"],
                evidence=row.get("evidence_mode") or "",
                issue=row.get("issue") or "",
                status=row["status"],
                record_count=row["record_count"],
                latest=row.get("latest_recorded_at") or "",
                detail=row.get("first_error") or row.get("reason") or "",
            )
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate LangSmith fleet records")
    parser.add_argument("records", type=Path, help="NDJSON file with langsmith-fleet/v1 records")
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("config/langsmith_fleet_registry.json"),
        help="Fleet registry JSON path",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Emit registry coverage summary instead of validation text",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format for --summary",
    )
    args = parser.parse_args()

    records, parse_errors = load_ndjson(args.records)
    registry = load_registry(args.registry)
    schema = load_record_schema()
    validation_errors = parse_errors + validate_records(records, registry=registry, schema=schema)

    if validation_errors and not args.summary:
        for error in validation_errors:
            print(f"line {error.line}: {error.message}", file=sys.stderr)
        raise SystemExit(1)

    if args.summary:
        summary = summarize_fleet_records(records, registry=registry)
        if args.format == "markdown":
            print(format_fleet_summary(summary), end="")
        else:
            print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"Validated {len(records)} {SCHEMA_VERSION} record(s)")


if __name__ == "__main__":
    main()
