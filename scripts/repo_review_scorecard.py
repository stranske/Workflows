#!/usr/bin/env python3
"""Weekly OpenSSF Scorecard scan for repo-review human-gated issue candidates.

Consumes the public Scorecard API (published by Health 53) for configured repos,
surfaces low-scoring checks in the notify desktop reminder, and only materializes
approved findings into ``approved-issue-queue.json`` after explicit human approval
in ``config/repo_review_feedback.json``.

CLI:

    python scripts/repo_review_scorecard.py \\
        --registry config/repo_review_registry.json \\
        --docs-config config/source_of_truth_docs.yml \\
        --out docs/reports/repo-review/scorecard-scan.json

Flags:

    --workspace-root <path>   parent dir containing each repo's local_path
    --repos <repo> [<repo>]   restrict to a subset (default: all active + enabled)
    --dry-run                 skip API calls; emit empty findings per repo
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

SCHEMA = "repo-review-scorecard-scan/v1"
SCORECARD_API_BASE = "https://api.securityscorecards.dev/projects"
SCORECARD_CANDIDATE_INDEX_START = 9000
PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
# Gating fields must come from per-repo feedback; scorecard_defaults alone cannot approve.
SCORECARD_GATING_KEYS = frozenset({"decision", "approved_findings", "dropped_findings"})

try:
    from scripts.repo_review_issue_quality import (
        ISSUE_BODY_REQUIRED_SECTIONS,
        issue_body_quality_errors,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from repo_review_issue_quality import (  # type: ignore[no-redef]
        ISSUE_BODY_REQUIRED_SECTIONS,
        issue_body_quality_errors,
    )


def normalize_priority(value: object) -> str:
    priority = str(value or "normal").lower().strip()
    return priority if priority in PRIORITY_ORDER else "normal"


ApiFetcher = Callable[[str], tuple[bool, dict[str, Any] | None, str | None]]


def load_scorecard_scan(path: Path | None) -> dict[str, Any] | None:
    """Load a scorecard-scan.json payload, or return None when absent/malformed."""
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != SCHEMA:
        return None
    return payload


def _merge_scorecard_config(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def load_scorecard_config(docs_config_path: Path) -> dict[str, Any]:
    """Read source_of_truth_docs.yml and return merged scorecard settings per repo."""
    data = yaml.safe_load(docs_config_path.read_text(encoding="utf-8")) or {}
    defaults = data.get("scorecard") or {}
    if not isinstance(defaults, dict):
        defaults = {}
    repos = data.get("repos") or {}
    if not isinstance(repos, dict):
        repos = {}
    per_repo: dict[str, dict[str, Any]] = {}
    for repo, repo_config in repos.items():
        if not isinstance(repo_config, dict):
            continue
        raw_scorecard = repo_config.get("scorecard")
        repo_scorecard = raw_scorecard if isinstance(raw_scorecard, dict) else {}
        explicit_scorecard = bool(repo_scorecard)
        per_repo[str(repo)] = {
            "local_path": str(repo_config.get("local_path") or ""),
            "explicit_scorecard": explicit_scorecard,
            "scorecard": _merge_scorecard_config(defaults, repo_scorecard),
        }
    return {
        "defaults": defaults,
        "repos": per_repo,
        "config_source": str(docs_config_path),
    }


def load_active_repos(registry_path: Path) -> set[str]:
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    return {
        str(r.get("repo"))
        for r in (data.get("repos") or [])
        if isinstance(r, dict) and r.get("status") == "active" and r.get("repo")
    }


def scorecard_finding_id(check_name: str) -> str:
    return f"scorecard:{check_name}"


def scorecard_priority(score: float) -> str:
    return "high" if score <= 3.0 else "normal"


def scorecard_api_url(repo: str) -> str:
    return f"{SCORECARD_API_BASE}/github.com/{repo}"


def parse_scorecard_api_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize API checks into finding records."""
    checks = payload.get("checks") or []
    if not isinstance(checks, list):
        return []
    findings: list[dict[str, Any]] = []
    for item in checks:
        if not isinstance(item, dict):
            continue
        check_name = str(item.get("name") or "").strip()
        if not check_name:
            continue
        documentation = item.get("documentation") or {}
        doc_url = ""
        if isinstance(documentation, dict):
            doc_url = str(documentation.get("url") or "").strip()
        details = item.get("details") or []
        if not isinstance(details, list):
            details = []
        findings.append(
            {
                "check": check_name,
                "score": float(item.get("score", 0) or 0),
                "reason": str(item.get("reason") or "").strip(),
                "details": [str(d).strip() for d in details if str(d).strip()],
                "documentation_url": doc_url,
            }
        )
    return findings


def filter_scorecard_findings(
    findings: list[dict[str, Any]],
    *,
    minimum_score: float,
    include_checks: list[str] | None = None,
    exclude_checks: list[str] | None = None,
    max_findings_per_repo: int,
    source_url: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    include = {c.strip() for c in (include_checks or []) if c.strip()}
    exclude = {c.strip() for c in (exclude_checks or []) if c.strip()}
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for finding in findings:
        check = str(finding.get("check") or "")
        if include and check not in include:
            skipped.append(
                {"finding_id": scorecard_finding_id(check), "reason": "not in include_checks"}
            )
            continue
        if check in exclude:
            skipped.append(
                {"finding_id": scorecard_finding_id(check), "reason": "listed in exclude_checks"}
            )
            continue
        score = float(finding.get("score", 0) or 0)
        if score >= minimum_score:
            continue
        priority = scorecard_priority(score)
        candidates.append(
            {
                "finding_id": scorecard_finding_id(check),
                "check": check,
                "score": score,
                "minimum_score": minimum_score,
                "priority": priority,
                "reason": str(finding.get("reason") or "").strip(),
                "details": list(finding.get("details") or []),
                "documentation_url": str(finding.get("documentation_url") or "").strip(),
                "source_url": source_url,
            }
        )
    candidates.sort(key=lambda item: (float(item["score"]), str(item["check"])))
    if max_findings_per_repo > 0 and len(candidates) > max_findings_per_repo:
        overflow = candidates[max_findings_per_repo:]
        candidates = candidates[:max_findings_per_repo]
        for item in overflow:
            skipped.append(
                {
                    "finding_id": item["finding_id"],
                    "reason": f"capped by max_findings_per_repo={max_findings_per_repo}",
                }
            )
    return candidates, skipped


def build_scorecard_issue_body(
    *,
    repo: str,
    finding: dict[str, Any],
    workflow_path: str,
) -> str:
    check = str(finding.get("check") or "unknown-check")
    score = float(finding.get("score", 0) or 0)
    minimum = float(finding.get("minimum_score", 7.0) or 7.0)
    reason = str(finding.get("reason") or "Scorecard reported a low score for this check.")
    finding_id = str(finding.get("finding_id") or scorecard_finding_id(check))
    doc_url = str(finding.get("documentation_url") or "").strip()
    doc_line = f" See `{doc_url}` for remediation guidance." if doc_url else ""
    workflow_ref = workflow_path or ".github/workflows/health-53-scorecard.yml"
    return f"""## Why

OpenSSF Scorecard reports a low score for the {check} check in {repo}, indicating supply-chain posture may fall below the configured minimum ({minimum}). {reason}{doc_line}

## Scope

- Remediate the Scorecard finding `{finding_id}` (score {score:.1f} / minimum {minimum:.1f}).
- Align repository settings, workflows, and documented security posture with the failing check criteria.

## Non-Goals

- Do not change unrelated consumer-template or sync-manifest surfaces.
- Do not alter advisory Health 53 Scorecard workflow permissions, SARIF category, or publish behavior.

## Tasks

- [ ] Review the current {check} posture for `{repo}` against OpenSSF Scorecard documentation and repository settings.
- [ ] Implement the repository or workflow changes required to raise the {check} check score to at least {minimum:.1f}.
- [ ] Update repo-local security or CI documentation when the remediation changes an operational contract.
- [ ] Confirm the public Scorecard API or `{workflow_ref}` run reflects the improvement after the fix lands.

## Acceptance Criteria

- [ ] The {check} check score meets or exceeds the configured minimum ({minimum:.1f}) on the public Scorecard API for `{repo}`.
- [ ] Required maintainer and automation merge paths documented in `docs/ci/WORKFLOWS.md` remain functional after the remediation.
- [ ] The remediation is traceable to concrete repository files or GitHub settings referenced in the implementation notes.

## Implementation Notes

Relevant files: `{workflow_ref}`, `config/source_of_truth_docs.yml` (scorecard section), and repository settings implicated by the {check} check in `{repo}`.
"""


def review_evidence_trace_for_scorecard(
    *,
    repo: str,
    finding: dict[str, Any],
    workflow_path: str,
) -> dict[str, Any]:
    check = str(finding.get("check") or "unknown-check")
    score = float(finding.get("score", 0) or 0)
    minimum = float(finding.get("minimum_score", 7.0) or 7.0)
    workflow_ref = workflow_path or ".github/workflows/health-53-scorecard.yml"
    return {
        "gap": (
            f"OpenSSF Scorecard reports {check} at {score:.1f}, below the configured "
            f"minimum {minimum:.1f} for {repo}."
        ),
        "current_state": (
            f"The public Scorecard API currently scores {check} at {score:.1f}. "
            f"Health 53 publishes advisory results via `{workflow_ref}`."
        ),
        "required_change": (
            f"Raise the {check} check score to at least {minimum:.1f} by remediating the "
            "repository settings or workflows implicated by the Scorecard finding."
        ),
        "design_refs": ["docs/ci/WORKFLOWS.md", workflow_ref],
        "implementation_refs": [workflow_ref, "config/source_of_truth_docs.yml"],
        "test_refs": [workflow_ref],
        "issue_title_pattern": f"^Remediate Scorecard {check} finding for {repo}$",
    }


def scorecard_issue_title(repo: str, check: str) -> str:
    return f"Remediate Scorecard {check} finding for {repo}"


def scorecard_labels(priority: str) -> list[str]:
    normalized = normalize_priority(priority)
    return ["repo-review-approved", f"priority:{normalized}"]


def _scorecard_decision_for_repo(
    feedback_config: dict[str, Any], repo: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    defaults = feedback_config.get("scorecard_defaults") or {}
    if not isinstance(defaults, dict):
        defaults = {}
    non_gating_defaults = {
        key: value for key, value in defaults.items() if key not in SCORECARD_GATING_KEYS
    }
    repo_decision = (feedback_config.get("decisions") or {}).get(repo) or {}
    if not isinstance(repo_decision, dict):
        repo_decision = {}
    repo_scorecard = repo_decision.get("scorecard")
    has_repo_scorecard = isinstance(repo_scorecard, dict) and bool(repo_scorecard)
    if not has_repo_scorecard:
        # scorecard_defaults alone cannot approve findings — per-repo block required.
        merged = {
            **non_gating_defaults,
            "decision": "defer",
            "approved_findings": [],
            "dropped_findings": [],
        }
        return merged, repo_decision
    merged = {**non_gating_defaults, **repo_scorecard}
    return merged, repo_decision


def _approved_findings_list(decision: dict[str, Any]) -> list[str] | None:
    approved = decision.get("approved_findings", [])
    if approved == "all":
        return None
    if not isinstance(approved, list):
        return []
    return [str(item).strip() for item in approved if str(item).strip()]


def approved_scorecard_issue_items(
    scorecard_scan: dict[str, Any] | None,
    feedback_config: dict[str, Any],
    generated_on: str,
) -> dict[str, list[Any]]:
    """Build approved/pending/dropped Scorecard queue items from scan + feedback."""
    result: dict[str, list[Any]] = {
        "issues": [],
        "pending": [],
        "dropped": [],
        "warnings": [],
    }
    if not scorecard_scan:
        return result

    candidate_index = SCORECARD_CANDIDATE_INDEX_START
    for bucket in scorecard_scan.get("by_repo") or []:
        if not isinstance(bucket, dict):
            continue
        repo = str(bucket.get("repo") or "").strip()
        if not repo:
            continue
        local_path = str(bucket.get("local_path") or "").strip()
        workflow_path = str(bucket.get("workflow") or ".github/workflows/health-53-scorecard.yml")
        scorecard_decision, repo_decision = _scorecard_decision_for_repo(feedback_config, repo)
        decision_type = str(scorecard_decision.get("decision") or "defer").strip().lower()
        approved_list = _approved_findings_list(scorecard_decision)
        if approved_list is None:
            result["warnings"].append(
                f"{repo}: scorecard approved_findings='all' is not honored; explicit finding IDs required."
            )
            approved_set: set[str] = set()
        else:
            approved_set = set(approved_list)
        dropped_set = {
            str(item).strip()
            for item in (scorecard_decision.get("dropped_findings") or [])
            if str(item).strip()
        }
        priority_overrides = scorecard_decision.get("priority_overrides") or {}
        if not isinstance(priority_overrides, dict):
            priority_overrides = {}
        default_priority = normalize_priority(scorecard_decision.get("priority", "normal"))
        feedback_notes = str(scorecard_decision.get("notes") or "").strip()

        findings = bucket.get("findings") or []
        if not isinstance(findings, list):
            findings = []

        for finding in findings:
            if not isinstance(finding, dict):
                continue
            finding_id = str(finding.get("finding_id") or "").strip()
            if not finding_id:
                continue
            check = str(finding.get("check") or "")
            if finding_id in dropped_set:
                result["dropped"].append(
                    {
                        "repo": repo,
                        "finding_id": finding_id,
                        "check": check,
                        "reason": "scorecard finding dropped",
                    }
                )
                continue
            if decision_type != "approve":
                result["pending"].append(
                    {
                        "repo": repo,
                        "finding_id": finding_id,
                        "check": check,
                        "score": finding.get("score"),
                        "reason": f"scorecard decision={decision_type}",
                    }
                )
                continue
            if finding_id not in approved_set:
                result["pending"].append(
                    {
                        "repo": repo,
                        "finding_id": finding_id,
                        "check": check,
                        "score": finding.get("score"),
                        "reason": "scorecard finding not explicitly approved",
                    }
                )
                continue

            priority = normalize_priority(priority_overrides.get(finding_id, default_priority))
            body = build_scorecard_issue_body(
                repo=repo,
                finding=finding,
                workflow_path=workflow_path,
            )
            quality_errors = issue_body_quality_errors(body)
            if quality_errors:
                result["warnings"].append(
                    f"{repo} scorecard finding {finding_id} failed issue-body quality: "
                    f"{'; '.join(quality_errors[:3])}"
                )
                result["pending"].append(
                    {
                        "repo": repo,
                        "finding_id": finding_id,
                        "check": check,
                        "score": finding.get("score"),
                        "reason": "scorecard issue body failed quality gate",
                    }
                )
                continue

            result["issues"].append(
                {
                    "repo": repo,
                    "local_path": local_path,
                    "priority": priority,
                    "priority_rank": PRIORITY_ORDER[priority],
                    "candidate_index": candidate_index,
                    "source_type": "scorecard finding",
                    "source": "OpenSSF Scorecard",
                    "title": scorecard_issue_title(repo, check),
                    "labels": scorecard_labels(priority),
                    "body_format": list(ISSUE_BODY_REQUIRED_SECTIONS),
                    "body_valid": True,
                    "body_quality_errors": [],
                    "review_evidence_trace": review_evidence_trace_for_scorecard(
                        repo=repo,
                        finding=finding,
                        workflow_path=workflow_path,
                    ),
                    "body": body,
                    "feedback_notes": feedback_notes,
                    "scorecard_finding_id": finding_id,
                }
            )
            candidate_index += 1

        # Blanket repo approvals must not silently approve Scorecard findings.
        repo_approved = repo_decision.get("approved_candidates")
        if repo_approved == "all" and findings and not approved_set:
            result["warnings"].append(
                f"{repo}: repo-level approved_candidates='all' does not approve Scorecard findings."
            )

    result["issues"].sort(
        key=lambda item: (
            int(item.get("priority_rank", 1)),
            str(item.get("repo", "")).lower(),
            int(item.get("candidate_index", 0)),
        )
    )
    return result


def fetch_scorecard_api(
    repo: str, *, timeout: int = 60
) -> tuple[bool, dict[str, Any] | None, str | None]:
    url = scorecard_api_url(repo)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return False, None, f"HTTP {exc.code} for {url}"
    except urllib.error.URLError as exc:
        return False, None, f"network error for {url}: {exc.reason}"
    except (TimeoutError, json.JSONDecodeError, OSError) as exc:
        return False, None, str(exc)
    if not isinstance(payload, dict):
        return False, None, f"unexpected payload type for {url}"
    return True, payload, None


def dry_run_fetcher(repo: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    return True, {"checks": []}, None


def scan_scorecard_repos(
    *,
    scorecard_config: dict[str, Any],
    active_repos: set[str],
    repo_subset: set[str] | None = None,
    fetcher: ApiFetcher | None = None,
) -> dict[str, Any]:
    fetch = fetcher or fetch_scorecard_api
    defaults = scorecard_config.get("defaults") or {}
    if not isinstance(defaults, dict):
        defaults = {}
    default_enabled = bool(defaults.get("enabled", False))
    default_minimum = float(defaults.get("default_minimum_score", 7.0) or 7.0)
    default_max = int(defaults.get("max_findings_per_repo", 5) or 5)
    default_include = list(defaults.get("include_checks") or [])
    default_exclude = list(defaults.get("exclude_checks") or [])

    by_repo: list[dict[str, Any]] = []
    total_findings = 0
    total_errors = 0

    for repo, repo_entry in (scorecard_config.get("repos") or {}).items():
        if repo not in active_repos:
            continue
        if repo_subset and repo not in repo_subset:
            continue
        if not isinstance(repo_entry, dict):
            continue
        # Global enabled=true applies only to repos with an explicit scorecard block
        # in source_of_truth_docs.yml — not every docs-configured fleet repo.
        if not repo_entry.get("explicit_scorecard"):
            continue
        repo_scorecard = repo_entry.get("scorecard") or {}
        if not isinstance(repo_scorecard, dict):
            repo_scorecard = {}
        enabled = bool(repo_scorecard.get("enabled", default_enabled))
        if not enabled:
            continue

        local_path = str(repo_entry.get("local_path") or "")
        minimum_score = float(
            repo_scorecard.get(
                "minimum_score", repo_scorecard.get("default_minimum_score", default_minimum)
            )
            or default_minimum
        )
        max_findings = int(repo_scorecard.get("max_findings_per_repo", default_max) or default_max)
        include_checks = list(repo_scorecard.get("include_checks", default_include) or [])
        exclude_checks = list(repo_scorecard.get("exclude_checks", default_exclude) or [])
        workflow_path = str(
            repo_scorecard.get("workflow") or ".github/workflows/health-53-scorecard.yml"
        )
        source_url = scorecard_api_url(repo)

        ok, payload, error = fetch(repo)
        errors: list[dict[str, str]] = []
        findings: list[dict[str, Any]] = []
        skipped_findings: list[dict[str, Any]] = []
        if not ok or payload is None:
            errors.append({"error": error or "unknown fetch error"})
            total_errors += 1
        else:
            raw_findings = parse_scorecard_api_response(payload)
            findings, skipped_findings = filter_scorecard_findings(
                raw_findings,
                minimum_score=minimum_score,
                include_checks=include_checks,
                exclude_checks=exclude_checks,
                max_findings_per_repo=max_findings,
                source_url=source_url,
            )
            total_findings += len(findings)

        by_repo.append(
            {
                "repo": repo,
                "local_path": local_path,
                "workflow": workflow_path,
                "source": {
                    "kind": "public_api",
                    "url": source_url,
                },
                "minimum_score": minimum_score,
                "findings": findings,
                "skipped_findings": skipped_findings,
                "errors": errors,
            }
        )

    by_repo.sort(key=lambda item: str(item.get("repo") or ""))
    return {
        "schema": SCHEMA,
        "generated_on": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config_source": str(
            scorecard_config.get("config_source") or "config/source_of_truth_docs.yml"
        ),
        "total_findings": total_findings,
        "total_errors": total_errors,
        "by_repo": by_repo,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument(
        "--docs-config",
        type=Path,
        default=Path("config/source_of_truth_docs.yml"),
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repos", nargs="*", default=[])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="skip API calls; emit empty findings per enabled repo",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        scorecard_config = load_scorecard_config(args.docs_config)
    except (FileNotFoundError, yaml.YAMLError, ValueError) as exc:
        print(f"[scorecard-scan] cannot load docs config: {exc}", file=sys.stderr)
        return 2
    try:
        active = load_active_repos(args.registry)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[scorecard-scan] cannot load registry: {exc}", file=sys.stderr)
        return 2

    repo_subset = set(args.repos) if args.repos else None
    fetcher: ApiFetcher = dry_run_fetcher if args.dry_run else fetch_scorecard_api
    result = scan_scorecard_repos(
        scorecard_config=scorecard_config,
        active_repos=active,
        repo_subset=repo_subset,
        fetcher=fetcher,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"[scorecard-scan] scanned {len(result['by_repo'])} repo(s); "
        f"findings={result['total_findings']} errors={result['total_errors']} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
