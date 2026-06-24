#!/usr/bin/env python3
"""Ensure reusable CI has a LangSmith fleet artifact to upload.

The normal producer remains repo-local instrumentation. This helper only writes
an explicit CI fallback row when an implemented registry repo produced no
``artifacts/langsmith/langsmith-fleet.ndjson`` file, so artifact distribution can
still be diagnosed from failed or partial CI runs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from datetime import UTC
except ImportError:  # pragma: no cover - Python < 3.11 compatibility
    from datetime import timezone

    UTC = timezone.utc  # noqa: UP017 - fallback for Python < 3.11

SCHEMA_VERSION = "langsmith-fleet/v1"
ARTIFACT_NAME = "langsmith-fleet.ndjson"
FALLBACK_ERROR_CATEGORY = "ci_fleet_artifact_missing"
ELIGIBLE_ROLLOUT_STATUSES = {"implemented", "implemented-followup-open"}


def load_registry(path: Path) -> dict[str, Any]:
    """Load the fleet registry JSON."""
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("registry must be a JSON object")
    repos = data.get("repos")
    if not isinstance(repos, list):
        raise ValueError("registry repos must be a list")
    return data


def _artifact_has_records(path: Path) -> bool:
    """Return whether an artifact file already contains at least one row."""
    if not path.exists() or not path.is_file():
        return False
    try:
        return any(line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


def _has_langsmith_artifact_contract(entry: dict[str, Any]) -> bool:
    """Return whether a registry entry has the fields needed for fallback rows."""
    operations = entry.get("operations")
    required_domain_fields = entry.get("required_domain_fields")
    return (
        str(entry.get("artifact_name", "")).strip() == ARTIFACT_NAME
        and bool(str(entry.get("surface", "")).strip())
        and bool(str(entry.get("issue", "")).strip())
        and isinstance(operations, list)
        and any(str(operation).strip() for operation in operations)
        and isinstance(required_domain_fields, list)
        and all(str(field).strip() for field in required_domain_fields)
    )


def _entry_for_repo(
    registry: dict[str, Any], repository: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Find one unambiguous fallback-eligible LangSmith registry entry."""
    normalized = repository.strip()
    repo_entries = [
        entry
        for entry in registry.get("repos", [])
        if isinstance(entry, dict) and str(entry.get("repo", "")).strip() == normalized
    ]
    if not repo_entries:
        return None, "repository_not_in_registry"
    contract_entries = [entry for entry in repo_entries if _has_langsmith_artifact_contract(entry)]
    if not contract_entries:
        return None, "repository_missing_langsmith_artifact_contract"
    eligible_entries = [
        entry
        for entry in contract_entries
        if str(entry.get("rollout_status") or "").strip() in ELIGIBLE_ROLLOUT_STATUSES
    ]
    if len(eligible_entries) == 1:
        return eligible_entries[0], None
    if len(eligible_entries) > 1:
        return None, "repository_langsmith_artifact_contract_ambiguous"
    if len(contract_entries) == 1:
        return contract_entries[0], None
    return None, "repository_langsmith_artifact_contract_ambiguous"


def _domain_fallback_value(field: str, *, now: datetime) -> Any:
    """Build a schema-friendly placeholder for a required domain field."""
    lowered = field.lower()
    if lowered in {"as_of_date"} or lowered.endswith("_date"):
        return now.date().isoformat()
    if lowered in {"seed", "row_count", "tool_call_count"} or lowered.endswith("_count"):
        return 0
    if lowered.endswith("_score") or lowered.endswith("_delta"):
        return 0
    if lowered.endswith("_status") or lowered in {"fallback_state", "result"}:
        return "ci_fallback_no_records"
    if lowered.endswith("_hash"):
        return "ref:ci-fallback-no-records"
    if lowered.endswith("_id"):
        return "ci-fallback-no-records"
    return "ci-fallback-no-records"


def build_fallback_record(
    entry: dict[str, Any],
    *,
    repository: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    job: str,
    python_version: str,
    sha: str,
    event_name: str,
    now: datetime,
) -> dict[str, Any]:
    """Build one registry-valid row that identifies missing CI producer output."""
    operations = entry.get("operations") if isinstance(entry.get("operations"), list) else []
    operation = str(operations[0]).strip() if operations else "ci-fallback"
    required_domain_fields = (
        entry.get("required_domain_fields")
        if isinstance(entry.get("required_domain_fields"), list)
        else []
    )
    domain = {
        str(field): _domain_fallback_value(str(field), now=now)
        for field in required_domain_fields
        if str(field).strip()
    }
    domain.update(
        {
            "workflow": workflow or "unknown",
            "job": job or "unknown",
            "python_version": python_version or "unknown",
            "run_attempt": run_attempt or "1",
            "event_name": event_name or "unknown",
            "fallback_reason": FALLBACK_ERROR_CATEGORY,
            "result": "no_ci_fleet_records",
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "repo": repository,
        "surface": str(entry.get("surface") or "unknown"),
        "operation": operation,
        "run_id": f"github-actions:{run_id or 'unknown'}:{run_attempt or '1'}:langsmith-fleet",
        "status": "error",
        "github_issue": str(entry.get("issue") or ""),
        "recorded_at": now.isoformat().replace("+00:00", "Z"),
        "input_hash": f"ref:{sha}" if sha else "ref:unknown",
        "output_hash": "artifact:langsmith-fleet-fallback",
        "artifact_ref": f"artifact:{ARTIFACT_NAME}",
        "error_category": FALLBACK_ERROR_CATEGORY,
        "domain": domain,
    }


def ensure_artifact(
    *,
    artifact_path: Path,
    registry_path: Path,
    repository: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    job: str,
    python_version: str,
    sha: str,
    event_name: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create a fallback artifact if an eligible repo produced no records."""
    if _artifact_has_records(artifact_path):
        return {
            "status": "existing",
            "artifact_path": str(artifact_path),
            "repository": repository,
        }

    registry = load_registry(registry_path)
    entry, skipped_reason = _entry_for_repo(registry, repository)
    if entry is None:
        return {
            "status": "skipped",
            "reason": skipped_reason or "repository_not_in_registry",
            "artifact_path": str(artifact_path),
            "repository": repository,
        }

    rollout_status = str(entry.get("rollout_status") or "").strip()
    if rollout_status not in ELIGIBLE_ROLLOUT_STATUSES:
        return {
            "status": "skipped",
            "reason": f"rollout_status_{rollout_status or 'missing'}",
            "artifact_path": str(artifact_path),
            "repository": repository,
        }

    timestamp = now or datetime.now(UTC)
    record = build_fallback_record(
        entry,
        repository=repository,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow=workflow,
        job=job,
        python_version=python_version,
        sha=sha,
        event_name=event_name,
        now=timestamp,
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "created",
        "reason": FALLBACK_ERROR_CATEGORY,
        "artifact_path": str(artifact_path),
        "repository": repository,
        "surface": record["surface"],
        "operation": record["operation"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments and environment defaults."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-path",
        type=Path,
        default=None,
        help="Target langsmith-fleet.ndjson path.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(os.environ.get("PROJECT_ROOT") or "."),
        help="Project root used when --artifact-path is omitted.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("config/langsmith_fleet_registry.json"),
        help="Workflows LangSmith fleet registry path.",
    )
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    parser.add_argument("--workflow", default=os.environ.get("GITHUB_WORKFLOW", ""))
    parser.add_argument("--job", default=os.environ.get("GITHUB_JOB", ""))
    parser.add_argument("--python-version", default=os.environ.get("PYTHON_VERSION", ""))
    parser.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--event-name", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point used by reusable CI."""
    args = parse_args(argv)
    artifact_path = args.artifact_path or (
        args.project_root / "artifacts" / "langsmith" / ARTIFACT_NAME
    )
    try:
        result = ensure_artifact(
            artifact_path=artifact_path,
            registry_path=args.registry,
            repository=args.repository,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            workflow=args.workflow,
            job=args.job,
            python_version=args.python_version,
            sha=args.sha,
            event_name=args.event_name,
        )
    except Exception as exc:  # pragma: no cover - defensive CI fail-open path
        result = {
            "status": "skipped",
            "reason": "ensure_failed",
            "error": str(exc),
            "artifact_path": str(artifact_path),
            "repository": args.repository,
        }
        print(
            f"::warning::LangSmith fleet fallback artifact ensure failed: {exc}",
            file=sys.stderr,
        )
    print(json.dumps(result, sort_keys=True))
    if result.get("status") == "created":
        print(
            "::notice::Created LangSmith fleet fallback artifact because no repo-produced "
            f"records were present: {artifact_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
