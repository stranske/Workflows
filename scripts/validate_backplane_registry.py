#!/usr/bin/env python3
"""Validate the Workflows-owned research-backplane participant registry."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ISSUE_REF_RE = re.compile(r"^stranske/[A-Za-z0-9_.-]+#[1-9][0-9]*$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
RUN_JOB_URL_RE = re.compile(
    r"^https://github\.com/stranske/[A-Za-z0-9_.-]+/actions/runs/[1-9][0-9]*/job/[1-9][0-9]*$"
)
ISSUE_COMMENT_URL_RE = re.compile(
    r"^https://github\.com/stranske/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*#issuecomment-[1-9][0-9]*$"
)
STATUSES = {"planned", "emitting", "conformant", "candidate", "none"}
REFERENCE_STATES = {"missing", "invalid", "stale", "valid", "not-applicable"}
MAX_STALE_AFTER_HOURS = 24 * 365


# Findings default to "error" severity (structural defects that must block
# everywhere). "stale" severity marks an OPERATIONAL freshness lapse (a reference
# run aged past the freshness window) — real signal, surfaced by the dedicated
# backplane lane (health-78) and the CLI, but it must not fail the general
# structural validity suite, or the required `summary` check would go red for every
# unrelated PR the moment the window lapses.
ERROR_SEVERITY = "error"
STALE_SEVERITY = "stale"


@dataclass(frozen=True)
class Finding:
    path: str
    message: str
    severity: str = ERROR_SEVERITY


def blocking_findings(findings: list[Finding]) -> list[Finding]:
    """Structural findings that must block validation everywhere.

    Operational freshness findings (``severity == STALE_SEVERITY``) are excluded:
    they are surfaced (CLI / health-78) but do not gate unrelated work.
    """

    return [finding for finding in findings if finding.severity != STALE_SEVERITY]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_strings(value: Any, path: str = "") -> list[Finding]:
    findings: list[Finding] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            findings.extend(_walk_strings(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_walk_strings(child, f"{path}[{index}]"))
    elif isinstance(value, str) and "TBD" in value:
        findings.append(Finding(path, "placeholder TBD reference is not allowed"))
    return findings


def _is_issue_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(ISSUE_REF_RE.fullmatch(value))


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _parse_aware_datetime(value: Any) -> datetime | None:
    parsed = _parse_datetime(value)
    if parsed is None or parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _validate_deferred_issue(entry: dict[str, Any], prefix: str) -> list[Finding]:
    findings: list[Finding] = []
    deferred = entry.get("issue_deferred")
    if not isinstance(deferred, dict):
        return [
            Finding(f"{prefix}.issue", "issue must be a real issue ref or carry issue_deferred")
        ]
    reason = deferred.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        findings.append(Finding(f"{prefix}.issue_deferred.reason", "deferred issue needs a reason"))
    expires_at = _parse_aware_datetime(deferred.get("expires_at"))
    if expires_at is None:
        findings.append(
            Finding(
                f"{prefix}.issue_deferred.expires_at",
                "deferred issue needs timezone-aware ISO timestamp",
            )
        )
    elif expires_at <= datetime.now(UTC):
        findings.append(Finding(f"{prefix}.issue_deferred.expires_at", "deferred issue expired"))
    return findings


def _validate_reference_evidence(
    entry: dict[str, Any], prefix: str, stale_after_hours: int
) -> list[Finding]:
    evidence = entry.get("reference_run_evidence")
    if not isinstance(evidence, dict):
        return [Finding(f"{prefix}.reference_run_evidence", "conformant entry needs evidence")]

    findings: list[Finding] = []
    required_issue_refs = (
        "source_issue",
        "producer_pr",
        "verifier_followup_issue",
        "verifier_followup_pr",
    )
    for key in required_issue_refs:
        if not _is_issue_ref(evidence.get(key)):
            findings.append(
                Finding(f"{prefix}.reference_run_evidence.{key}", "must be issue/PR ref")
            )
    if _is_issue_ref(entry.get("issue")) and evidence.get("source_issue") != entry["issue"]:
        findings.append(
            Finding(
                f"{prefix}.reference_run_evidence.source_issue",
                "must match participant issue",
            )
        )

    run_url_keys = ("emit_reference_run_url", "conformance_run_url")
    for key in run_url_keys:
        if not isinstance(evidence.get(key), str) or not RUN_JOB_URL_RE.fullmatch(evidence[key]):
            findings.append(
                Finding(f"{prefix}.reference_run_evidence.{key}", "must be GitHub run job URL")
            )

    if not isinstance(
        evidence.get("disposition_comment"), str
    ) or not ISSUE_COMMENT_URL_RE.fullmatch(evidence["disposition_comment"]):
        findings.append(
            Finding(
                f"{prefix}.reference_run_evidence.disposition_comment",
                "must be GitHub issue comment URL",
            )
        )

    for key in ("reference_run_sha256", "manifest_artifact_sha256", "conformance_report_sha256"):
        if not isinstance(evidence.get(key), str) or not SHA256_RE.fullmatch(evidence[key]):
            findings.append(Finding(f"{prefix}.reference_run_evidence.{key}", "must be sha256"))

    generated_at = _parse_aware_datetime(evidence.get("generated_at"))
    now = datetime.now(UTC)
    if generated_at is None:
        findings.append(
            Finding(
                f"{prefix}.reference_run_evidence.generated_at",
                "must be timezone-aware ISO time",
            )
        )
    elif generated_at > now:
        findings.append(
            Finding(f"{prefix}.reference_run_evidence.generated_at", "must not be in the future")
        )
    elif now - generated_at > timedelta(hours=stale_after_hours):
        findings.append(
            Finding(
                f"{prefix}.reference_run_evidence.generated_at",
                "reference run is stale",
                severity=STALE_SEVERITY,
            )
        )
    run_id = evidence.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        findings.append(Finding(f"{prefix}.reference_run_evidence.run_id", "must be populated"))
    return findings


def _validate_lifecycle_history(entry: dict[str, Any], prefix: str) -> list[Finding]:
    history = entry.get("lifecycle_history")
    if not isinstance(history, list):
        return [Finding(f"{prefix}.lifecycle_history", "conformant entry needs lifecycle history")]

    findings: list[Finding] = []
    expected = ["planned", "emitting", "conformant"]
    actual: list[str] = []
    previous_at: datetime | None = None
    for index, item in enumerate(history):
        item_prefix = f"{prefix}.lifecycle_history[{index}]"
        if not isinstance(item, dict):
            findings.append(Finding(item_prefix, "lifecycle history entry must be an object"))
            continue

        status = item.get("status")
        if isinstance(status, str):
            actual.append(status)
        else:
            findings.append(Finding(f"{item_prefix}.status", "lifecycle status must be populated"))

        at = _parse_aware_datetime(item.get("at"))
        if at is None:
            findings.append(Finding(f"{item_prefix}.at", "must be timezone-aware ISO time"))
        elif previous_at is not None and at < previous_at:
            findings.append(Finding(f"{item_prefix}.at", "lifecycle timestamps must be monotonic"))
        elif at is not None:
            previous_at = at

        evidence = item.get("evidence")
        evidence_ok = _is_issue_ref(evidence) or (
            isinstance(evidence, str) and RUN_JOB_URL_RE.fullmatch(evidence)
        )
        if not evidence_ok:
            findings.append(
                Finding(f"{item_prefix}.evidence", "must be issue ref or GitHub run job URL")
            )

    if actual != expected:
        findings.append(
            Finding(
                f"{prefix}.lifecycle_history", "must progress planned -> emitting -> conformant"
            )
        )
    return findings


def validate_registry(registry: Any) -> list[Finding]:
    findings = _walk_strings(registry)

    if not isinstance(registry, dict):
        return [Finding("registry", "registry must be an object")]

    parent_issue = registry.get("parent_issue")
    if not _is_issue_ref(parent_issue):
        findings.append(Finding("parent_issue", "parent_issue must be a real issue ref"))

    stale_after_hours = registry.get("stale_after_hours", 168)
    if isinstance(stale_after_hours, bool) or not isinstance(stale_after_hours, int):
        findings.append(Finding("stale_after_hours", "stale_after_hours must be an integer"))
        stale_after_hours = 168
    elif stale_after_hours <= 0:
        findings.append(Finding("stale_after_hours", "stale_after_hours must be positive"))
        stale_after_hours = 168
    elif stale_after_hours > MAX_STALE_AFTER_HOURS:
        findings.append(
            Finding(
                "stale_after_hours",
                f"stale_after_hours must be <= {MAX_STALE_AFTER_HOURS}",
            )
        )
        stale_after_hours = 168

    participants = registry.get("participants")
    if not isinstance(participants, list) or not participants:
        findings.append(Finding("participants", "participants must be a non-empty list"))
        return findings

    seen: set[str] = set()
    for index, entry in enumerate(participants):
        prefix = f"participants[{index}]"
        if not isinstance(entry, dict):
            findings.append(Finding(prefix, "participant entry must be an object"))
            continue
        repo = entry.get("repo")
        if not isinstance(repo, str) or not repo.startswith("stranske/"):
            findings.append(Finding(f"{prefix}.repo", "repo must be stranske/<repo>"))
        elif repo in seen:
            findings.append(Finding(f"{prefix}.repo", "duplicate participant repo"))
        else:
            seen.add(repo)

        if entry.get("parent_issue") != parent_issue:
            findings.append(Finding(f"{prefix}.parent_issue", "must match registry parent_issue"))

        status = entry.get("status")
        if status not in STATUSES:
            findings.append(Finding(f"{prefix}.status", "unknown lifecycle status"))

        reference_state = entry.get("reference_state")
        if reference_state not in REFERENCE_STATES:
            findings.append(Finding(f"{prefix}.reference_state", "unknown reference_state"))

        issue = entry.get("issue")
        if issue is None:
            findings.extend(_validate_deferred_issue(entry, prefix))
        elif not _is_issue_ref(issue):
            findings.append(Finding(f"{prefix}.issue", "issue must be a real issue ref"))

        if status == "conformant":
            if not _is_issue_ref(issue):
                findings.append(
                    Finding(f"{prefix}.issue", "conformant entry needs a real issue ref")
                )
            if reference_state != "valid":
                findings.append(
                    Finding(f"{prefix}.reference_state", "conformant entries must be valid")
                )
            findings.extend(_validate_lifecycle_history(entry, prefix))
            findings.extend(_validate_reference_evidence(entry, prefix, stale_after_hours))
        elif reference_state == "valid":
            findings.append(
                Finding(f"{prefix}.reference_state", "valid evidence requires conformant status")
            )

    return findings


def _reference_rows(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entry in registry.get("participants", []):
        if not isinstance(entry, dict):
            rows.append(
                {
                    "repo": None,
                    "lifecycle_status": None,
                    "reference_state": None,
                    "issue": None,
                    "deferred_until": None,
                    "run_id": None,
                    "generated_at": None,
                    "conformance_run_url": None,
                }
            )
            continue
        evidence = entry.get("reference_run_evidence") or {}
        rows.append(
            {
                "repo": entry.get("repo"),
                "lifecycle_status": entry.get("status"),
                "reference_state": entry.get("reference_state"),
                "issue": entry.get("issue"),
                "deferred_until": (entry.get("issue_deferred") or {}).get("expires_at"),
                "run_id": evidence.get("run_id"),
                "generated_at": evidence.get("generated_at"),
                "conformance_run_url": evidence.get("conformance_run_url"),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "registry",
        type=Path,
        nargs="?",
        default=Path("config/backplane_participants.json"),
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable report")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Compatibility flag; validation is always strict.",
    )
    args = parser.parse_args(argv)

    registry = _load_json(args.registry)
    findings = validate_registry(registry)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "ok": not findings,
        "finding_count": len(findings),
        "findings": [{"path": f.path, "message": f.message} for f in findings],
        "participants": _reference_rows(registry),
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif findings:
        print("Backplane registry validation failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding.path}: {finding.message}", file=sys.stderr)
    else:
        print("Backplane registry validation passed.")

    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
