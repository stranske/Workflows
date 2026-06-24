#!/usr/bin/env python3
"""Export post-merge keepalive durability labels as langsmith-fleet/v1 records."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "langsmith-fleet/v1"
WORKFLOWS_REPO = "stranske/Workflows"
WORKFLOWS_ISSUE = "stranske/Workflows#2150"
WORKFLOWS_SURFACE = "agent-automation"
DURABILITY_OPERATION = "durability"
DEFAULT_ARTIFACT = Path("artifacts/langsmith/langsmith-fleet.ndjson")
KNOWN_AGENT_LABELS = {"codex", "claude", "cursor", "gemini", "vibe"}


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _label_names(pr: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for label in pr.get("labels") or []:
        name = label.get("name") if isinstance(label, dict) else label
        if isinstance(name, str) and name.strip():
            out.append(name.strip())
    return out


def infer_agent(pr: dict[str, Any]) -> str:
    """Infer the producing agent from PR labels or branch naming."""
    for label in _label_names(pr):
        lower = label.lower().strip()
        if lower.startswith("agent:"):
            candidate = lower.split(":", 1)[1].strip()
            if candidate in KNOWN_AGENT_LABELS:
                return candidate
        if lower.startswith("runner:"):
            candidate = lower.split(":", 1)[1].strip()
            if candidate in KNOWN_AGENT_LABELS:
                return candidate

    head_ref = str(pr.get("headRefName") or pr.get("head_ref") or "").lower()
    for agent in KNOWN_AGENT_LABELS:
        if head_ref.startswith(f"{agent}/") or head_ref.startswith(f"{agent}-"):
            return agent
    return "unknown"


def _closing_issue_refs(pr: dict[str, Any]) -> list[dict[str, Any]]:
    refs = pr.get("closingIssuesReferences") or pr.get("closing_issues") or []
    return [ref for ref in refs if isinstance(ref, dict)]


def _has_reopened_closing_issue(pr: dict[str, Any]) -> dict[str, Any] | None:
    for ref in _closing_issue_refs(pr):
        state = str(ref.get("state") or ref.get("stateReason") or "").strip().lower()
        if state == "open":
            return ref
    return None


def _mentions_pr_number(text: str, number: int) -> bool:
    return bool(
        re.search(rf"(?<!\d)#\s*{number}\b", text)
        or re.search(rf"/pull/{number}\b", text)
        or re.search(rf"\bpr\s*{number}\b", text, re.IGNORECASE)
    )


def _matching_revert(pr: dict[str, Any], revert_prs: list[dict[str, Any]]) -> dict[str, Any] | None:
    number = int(pr.get("number") or 0)
    merged_at = _parse_time(pr.get("mergedAt") or pr.get("merged_at"))
    if number <= 0:
        return None
    for candidate in revert_prs:
        candidate_merged_at = _parse_time(candidate.get("mergedAt") or candidate.get("merged_at"))
        if merged_at and candidate_merged_at and candidate_merged_at < merged_at:
            continue
        text = f"{candidate.get('title') or ''}\n{candidate.get('body') or ''}"
        if _mentions_pr_number(text, number):
            return candidate
    return None


def classify_durability(
    pr: dict[str, Any],
    *,
    revert_prs: list[dict[str, Any]],
    now: datetime,
    grace_days: int,
) -> dict[str, Any]:
    """Classify a merged keepalive PR after the durability grace window."""
    number = int(pr.get("number") or 0)
    merged_at = _parse_time(pr.get("mergedAt") or pr.get("merged_at"))
    if number <= 0 or merged_at is None:
        return {"durability": "skipped", "reason": "missing_merged_pr_metadata"}

    age = now.astimezone(UTC) - merged_at
    if age < timedelta(days=grace_days):
        return {
            "durability": "pending",
            "reason": "inside_grace_window",
            "age_days": age.total_seconds() / 86400,
        }

    revert = _matching_revert(pr, revert_prs)
    if revert:
        return {
            "durability": "reverted",
            "reason": "matching_revert_pr",
            "evidence_pr": int(revert.get("number") or 0),
            "evidence_title": str(revert.get("title") or "")[:160],
        }

    reopened = _has_reopened_closing_issue(pr)
    if reopened:
        return {
            "durability": "reopened",
            "reason": "closing_issue_reopened",
            "evidence_issue": int(reopened.get("number") or 0),
        }

    return {"durability": "durable", "reason": "no_revert_or_reopened_issue_after_grace"}


def build_fleet_record(
    repo: str,
    pr: dict[str, Any],
    classification: dict[str, Any],
    *,
    now: datetime,
    grace_days: int,
) -> dict[str, Any]:
    pr_number = int(pr["number"])
    durability = str(classification["durability"])
    merged_at = _parse_time(pr.get("mergedAt") or pr.get("merged_at"))
    agent = infer_agent(pr)
    target_pr = f"{repo}#{pr_number}"
    domain = {
        "workflow": "maint-85-keepalive-durability-export",
        "agent": agent,
        "step": "post-merge-durability",
        "attempt": 1,
        "result": durability,
        "durability": durability,
        "target_repo": repo,
        "target_pr": target_pr,
        "merged_at": _iso(merged_at) if merged_at else "",
        "grace_days": grace_days,
        "reason": classification.get("reason", ""),
    }
    for key in ("evidence_pr", "evidence_issue", "evidence_title", "age_days"):
        if key in classification:
            domain[key] = classification[key]
    closing_refs = _closing_issue_refs(pr)
    if closing_refs and closing_refs[0].get("number"):
        domain["target_issue"] = f"{repo}#{closing_refs[0]['number']}"

    status = {"durable": "success", "pending": "skipped"}.get(durability, "error")
    return {
        "schema_version": SCHEMA_VERSION,
        "repo": WORKFLOWS_REPO,
        "surface": WORKFLOWS_SURFACE,
        "operation": DURABILITY_OPERATION,
        "run_id": f"durability:{target_pr}",
        "status": status,
        "github_issue": WORKFLOWS_ISSUE,
        "github_pr": target_pr,
        "recorded_at": _iso(now),
        "domain": domain,
    }


def build_records(
    repo_payloads: list[dict[str, Any]],
    *,
    now: datetime,
    grace_days: int,
    include_pending: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    skipped: Counter[str] = Counter()

    for payload in repo_payloads:
        repo = str(payload.get("repo") or "").strip()
        if not repo:
            skipped["missing_repo"] += 1
            continue
        revert_prs = [pr for pr in payload.get("revert_prs", []) if isinstance(pr, dict)]
        for pr in payload.get("prs", []) or []:
            if not isinstance(pr, dict):
                skipped["invalid_pr"] += 1
                continue
            classification = classify_durability(
                pr, revert_prs=revert_prs, now=now, grace_days=grace_days
            )
            durability = str(classification.get("durability") or "skipped")
            counts[durability] += 1
            if durability == "pending" and not include_pending:
                skipped["pending_grace"] += 1
                continue
            if durability == "skipped":
                skipped[str(classification.get("reason") or "skipped")] += 1
                continue
            records.append(
                build_fleet_record(repo, pr, classification, now=now, grace_days=grace_days)
            )

    summary = {
        "records": len(records),
        "counts": dict(sorted(counts.items())),
        "skipped": dict(sorted(skipped.items())),
    }
    return records, summary


def registry_repos(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    repos: list[str] = []
    seen: set[str] = set()
    for entry in data.get("repos", []):
        repo = str(entry.get("repo") or "").strip()
        if repo and repo not in seen:
            seen.add(repo)
            repos.append(repo)
    return repos


def _gh_json(args: list[str]) -> list[dict[str, Any]]:
    proc = subprocess.run(["gh", *args], text=True, capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "gh command failed")
    data = json.loads(proc.stdout or "[]")
    if not isinstance(data, list):
        raise RuntimeError("gh command did not return a JSON array")
    return [item for item in data if isinstance(item, dict)]


def fetch_repo_payload(repo: str, *, since: str, limit: int) -> dict[str, Any]:
    pr_fields = "number,title,body,mergedAt,labels,author,headRefName,closingIssuesReferences"
    prs = _gh_json(
        [
            "pr",
            "list",
            "-R",
            repo,
            "--state",
            "merged",
            "--limit",
            str(limit),
            "--label",
            "agents:keepalive",
            "--search",
            f"merged:>={since}",
            "--json",
            pr_fields,
        ]
    )
    revert_prs = _gh_json(
        [
            "pr",
            "list",
            "-R",
            repo,
            "--state",
            "merged",
            "--limit",
            str(limit),
            "--search",
            f"Revert in:title merged:>={since}",
            "--json",
            "number,title,body,mergedAt",
        ]
    )
    return {"repo": repo, "prs": prs, "revert_prs": revert_prs}


def write_ndjson(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records
    )
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, help="Offline payload with repos/prs/revert_prs")
    parser.add_argument(
        "--registry", type=Path, default=Path("config/langsmith_fleet_registry.json")
    )
    parser.add_argument(
        "--repo", action="append", default=[], help="Repository to scan; repeatable"
    )
    parser.add_argument("--days", type=int, default=30, help="Merged PR lookback window")
    parser.add_argument("--grace-days", type=int, default=7, help="Durability grace window")
    parser.add_argument("--limit", type=int, default=100, help="Per-repo PR query limit")
    parser.add_argument(
        "--include-pending", action="store_true", help="Emit pending grace-window records"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    args = parser.parse_args(argv)

    if args.days <= 0:
        parser.error("--days must be positive")
    if args.grace_days < 0:
        parser.error("--grace-days must be non-negative")
    if args.limit <= 0:
        parser.error("--limit must be positive")

    now = datetime.now(UTC)
    if args.input_json:
        try:
            payload = json.loads(args.input_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"--input-json could not be read: {exc}")
        repo_payloads = payload.get("repos", []) if isinstance(payload, dict) else []
        if not isinstance(repo_payloads, list):
            parser.error("--input-json must contain a repos array")
    else:
        since = (now - timedelta(days=args.days)).date().isoformat()
        repos = args.repo or registry_repos(args.registry)
        repo_payloads = []
        errors: dict[str, str] = {}
        for repo in repos:
            try:
                repo_payloads.append(fetch_repo_payload(repo, since=since, limit=args.limit))
            except Exception as exc:  # pragma: no cover - exercised in live workflow
                errors[repo] = str(exc)
        if errors:
            print(json.dumps({"fetch_errors": errors}, indent=2, sort_keys=True), file=sys.stderr)
            if not repo_payloads:
                return 1

    records, summary = build_records(
        repo_payloads, now=now, grace_days=args.grace_days, include_pending=args.include_pending
    )
    write_ndjson(records, args.output)

    summary = {
        **summary,
        "schema_version": SCHEMA_VERSION,
        "output": str(args.output),
        "repo_payloads": len(repo_payloads),
        "include_pending": args.include_pending,
        "grace_days": args.grace_days,
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            f"export_keepalive_durability: wrote {summary['records']} record(s) "
            f"to {args.output}"
        )
        if summary["counts"]:
            print(f"counts: {json.dumps(summary['counts'], sort_keys=True)}")
        if summary["skipped"]:
            print(f"skipped: {json.dumps(summary['skipped'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
