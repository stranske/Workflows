#!/usr/bin/env python3
"""Validate the Workflows-owned research-backplane participant registry."""

from __future__ import annotations

import argparse
import difflib
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
EMITTED_EVIDENCE_POLICIES = {"manifest-evidence-closure/v1"}
REFERENCE_STATES = {"missing", "invalid", "stale", "valid", "not-applicable"}
MAX_STALE_AFTER_HOURS = 24 * 365


# Findings default to "error" severity (structural defects that must block
# everywhere). "stale" severity marks an operational freshness lapse, such as an
# expired deferral or a stale reference run, surfaced by the dedicated
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
    try:
        expires_at = _parse_aware_datetime(deferred.get("expires_at"))
    except OverflowError:
        # A timezone offset can put the expiry outside the supported UTC range.
        expires_at = None
    if expires_at is None:
        findings.append(
            Finding(
                f"{prefix}.issue_deferred.expires_at",
                "deferred issue needs timezone-aware ISO timestamp",
            )
        )
    elif expires_at <= datetime.now(UTC):
        findings.append(
            Finding(
                f"{prefix}.issue_deferred.expires_at",
                "deferred issue expired",
                severity=STALE_SEVERITY,
            )
        )
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

        policy = entry.get("emitted_evidence_policy")
        if policy is not None:
            if not isinstance(policy, str) or policy not in EMITTED_EVIDENCE_POLICIES:
                findings.append(
                    Finding(f"{prefix}.emitted_evidence_policy", "unknown emitted evidence policy")
                )
            if entry.get("role") not in {"producer", "bridge"}:
                findings.append(
                    Finding(f"{prefix}.emitted_evidence_policy", "requires producer or bridge role")
                )
            if status not in {"emitting", "conformant"}:
                findings.append(
                    Finding(
                        f"{prefix}.emitted_evidence_policy",
                        "requires emitting or conformant status",
                    )
                )

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


def _format_issue_state(row: dict[str, Any]) -> str:
    issue = row.get("issue")
    if issue:
        return f"`{issue}`"
    deferred_until = row.get("deferred_until")
    if deferred_until:
        date_part = str(deferred_until).split("T", 1)[0]
        return f"deferred until {date_part}"
    return "none"


def _pension_reference_evidence(registry: dict[str, Any]) -> dict[str, Any] | None:
    for entry in registry.get("participants", []):
        if isinstance(entry, dict) and entry.get("repo") == "stranske/Pension-Data":
            evidence = entry.get("reference_run_evidence")
            if isinstance(evidence, dict):
                return evidence
    return None


def render_status_markdown(registry: dict[str, Any]) -> str:
    """Render the human-readable backplane status report from registry JSON."""
    parent_issue = registry.get("parent_issue", "unknown")
    rows = _reference_rows(registry)
    lines = [
        "# Backplane Registry Status",
        "",
        f"Generated from `config/backplane_participants.json` for {parent_issue}.",
        "",
        "Regenerate: `python scripts/validate_backplane_registry.py "
        "--write-status docs/reports/backplane_registry_status.md`",
        "",
        "| Repo | Lifecycle status | Reference state | Issue state |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {repo} | {lifecycle} | {reference} | {issue_state} |".format(
                repo=row.get("repo"),
                lifecycle=row.get("lifecycle_status"),
                reference=row.get("reference_state"),
                issue_state=_format_issue_state(row),
            )
        )

    if not any(row.get("deferred_until") for row in rows):
        lines.extend(["", "Deferrals: none deferred."])

    evidence = _pension_reference_evidence(registry)
    if evidence:
        lines.extend(
            [
                "",
                "Pension-Data reference evidence:",
                "",
                f"- Source issue: `{evidence.get('source_issue')}`",
                f"- Producer PR: `{evidence.get('producer_pr')}`",
                (
                    "- Verifier follow-up: "
                    f"`{evidence.get('verifier_followup_issue')}` / "
                    f"`{evidence.get('verifier_followup_pr')}`"
                ),
                f"- Reference run: `{evidence.get('run_id')}`",
                f"- Emit-reference-run job: `{evidence.get('emit_reference_run_url')}`",
                f"- Backplane conformance job: `{evidence.get('conformance_run_url')}`",
                f"- Run artifact SHA256: `{evidence.get('reference_run_sha256')}`",
                f"- Manifest artifact SHA256: `{evidence.get('manifest_artifact_sha256')}`",
            ]
        )

    return "\n".join(lines) + "\n"


# --- Freshness tracker (health-78 scheduled/dispatch publisher) -------------
#
# The tracker turns the warning-only freshness report into one marker-
# deduplicated issue. The publisher finds the issue by this body marker, never by
# title search, so a retitled or hand-edited tracker cannot spawn a duplicate.
TRACKER_MARKER = "<!-- backplane-freshness-tracker:v1 -->"
TRACKER_TITLE = "Backplane registry freshness: stale findings need action"
TRACKER_RUNS_START = "<!-- backplane-freshness-tracker:runs -->"
TRACKER_RUNS_END = "<!-- /backplane-freshness-tracker:runs -->"
TRACKER_RUN_HISTORY_LIMIT = 10
TRACKER_DECISIONS = ("create", "update", "reopen", "close", "refuse")

DEFERRAL_FINDING_SUFFIX = ".issue_deferred.expires_at"
REFERENCE_FINDING_SUFFIX = ".reference_run_evidence.generated_at"
_PARTICIPANT_PATH_RE = re.compile(r"^participants\[(\d+)\]")
_RUN_URL_LINE_RE = re.compile(r"^- (https://\S+)")
_REQUIRED_COUNT_KEYS = ("finding_count", "blocking_count", "stale_count")

try:
    from scripts.list_registered_consumer_repos import is_owner_excluded
except ModuleNotFoundError:  # pragma: no cover - script executed from scripts/
    from list_registered_consumer_repos import is_owner_excluded  # type: ignore[no-redef]


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def tracker_report_problem(report: Any) -> str | None:
    """Return why ``report`` cannot drive the tracker, or None when it is complete.

    A complete report carries every count, a findings list whose per-severity
    tallies match those counts, and a participants list. Anything else (missing
    file, truncated JSON, a hand-trimmed dict) is refused rather than read as
    "zero findings", so an unreadable report can never close the tracker.
    """

    if report is None:
        return "registry-status report is missing or unreadable"
    if not isinstance(report, dict):
        return "registry-status report is not a JSON object"
    for key in _REQUIRED_COUNT_KEYS:
        if key not in report:
            return f"registry-status report is missing {key}"
        if not _is_count(report[key]):
            return f"registry-status report {key} is not a non-negative integer"
    findings = report.get("findings")
    if not isinstance(findings, list):
        return "registry-status report is missing findings[]"
    if not isinstance(report.get("participants"), list):
        return "registry-status report is missing participants[]"
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict) or not all(
            isinstance(finding.get(key), str) for key in ("path", "message", "severity")
        ):
            return f"registry-status report findings[{index}] is malformed"
    stale = sum(1 for f in findings if f["severity"] == STALE_SEVERITY)
    blocking = len(findings) - stale
    if len(findings) != report["finding_count"]:
        return "registry-status report finding_count does not match findings[]"
    if stale != report["stale_count"]:
        return "registry-status report stale_count does not match findings[]"
    if blocking != report["blocking_count"]:
        return "registry-status report blocking_count does not match findings[]"
    return None


def load_tracker_report(path: Path) -> dict[str, Any] | None:
    """Read a registry-status report; None when the file is missing or not JSON."""

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _finding_repo(report: dict[str, Any], path: str) -> str | None:
    match = _PARTICIPANT_PATH_RE.match(path)
    if match is None:
        return None
    index = int(match.group(1))
    participants = report.get("participants") or []
    if index >= len(participants) or not isinstance(participants[index], dict):
        return None
    repo = participants[index].get("repo")
    return repo if isinstance(repo, str) else None


def tracker_counts(report: dict[str, Any]) -> dict[str, Any]:
    """Classify a complete report's stale findings after owner repo exclusions.

    ``drainable_count`` is the number of stale findings with a named drain path:
    an administrative deferral decision or a fresh validated reference run.
    ``unclassified`` stale findings have no known drain and are reported as such.
    """

    deferrals: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    unclassified: list[dict[str, Any]] = []
    excluded = 0
    blocking = 0
    for finding in report["findings"]:
        repo = _finding_repo(report, finding["path"])
        if repo is not None and is_owner_excluded(repo):
            excluded += 1
            continue
        if finding["severity"] != STALE_SEVERITY:
            blocking += 1
            continue
        row = {**finding, "repo": repo}
        if finding["path"].endswith(DEFERRAL_FINDING_SUFFIX):
            deferrals.append(row)
        elif finding["path"].endswith(REFERENCE_FINDING_SUFFIX):
            references.append(row)
        else:
            unclassified.append(row)
    stale_count = len(deferrals) + len(references) + len(unclassified)
    return {
        "blocking_count": blocking,
        "stale_count": stale_count,
        "drainable_count": len(deferrals) + len(references),
        "owner_excluded_count": excluded,
        "deferrals": deferrals,
        "references": references,
        "unclassified": unclassified,
    }


def tracker_decision(report: Any, existing_issue: dict[str, Any] | None) -> str:
    """Decide what the publisher does with the marker tracker issue.

    ``existing_issue`` is the issue found by :data:`TRACKER_MARKER` (``None``
    when there is none), with ``state`` ``"open"`` or ``"closed"``. Returns one
    of :data:`TRACKER_DECISIONS`. ``close`` is only returned for a complete,
    non-blocking report with zero stale findings; the publisher treats ``close``
    with no open tracker as "already drained, nothing to do".
    """

    if tracker_report_problem(report) is not None:
        return "refuse"
    counts = tracker_counts(report)
    if counts["blocking_count"] > 0:
        return "refuse"
    if counts["stale_count"] == 0:
        return "close"
    if existing_issue is None:
        return "create"
    state = str(existing_issue.get("state", "")).lower()
    if state == "closed":
        return "reopen"
    return "update"


def tracker_runs_from_body(body: str | None) -> list[str]:
    """Return the run URLs recorded in an existing tracker body, oldest first."""

    if not body or TRACKER_RUNS_START not in body or TRACKER_RUNS_END not in body:
        return []
    section = body.split(TRACKER_RUNS_START, 1)[1].split(TRACKER_RUNS_END, 1)[0]
    runs = []
    for line in section.splitlines():
        match = _RUN_URL_LINE_RE.match(line.strip())
        if match:
            runs.append(match.group(1))
    return runs


def _finding_lines(rows: list[dict[str, Any]]) -> list[str]:
    return [f"- `{row['repo'] or 'unknown'}` — `{row['path']}`: {row['message']}" for row in rows]


def render_tracker(
    report: dict[str, Any],
    run_url: str,
    head_sha: str,
    prior_runs: list[str] | None = None,
) -> str:
    """Render the tracker body; every count is derived from ``report``."""

    counts = tracker_counts(report)
    runs = [url for url in (prior_runs or []) if url != run_url] + [run_url]
    runs = runs[-TRACKER_RUN_HISTORY_LIMIT:]
    stale = counts["stale_count"]
    drainable = counts["drainable_count"]
    lines = [
        TRACKER_MARKER,
        "## Backplane registry freshness tracker",
        "",
        "Opened by Health 78 (`.github/workflows/health-78-backplane-contract.yml`) from the",
        "uploaded `registry-status.json` report. Freshness findings stay warning-only in CI;",
        "this issue is where they get acted on. Lifecycle: "
        "`docs/contracts/research-backplane-contract.md`.",
        "",
        f"- `blocking_count`: {counts['blocking_count']}",
        f"- `stale_count`: {stale}",
        f"- `drainable_count`: {drainable}",
        f"- Owner-excluded findings omitted: {counts['owner_excluded_count']}",
        f"- Report generated at: `{report.get('generated_at', 'unknown')}`",
        f"- Head SHA: `{head_sha}`",
        f"- Run: {run_url}",
        "",
    ]
    if stale == 0:
        lines += [
            "### Status: fully drained",
            "",
            "`stale_count` is 0 in a complete, structurally valid report. "
            "The tracker closes on this run and reopens on the next stale finding.",
            "",
        ]
    else:
        lines += [f"**{stale} stale finding(s), {drainable} with a named drain action.**", ""]
    lines += [
        f"### Administrative deferral actions ({len(counts['deferrals'])})",
        "",
        "Expired `issue_deferred.expires_at`: renew the deferral with a reason, link a real",
        "implementation issue, or change the participant status in",
        "`config/backplane_participants.json`.",
        "",
    ]
    lines += _finding_lines(counts["deferrals"]) or ["- none"]
    lines += [
        "",
        f"### Stale reference evidence ({len(counts['references'])})",
        "",
        "Stale `reference_run_evidence.generated_at`: needs a fresh validated reference run",
        "recorded with its new evidence. Do not edit the timestamp without a new run.",
        "",
    ]
    lines += _finding_lines(counts["references"]) or ["- none"]
    if counts["unclassified"]:
        lines += [
            "",
            f"### Unclassified stale findings ({len(counts['unclassified'])}, no known drain)",
            "",
        ]
        lines += _finding_lines(counts["unclassified"])
    lines += ["", "### Runs", "", TRACKER_RUNS_START]
    lines += [f"- {url}" for url in runs]
    lines += [TRACKER_RUNS_END, ""]
    return "\n".join(lines)


def tracker_plan(
    report: Any,
    existing_issue: dict[str, Any] | None,
    run_url: str,
    head_sha: str,
) -> dict[str, Any]:
    """Decision plus everything the publisher needs to apply it."""

    decision = tracker_decision(report, existing_issue)
    plan: dict[str, Any] = {
        "decision": decision,
        "marker": TRACKER_MARKER,
        "title": TRACKER_TITLE,
    }
    if decision == "refuse":
        problem = tracker_report_problem(report)
        # "report": the report itself is unusable (a publisher defect, fail loudly);
        # "blocking": structural findings already fail the validation step.
        plan["refuse_kind"] = "report" if problem else "blocking"
        plan["reason"] = problem or (
            f"blocking_count={tracker_counts(report)['blocking_count']}: structural "
            "findings must be fixed first; the tracker only reports freshness"
        )
        return plan
    counts = tracker_counts(report)
    prior = tracker_runs_from_body((existing_issue or {}).get("body"))
    plan.update(
        {
            "blocking_count": counts["blocking_count"],
            "stale_count": counts["stale_count"],
            "drainable_count": counts["drainable_count"],
            "body": render_tracker(report, run_url, head_sha, prior),
        }
    )
    if decision == "close":
        plan["comment"] = (
            f"Fully drained: `stale_count=0`, `blocking_count=0` in {run_url} "
            f"(head `{head_sha}`). Closing; the next stale finding reopens this tracker."
        )
    return plan


def _tracker_main(args: argparse.Namespace) -> int:
    existing: dict[str, Any] | None = None
    if args.tracker_existing_state != "none":
        existing = {"state": args.tracker_existing_state, "body": ""}
        if args.tracker_existing_body is not None:
            try:
                existing["body"] = args.tracker_existing_body.read_text(encoding="utf-8")
            except OSError:
                existing["body"] = ""
    plan = tracker_plan(
        load_tracker_report(args.tracker_report),
        existing,
        args.run_url or "unknown",
        args.head_sha or "unknown",
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


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
        help="Compatibility flag; structural validation is always strict.",
    )
    parser.add_argument(
        "--enforce-freshness",
        action="store_true",
        help=(
            "Also fail on expired deferrals and stale reference runs. "
            "Freshness findings are warnings by default."
        ),
    )
    status_mode = parser.add_mutually_exclusive_group()
    status_mode.add_argument(
        "--write-status",
        type=Path,
        metavar="PATH",
        help="Write the markdown status report rendered from the registry.",
    )
    status_mode.add_argument(
        "--check-status",
        type=Path,
        metavar="PATH",
        help="Fail when PATH differs from the rendered markdown status report.",
    )
    tracker = parser.add_argument_group("freshness tracker")
    tracker.add_argument(
        "--tracker-report",
        type=Path,
        metavar="PATH",
        help="Print the tracker plan (decision, title, body) for a registry-status report.",
    )
    tracker.add_argument(
        "--tracker-existing-state",
        choices=("none", "open", "closed"),
        default="none",
        help="State of the issue found by the tracker marker.",
    )
    tracker.add_argument(
        "--tracker-existing-body",
        type=Path,
        metavar="PATH",
        help="File holding the existing tracker body (carries the run history).",
    )
    tracker.add_argument("--run-url", help="Provenance: URL of the publishing run.")
    tracker.add_argument("--head-sha", help="Provenance: commit SHA the run validated.")
    args = parser.parse_args(argv)

    if args.tracker_report is not None:
        return _tracker_main(args)

    registry = _load_json(args.registry)

    if args.write_status is not None:
        args.write_status.write_text(render_status_markdown(registry), encoding="utf-8")
        return 0

    if args.check_status is not None:
        expected = render_status_markdown(registry)
        try:
            actual = args.check_status.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Unable to read status report {args.check_status}: {exc}", file=sys.stderr)
            return 1
        if actual == expected:
            return 0
        diff = difflib.unified_diff(
            actual.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=str(args.check_status),
            tofile="rendered",
        )
        sys.stdout.writelines(diff)
        return 1
    findings = validate_registry(registry)
    blocking = blocking_findings(findings)
    stale = [f for f in findings if f.severity == STALE_SEVERITY]
    fail = bool(blocking) or (args.enforce_freshness and bool(stale))
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "ok": not findings,
        "blocking_ok": not blocking,
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "stale_count": len(stale),
        "findings": [
            {"path": f.path, "message": f.message, "severity": f.severity} for f in findings
        ],
        "participants": _reference_rows(registry),
    }

    # Emit staleness as a GitHub Actions warning annotation on stderr regardless of
    # output mode, so the freshness signal surfaces in the Actions UI even when the
    # JSON report is piped to a file. Non-blocking unless --enforce-freshness.
    for finding in stale:
        print(f"::warning::{finding.path}: {finding.message}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"blocking_count={report['blocking_count']}, stale_count={report['stale_count']}")
        if blocking:
            print("Backplane registry validation failed:", file=sys.stderr)
            for finding in blocking:
                print(f"- {finding.path}: {finding.message}", file=sys.stderr)
        if not findings:
            print("Backplane registry validation passed.")
        elif not blocking and not args.enforce_freshness:
            print("Backplane registry structurally valid (freshness warnings only).")
        if stale:
            print()
            for finding in stale:
                print(f"- {finding.path}: {finding.message}")

    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
