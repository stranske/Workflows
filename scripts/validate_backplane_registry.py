#!/usr/bin/env python3
"""Validate the Workflows-owned research-backplane participant registry."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ISSUE_REF_RE = re.compile(r"^stranske/[A-Za-z0-9_.-]+#[1-9][0-9]*$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
URL_RE = re.compile(r"^https://github.com/stranske/[A-Za-z0-9_.-]+/(actions/runs|issues|pull)/")
STATUSES = {"planned", "emitting", "conformant", "candidate", "none"}
REFERENCE_STATES = {"missing", "invalid", "stale", "valid", "not-applicable"}


@dataclass(frozen=True)
class Finding:
    path: str
    message: str


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


def _validate_deferred_issue(entry: dict[str, Any], prefix: str) -> list[Finding]:
    findings: list[Finding] = []
    deferred = entry.get("issue_deferred")
    if not isinstance(deferred, dict):
        return [
            Finding(f"{prefix}.issue", "issue must be a real issue ref or carry issue_deferred")
        ]
    if not deferred.get("reason"):
        findings.append(Finding(f"{prefix}.issue_deferred.reason", "deferred issue needs a reason"))
    if _parse_datetime(deferred.get("expires_at")) is None:
        findings.append(
            Finding(f"{prefix}.issue_deferred.expires_at", "deferred issue needs ISO timestamp")
        )
    return findings


def _validate_reference_evidence(entry: dict[str, Any], prefix: str) -> list[Finding]:
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

    for key in ("emit_reference_run_url", "conformance_run_url", "disposition_comment"):
        if not isinstance(evidence.get(key), str) or not URL_RE.match(evidence[key]):
            findings.append(Finding(f"{prefix}.reference_run_evidence.{key}", "must be GitHub URL"))

    for key in ("reference_run_sha256", "manifest_artifact_sha256", "conformance_report_sha256"):
        if not isinstance(evidence.get(key), str) or not SHA256_RE.fullmatch(evidence[key]):
            findings.append(Finding(f"{prefix}.reference_run_evidence.{key}", "must be sha256"))

    if _parse_datetime(evidence.get("generated_at")) is None:
        findings.append(
            Finding(f"{prefix}.reference_run_evidence.generated_at", "must be ISO time")
        )
    if not evidence.get("run_id"):
        findings.append(Finding(f"{prefix}.reference_run_evidence.run_id", "must be populated"))
    return findings


def validate_registry(registry: dict[str, Any]) -> list[Finding]:
    findings = _walk_strings(registry)

    parent_issue = registry.get("parent_issue")
    if not _is_issue_ref(parent_issue):
        findings.append(Finding("parent_issue", "parent_issue must be a real issue ref"))

    participants = registry.get("participants")
    if not isinstance(participants, list) or not participants:
        findings.append(Finding("participants", "participants must be a non-empty list"))
        return findings

    seen: set[str] = set()
    for index, entry in enumerate(participants):
        prefix = f"participants[{index}]"
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
            if reference_state != "valid":
                findings.append(
                    Finding(f"{prefix}.reference_state", "conformant entries must be valid")
                )
            findings.extend(_validate_reference_evidence(entry, prefix))
        elif reference_state == "valid":
            findings.append(
                Finding(f"{prefix}.reference_state", "valid evidence requires conformant status")
            )

    return findings


def _reference_rows(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entry in registry.get("participants", []):
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
