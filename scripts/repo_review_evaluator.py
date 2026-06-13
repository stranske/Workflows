#!/usr/bin/env python3
"""Generate local weekly design-vs-implementation repo review packets.

This script is intentionally local-first. It reads a registry of repos,
standardizes the review worksheet for each active local clone, gathers issue
draft inputs from Issues.txt and prior design-review archives, and writes a
single human decision packet. It does not create GitHub issues.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from scripts.repo_review_issue_quality import (
        ISSUE_BODY_REQUIRED_SECTIONS,
        issue_body_is_agent_ready,
        issue_body_quality_errors,
        review_evidence_trace_errors,
    )
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution.
    from repo_review_issue_quality import (  # type: ignore[no-redef]
        ISSUE_BODY_REQUIRED_SECTIONS,
        issue_body_is_agent_ready,
        issue_body_quality_errors,
        review_evidence_trace_errors,
    )

VALID_STATUSES = {"active", "paused", "ignored", "needs-human"}
PENDING_REVIEW_STATUS = "pending standardized review"
EXECUTED_REVIEW_STATUS = "standard review executed; human decision queued"
REVIEW_PROMPT_RE = re.compile(
    r"summary of the current state|state of the codebase|what work remains|original design|"
    r"long[- ]term repo goals|current state.*repo|remaining gaps?|production ready|"
    r"production-readiness|ready to test|full goals|readme and docs|full testing|"
    r"most recent issue set|after the completion",
    re.I,
)
MAINTENANCE_SESSION_RE = re.compile(
    r"dependabot|sync[- ]generated|open PRs?|automerge|rate limits?|verify:compare|"
    r"verify:evaluate|remote repo api capacity|maintenance PRs?",
    re.I,
)
STRICT_REVIEW_PROMPT_RE = re.compile(
    r"state of the codebase|what work remains|original design|long[- ]term repo goals|"
    r"remaining gaps?|production-readiness|ready to test|full goals|readme and docs|"
    r"full testing|most recent issue set|after the completion",
    re.I,
)
ISSUE_HEADING_RE = re.compile(
    r"^(?:#+\s*)?(?:Issue\s+)?(?P<num>\d+)(?:[\).:]|\s+[-–—])\s*(?P<title>.+)$",
    re.I,
)
ARCHIVE_RECOMMENDATION_RE = re.compile(r"^(?P<num>\d+)[\).]\s+(?P<title>.+)$")
GENERATED_DIRTY_PATH_PREFIXES = (
    ".mypy_cache/",
    ".gitnexus/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
    ".worktrees/",
    "__pycache__/",
    "docs/reports/",
    "node_modules/",
)
GENERATED_DIRTY_PATH_PARTS = ("/__pycache__/",)
GENERATED_DIRTY_SUFFIXES = (".pyc", ".pyo", ".DS_Store")
GENERATED_DIRTY_FILENAMES = {".gitnexus", "workloop-state.md"}
HELPER_DIRTY_FILENAMES = {"Issues.txt"}
DESIGN_DOC_EXCLUDED_PREFIXES = (
    ".github/",
    ".venv/",
    "archive/",
    "archives/",
    "agents/",
    "docs/archive/",
    "docs/reports/",
    "node_modules/",
    "scripts/",
)
DESIGN_DOC_EXCLUDED_NAMES = {
    "AGENT_ISSUE_FORMAT.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CODEX_TOKEN_REFRESH.md",
    "LABELS.md",
}
IMPLEMENTATION_AREA_PATHS = (
    "api",
    "src",
    "app",
    "apps",
    "backend",
    "lib",
    "packages",
    "dashboard",
    "frontend",
    "trip_planner",
    "scripts",
    "tests",
    ".github/workflows",
)
REVIEW_SCAN_FILE_LIMIT = 300
SOURCE_FILE_SUFFIXES = (
    ".css",
    ".go",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".mjs",
    ".py",
    ".rs",
    ".sh",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
)
IMPLEMENTATION_SCAN_EXCLUDED_PREFIXES = (
    ".agents/",
    ".github/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
    ".worktrees/",
    "archive/",
    "archives/",
    "docs/",
    "docs/reports/",
    "node_modules/",
)
IMPLEMENTATION_SCAN_EXCLUDED_PARTS = ("/__pycache__/", "/node_modules/")
EVIDENCE_SCAN_EXCLUDED_PREFIXES = (
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
    ".worktrees/",
    "node_modules/",
)
EVIDENCE_SCAN_EXCLUDED_PARTS = ("/__pycache__/", "/node_modules/")
TEST_FILE_RE = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)test[_-].+|[_-]test\.", re.I)
SMOKE_TEST_RE = re.compile(r"\b(smoke|e2e|end[- ]to[- ]end|integration|live)\b", re.I)
STATE_INTEGRATION_RE = re.compile(
    r"\b(api|client|database|db|github|integration|persist|provider|source|state|store|token|workflow)\b",
    re.I,
)
REVIEW_DIMENSIONS = (
    {
        "id": "design_contract",
        "label": "Design Contract",
        "prompt": (
            "Identify the intended product or workflow from README/docs and the registry "
            "decision anchor. Note stale, conflicting, or missing design commitments."
        ),
    },
    {
        "id": "implementation_coverage",
        "label": "Implementation Coverage",
        "prompt": (
            "Compare the documented capabilities to current code paths. Distinguish real "
            "working behavior from scaffolds, seams, fixtures, or advisory-only outputs."
        ),
    },
    {
        "id": "test_and_live_readiness",
        "label": "Test And Live Readiness",
        "prompt": (
            "Determine whether tests or smoke paths prove the user journey that the design "
            "requires. Identify blockers before live testing or production-like use."
        ),
    },
    {
        "id": "integration_and_state",
        "label": "Integration And State",
        "prompt": (
            "Check cross-repo contracts, external providers, persistence, reload behavior, "
            "source authority, generated artifacts, and workflow automation handoffs."
        ),
    },
    {
        "id": "issue_generation",
        "label": "Issue Generation",
        "prompt": (
            "Convert only verified gaps into issue drafts with evidence, non-goals, tasks, "
            "acceptance criteria, and tests that would fail before the fix."
        ),
    },
)
PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
GITNEXUS_REFRESH_STATUSES = {"missing", "stale"}
GENERIC_REVIEW_SUMMARY_PHRASES = (
    "implementation files exist, but the automated keyword pass",
    "implementation files and repo-domain code hits were found",
    "semantic review must verify",
    "testing/live-readiness evidence exists, but approval still requires confirming",
    "test and smoke/integration markers exist; review must verify",
    "integration/state/workflow evidence was found; review must confirm",
    "no candidate issue set was generated from current inputs",
)


@dataclass(frozen=True)
class RepoConfig:
    repo: str
    local_path: str
    status: str
    cadence: str
    decision_anchor: str


@dataclass(frozen=True)
class IssueDraft:
    number: int
    title: str
    body: str
    open_tasks: int
    done_tasks: int


@dataclass(frozen=True)
class ArchiveCandidate:
    title: str
    source_file: str
    thread_name: str
    timestamp: str
    excerpt: str


def run_git(repo_path: Path, args: list[str], timeout: int = 30) -> str:
    if not (repo_path / ".git").exists() and not (repo_path / ".git").is_file():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.rstrip()


def status_path(status_line: str) -> str:
    return status_line[3:].strip() if len(status_line) > 3 else status_line.strip()


def is_generated_dirty_path(status_line: str) -> bool:
    path = status_path(status_line)
    return (
        path.startswith(GENERATED_DIRTY_PATH_PREFIXES)
        or any(part in path for part in GENERATED_DIRTY_PATH_PARTS)
        or path.endswith(GENERATED_DIRTY_SUFFIXES)
        or path in GENERATED_DIRTY_FILENAMES
    )


def material_status_lines(status_lines: list[str]) -> list[str]:
    return [line for line in status_lines if not is_generated_dirty_path(line)]


def is_gitnexus_ignore_helper(repo_path: Path | None, status_line: str) -> bool:
    if repo_path is None or status_path(status_line) != ".gitignore":
        return False
    diff = "\n".join(
        [
            run_git(repo_path, ["diff", "--", ".gitignore"], timeout=5),
            run_git(repo_path, ["diff", "--cached", "--", ".gitignore"], timeout=5),
        ]
    )
    changed_lines = [
        line
        for line in diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    return changed_lines == ["+.gitnexus"]


def is_helper_dirty_path(status_line: str, repo_path: Path | None = None) -> bool:
    return status_path(status_line) in HELPER_DIRTY_FILENAMES or is_gitnexus_ignore_helper(
        repo_path, status_line
    )


def helper_status_lines(status_lines: list[str], repo_path: Path | None = None) -> list[str]:
    return [
        line
        for line in status_lines
        if not is_generated_dirty_path(line) and is_helper_dirty_path(line, repo_path)
    ]


def review_blocking_status_lines(
    status_lines: list[str], repo_path: Path | None = None
) -> list[str]:
    return [
        line
        for line in status_lines
        if not is_generated_dirty_path(line) and not is_helper_dirty_path(line, repo_path)
    ]


def issue_queue_status(
    round1_findings: dict[str, Any] | None,
    round2_converged: dict[str, Any] | None = None,
) -> str:
    """Issue queue status reflects the latest negotiated review state.

    Precedence: round-2 converged set > round-1 single-agent findings > nothing.
    Issues.txt drafts and archive entries are not candidate sources under the
    new design.
    """
    if round2_converged:
        candidates = round2_converged.get("converged_candidates") or []
        meta = round2_converged.get("meta_candidate")
        deadlocks = round2_converged.get("deadlocked_candidates") or []
        if candidates or meta:
            return "round 2 converged"
        if deadlocks:
            return "round 2 deadlocked"
        return "round 2 found no gaps"
    if not round1_findings:
        return "round 1 not yet run"
    candidates = round1_findings.get("candidates") or []
    if candidates:
        return "round 1 candidates present"
    if round1_findings.get("deeper_review_needed"):
        return "round 1 requested deeper review"
    return "round 1 found no gaps"


def review_status(repo: RepoConfig, repo_path: Path, blocking_lines: list[str]) -> str:
    if repo.status != "active":
        return "not scheduled"
    if not repo_path.exists():
        return "missing local clone"
    if blocking_lines:
        return "blocked by non-helper local changes"
    return PENDING_REVIEW_STATUS


def is_design_doc_path(rel_path: str) -> bool:
    lowered = rel_path.lower()
    return (
        lowered.endswith(".md")
        and not lowered.startswith(DESIGN_DOC_EXCLUDED_PREFIXES)
        and not Path(rel_path).name.startswith("codex-prompt-")
        and Path(rel_path).name not in DESIGN_DOC_EXCLUDED_NAMES
        and "/docs/reports/" not in lowered
        and "/__pycache__/" not in lowered
    )


def collect_design_files(repo_path: Path, limit: int = 20) -> list[str]:
    if not repo_path.exists():
        return []
    tracked = run_git(repo_path, ["ls-files", "*.md"]).splitlines()
    if tracked:
        candidates = [path for path in tracked if is_design_doc_path(path)]
    else:
        candidates = [
            str(path.relative_to(repo_path).as_posix())
            for path in repo_path.rglob("*.md")
            if is_design_doc_path(str(path.relative_to(repo_path).as_posix()))
        ]

    def sort_key(path: str) -> tuple[int, str]:
        priority = 3
        if path == "README.md":
            priority = 0
        elif path.startswith("docs/"):
            priority = 1
        elif "/" not in path:
            priority = 2
        return priority, path.lower()

    return sorted(dict.fromkeys(candidates), key=sort_key)[:limit]


def collect_implementation_areas(repo_path: Path) -> list[dict[str, int | str]]:
    areas: list[dict[str, int | str]] = []
    if not repo_path.exists():
        return areas
    for rel_path in IMPLEMENTATION_AREA_PATHS:
        path = repo_path / rel_path
        if not path.exists():
            continue
        tracked_files = len(run_git(repo_path, ["ls-files", rel_path]).splitlines())
        areas.append({"path": rel_path, "tracked_files": tracked_files})
    return areas


def format_implementation_areas(areas: list[dict[str, int | str]]) -> list[str]:
    return [f"{area['path']} ({area['tracked_files']} tracked files)" for area in areas]


def tracked_repo_files(repo_path: Path) -> list[str]:
    if not repo_path.exists():
        return []
    return run_git(repo_path, ["ls-files"]).splitlines()


def is_source_like_file(path: str) -> bool:
    return path.endswith(SOURCE_FILE_SUFFIXES)


def is_test_file(path: str) -> bool:
    return TEST_FILE_RE.search(path) is not None


def is_evidence_noise_file(path: str) -> bool:
    return path.startswith(EVIDENCE_SCAN_EXCLUDED_PREFIXES) or any(
        part in path for part in EVIDENCE_SCAN_EXCLUDED_PARTS
    )


def is_implementation_file(path: str) -> bool:
    return (
        is_source_like_file(path)
        and not is_evidence_noise_file(path)
        and not is_design_doc_path(path)
        and not is_test_file(path)
        and not path.startswith(IMPLEMENTATION_SCAN_EXCLUDED_PREFIXES)
        and not any(part in path for part in IMPLEMENTATION_SCAN_EXCLUDED_PARTS)
    )


def markdown_headings(repo_path: Path, rel_path: str, limit: int = 6) -> list[str]:
    text = run_git(repo_path, ["grep", "-h", "-e", "^#", "--", rel_path], timeout=5)
    headings: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            heading = line.strip().lstrip("#").strip()
            if heading:
                headings.append(heading)
        if len(headings) >= limit:
            break
    return headings


def keyword_file_hits(
    repo_path: Path,
    files: list[str],
    keywords: set[str],
    limit: int = 8,
    pathspecs: list[str] | None = None,
) -> list[str]:
    normalized_keywords = [
        keyword.lower()
        for keyword in sorted(keywords)
        if len(keyword) >= 3 and not keyword.endswith(".md")
    ]
    if not normalized_keywords:
        return []
    candidate_set = set(files)
    hits = git_grep_files(
        repo_path,
        normalized_keywords,
        pathspecs=pathspecs or files[:REVIEW_SCAN_FILE_LIMIT],
        limit=limit * 4,
    )
    return [path for path in hits if path in candidate_set and is_source_like_file(path)][:limit]


def git_grep_files(
    repo_path: Path,
    patterns: list[str],
    pathspecs: list[str],
    limit: int = 12,
    timeout: int = 10,
) -> list[str]:
    bounded_pathspecs = list(dict.fromkeys(pathspecs))[:REVIEW_SCAN_FILE_LIMIT]
    if not patterns or not bounded_pathspecs or not repo_path.exists():
        return []
    args = ["grep", "-Il", "-i"]
    for pattern in patterns[:30]:
        args.extend(["-e", pattern])
    args.extend(["--", *bounded_pathspecs])
    output = run_git(repo_path, args, timeout=timeout)
    if not output:
        return []
    return output.splitlines()[:limit]


def review_execution_status(state: dict[str, Any]) -> str:
    if state["status"] != "active":
        return "not scheduled"
    if not state["exists"]:
        return "blocked: missing local clone"
    if state["review_blocking_dirty_count"]:
        return "blocked: non-helper local changes"
    return "executed"


def gap_label(severity: str) -> str:
    if severity in {"material", "blocks testing", "blocks live use"}:
        return "yes"
    if severity == "needs human decision":
        return "needs human decision"
    return "no"


def build_review_execution(state: dict[str, Any]) -> dict[str, Any]:
    repo_path = Path(state["local_path"])
    tracked_files = tracked_repo_files(repo_path)
    evidence_files = [path for path in tracked_files if not is_evidence_noise_file(path)]
    implementation_files = [path for path in evidence_files if is_implementation_file(path)]
    test_files = [path for path in evidence_files if is_test_file(path)]
    implementation_scan_files = implementation_files[:REVIEW_SCAN_FILE_LIMIT]
    test_scan_files = test_files[:REVIEW_SCAN_FILE_LIMIT]
    smoke_name_files = [path for path in test_files if SMOKE_TEST_RE.search(path)]
    smoke_content_files = [
        path
        for path in git_grep_files(
            repo_path,
            ["smoke", "e2e", "end-to-end", "integration", "live"],
            pathspecs=test_scan_files,
            limit=20,
        )
        if path in set(test_files)
    ]
    smoke_test_files = list(dict.fromkeys([*smoke_name_files, *smoke_content_files]))[:10]
    workflow_files = [
        path
        for path in tracked_files
        if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))
    ]
    integration_name_files = [
        path for path in implementation_files if STATE_INTEGRATION_RE.search(path)
    ][:12]
    integration_content_files = [
        path
        for path in git_grep_files(
            repo_path,
            [
                "api",
                "client",
                "database",
                "github",
                "integration",
                "persist",
                "provider",
                "source",
                "state",
                "store",
                "token",
                "workflow",
            ],
            pathspecs=implementation_scan_files,
            limit=40,
        )
        if path in set(implementation_files)
    ]
    integration_files = list(dict.fromkeys([*integration_name_files, *integration_content_files]))[
        :12
    ]
    design_headings = {
        rel_path: markdown_headings(repo_path, rel_path) for rel_path in state["design_files"][:6]
    }
    domain_hits = keyword_file_hits(
        repo_path,
        implementation_files,
        repo_domain_keywords(
            RepoConfig(
                repo=state["repo"],
                local_path=Path(state["local_path"]).name,
                status=state["status"],
                cadence=state["cadence"],
                decision_anchor=state["decision_anchor"],
            )
        ),
        pathspecs=implementation_scan_files,
    )
    status = review_execution_status(state)
    dimensions: list[dict[str, Any]] = []

    if not state["design_files"]:
        design_severity = "blocks testing"
        design_finding = (
            "No tracked design sources were found; the design contract is not reviewable."
        )
    else:
        design_severity = "none"
        design_finding = f"Collected {state['design_source_count']} design sources and registry anchor for comparison."
    dimensions.append(
        {
            "id": "design_contract",
            "label": "Design Contract",
            "evidence": [
                f"Decision anchor: {state['decision_anchor'] or 'none recorded'}",
                f"Design sources: {state['design_source_count']}",
                *[
                    f"{rel_path}: {', '.join(headings[:4]) if headings else 'no headings found'}"
                    for rel_path, headings in design_headings.items()
                ],
            ],
            "finding": design_finding,
            "gap_severity": design_severity,
            "issue_draft_needed": gap_label(design_severity),
        }
    )

    if not implementation_files:
        implementation_severity = "blocks testing"
        implementation_finding = "No source-like implementation files were detected."
    elif not domain_hits:
        implementation_severity = "needs human decision"
        implementation_finding = (
            "Implementation files exist, but the automated keyword pass did not map repo-domain terms "
            "to code paths; a semantic review should confirm coverage."
        )
    else:
        implementation_severity = "needs human decision"
        implementation_finding = (
            "Implementation files and repo-domain code hits were found; semantic review must verify "
            "whether these paths satisfy the design contract."
        )
    dimensions.append(
        {
            "id": "implementation_coverage",
            "label": "Implementation Coverage",
            "evidence": [
                f"Source-like implementation files: {len(implementation_files)}",
                f"Implementation areas: {', '.join(format_implementation_areas(state['implementation_areas'])) or 'none'}",
                f"Domain keyword hits: {', '.join(domain_hits) if domain_hits else 'none'}",
            ],
            "finding": implementation_finding,
            "gap_severity": implementation_severity,
            "issue_draft_needed": gap_label(implementation_severity),
        }
    )

    if not test_files and not workflow_files:
        test_severity = "blocks testing"
        test_finding = "No tests or CI workflow files were detected."
    elif not smoke_test_files:
        test_severity = "material"
        test_finding = "Tests or workflows exist, but the automated pass did not find smoke/e2e/live readiness markers."
    else:
        test_severity = "needs human decision"
        test_finding = "Test and smoke/integration markers exist; review must verify they prove the intended user journey."
    dimensions.append(
        {
            "id": "test_and_live_readiness",
            "label": "Test And Live Readiness",
            "evidence": [
                f"Test files: {len(test_files)}",
                f"Workflow files: {len(workflow_files)}",
                f"Smoke/e2e/live markers: {', '.join(smoke_test_files) if smoke_test_files else 'none'}",
            ],
            "finding": test_finding,
            "gap_severity": test_severity,
            "issue_draft_needed": gap_label(test_severity),
        }
    )

    if not integration_files and not workflow_files:
        integration_severity = "material"
        integration_finding = "No integration/state/workflow evidence was detected."
    else:
        integration_severity = "needs human decision"
        integration_finding = (
            "Integration/state/workflow evidence was found; review must confirm persistence, provider, "
            "and cross-repo behavior against the design contract."
        )
    dimensions.append(
        {
            "id": "integration_and_state",
            "label": "Integration And State",
            "evidence": [
                f"Integration/state files: {', '.join(integration_files) if integration_files else 'none'}",
                f"Workflow files: {', '.join(workflow_files[:10]) if workflow_files else 'none'}",
            ],
            "finding": integration_finding,
            "gap_severity": integration_severity,
            "issue_draft_needed": gap_label(integration_severity),
        }
    )

    findings = state.get("round1_findings")
    round1_candidate_count = (
        len(findings.get("candidates") or []) if isinstance(findings, dict) else 0
    )
    if findings and round1_candidate_count:
        issue_severity = "needs human decision"
        issue_finding = (
            "Round-1 candidates are queued; the human decision is whether to approve them as-is, "
            "revise, defer, drop, or send back for deeper review."
        )
    elif findings and findings.get("deeper_review_needed"):
        issue_severity = "material"
        issue_finding = (
            "Round 1 requested deeper review; do not accept no-new-issues from this state."
        )
    elif findings:
        issue_severity = "needs human decision"
        issue_finding = (
            "Round 1 produced no candidates. Verify the no_new_work_justification before accepting "
            "no-new-issues; archive-progress and remote-progress entries are dedup signal only, not "
            "evidence of completion."
        )
    else:
        issue_severity = "needs human decision"
        issue_finding = (
            "Round 1 has not run for this repo. Run the round-1 reviewer agent against "
            "review-inputs.md before approving any issues for this cycle."
        )
    dimensions.append(
        {
            "id": "issue_generation",
            "label": "Issue Generation",
            "evidence": [
                f"Round 1 findings: {'present' if findings else 'not yet run'}",
                f"Round 1 candidates: {round1_candidate_count}",
                f"Archive progress entries (dedup-only): {state.get('archive_progress_count', 0)}",
                f"Remote open issues: {state['remote_open_issue_count'] if state['remote_open_issue_count'] is not None else 'unknown'}",
            ],
            "finding": issue_finding,
            "gap_severity": issue_severity,
            "issue_draft_needed": gap_label(issue_severity),
        }
    )

    gap_count = sum(
        1
        for dimension in dimensions
        if dimension["gap_severity"] in {"material", "blocks testing", "blocks live use"}
    )
    decision_count = sum(
        1 for dimension in dimensions if dimension["gap_severity"] == "needs human decision"
    )
    return {
        "status": status,
        "dimensions": dimensions,
        "gap_count": gap_count,
        "needs_decision_count": decision_count,
        "tracked_file_count": len(tracked_files),
        "implementation_file_count": len(implementation_files),
        "test_file_count": len(test_files),
        "workflow_file_count": len(workflow_files),
        "summary": (
            f"Execution status: {status}; material/blocking automated gaps: {gap_count}; "
            f"dimensions needing semantic decision: {decision_count}."
        ),
    }


def remote_open_issue_count(repo: str) -> int | None:
    if shutil.which("gh") is None:
        return None
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--limit",
                "200",
                "--json",
                "number",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    return len(payload)


def collect_remote_progress(
    repo: str,
    *,
    open_issue_limit: int = 100,
    merged_pr_lookback_days: int = 30,
    merged_pr_limit: int = 50,
) -> dict[str, Any]:
    """Collect open GitHub issues + recently-merged PRs for round-1 dedup.

    The output is a dict with:
      - `open_issues`: list of {number, title, labels, created_at}
      - `recent_merged_prs`: list of {number, title, merged_at}
      - `available`: bool — false when `gh` is missing or auth fails.
      - `lookback_days`: how far back the merged-PR query went.

    The agent uses this to recognize "this gap is already an open issue or
    already shipped in a recent PR" before raising it as a candidate.
    """
    result: dict[str, Any] = {
        "available": False,
        "lookback_days": merged_pr_lookback_days,
        "open_issues": [],
        "recent_merged_prs": [],
        "warnings": [],
    }
    if shutil.which("gh") is None:
        result["warnings"].append("gh CLI not available; remote progress unknown")
        return result

    def _gh_json(args: list[str], timeout: int = 30) -> Any:
        try:
            proc = subprocess.run(
                args, check=False, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return None
        if proc.returncode != 0:
            return None
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None
        return payload

    issues_payload = _gh_json(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            str(open_issue_limit),
            "--json",
            "number,title,labels,createdAt",
        ]
    )
    if isinstance(issues_payload, list):
        result["available"] = True
        for item in issues_payload:
            labels = item.get("labels") or []
            label_names = [
                str(label.get("name", ""))
                for label in labels
                if isinstance(label, dict) and label.get("name")
            ]
            result["open_issues"].append(
                {
                    "number": item.get("number"),
                    "title": str(item.get("title", "")),
                    "labels": label_names,
                    "created_at": str(item.get("createdAt", "")),
                }
            )
    else:
        result["warnings"].append("gh issue list failed or returned non-list")

    cutoff_date = (datetime.now(UTC).date() - timedelta(days=merged_pr_lookback_days)).isoformat()
    pr_payload = _gh_json(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "merged",
            "--search",
            f"merged:>={cutoff_date}",
            "--limit",
            str(merged_pr_limit),
            "--json",
            "number,title,mergedAt",
        ]
    )
    if isinstance(pr_payload, list):
        for item in pr_payload:
            result["recent_merged_prs"].append(
                {
                    "number": item.get("number"),
                    "title": str(item.get("title", "")),
                    "merged_at": str(item.get("mergedAt", "")),
                }
            )
    else:
        result["warnings"].append("gh pr list (merged) failed or returned non-list")

    return result


def load_round1_findings(output_dir: Path | None, repo: str) -> dict[str, Any] | None:
    """Load the most recent round-1 findings.json for `repo` if any exist.

    Looks in `<output_dir>/round1/<agent>/<repo_safe>/findings.json` across
    all agent subdirectories and returns the newest by mtime. Returns None if
    no findings exist yet.

    Note: when `<output_dir>/round2/<repo_safe>/converged.json` exists, the
    evaluator uses that as the candidate source instead — round 1 findings
    are then preserved only as audit-trail context.
    """
    if output_dir is None:
        return None
    safe_name = repo.replace("/", "__")
    round1_root = output_dir / "round1"
    if not round1_root.is_dir():
        return None
    candidates: list[tuple[float, Path]] = []
    for agent_dir in round1_root.iterdir():
        if not agent_dir.is_dir():
            continue
        findings_path = agent_dir / safe_name / "findings.json"
        if findings_path.is_file():
            candidates.append((findings_path.stat().st_mtime, findings_path))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    newest = candidates[0][1]
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    data["__source_path"] = str(newest)
    return data


def load_round2_converged(output_dir: Path | None, repo: str) -> dict[str, Any] | None:
    """Load the round-2 converged set for `repo` if it exists.

    Looks at `<output_dir>/round2/<repo_safe>/converged.json`. Returns None
    when round 2 hasn't completed yet — the evaluator then falls back to the
    most-recent round-1 findings.

    The converged set is the source of truth once round 2 finishes: it
    contains the negotiated per-instance candidates, any meta-candidate, and
    the deadlocked items that need human attention.
    """
    if output_dir is None:
        return None
    safe_name = repo.replace("/", "__")
    converged_path = output_dir / "round2" / safe_name / "converged.json"
    if not converged_path.is_file():
        return None
    try:
        data = json.loads(converged_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    data["__source_path"] = str(converged_path)
    return data


def load_registry(path: Path) -> tuple[Path, list[str], list[RepoConfig], list[Path]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    workspace_root = Path(data.get("workspace_root", "."))
    if not workspace_root.is_absolute():
        workspace_root = (path.parent.parent / workspace_root).resolve()

    excluded = [str(item).lower() for item in data.get("excluded_repo_names", [])]
    archive_paths = [
        Path(item).expanduser() for item in data.get("archive_review", {}).get("paths", [])
    ]
    repos: list[RepoConfig] = []
    seen: set[str] = set()
    for raw in data.get("repos", []):
        repo = str(raw["repo"])
        repo_name = repo.rsplit("/", 1)[-1].lower()
        local_name = str(raw["local_path"]).lower()
        if repo_name in excluded or local_name in excluded:
            continue
        if repo in seen:
            continue
        seen.add(repo)
        status = str(raw.get("status", "paused"))
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status for {repo}: {status}")
        repos.append(
            RepoConfig(
                repo=repo,
                local_path=str(raw["local_path"]),
                status=status,
                cadence=str(raw.get("cadence", "manual")),
                decision_anchor=str(raw.get("decision_anchor", "")).strip(),
            )
        )
    return workspace_root, excluded, repos, archive_paths


def load_json_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected object in {path}")
    return data


def gitnexus_meta_candidates(workspace_root: Path, repo_path: Path, repo: RepoConfig) -> list[Path]:
    repo_name = repo.repo.rsplit("/", 1)[-1]
    candidates = [
        repo_path / ".gitnexus" / "meta.json",
        workspace_root / repo_name / ".gitnexus" / "meta.json",
    ]
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(candidate)
    return unique


def collect_gitnexus_map(workspace_root: Path, repo_path: Path, repo: RepoConfig) -> dict[str, Any]:
    head_commit = run_git(repo_path, ["rev-parse", "HEAD"])
    for meta_path in gitnexus_meta_candidates(workspace_root, repo_path, repo):
        if not meta_path.is_file():
            continue
        meta = load_json_config(meta_path)
        indexed_commit = str(meta.get("lastCommit", ""))
        if head_commit and indexed_commit:
            status = "current" if head_commit == indexed_commit else "stale"
        else:
            status = "available"
        stats = meta.get("stats") if isinstance(meta.get("stats"), dict) else {}
        # A commit-current map with embeddings: 0 forces every reviewer to fall
        # back to Cypher because natural-language `gitnexus query` returns
        # nothing — that's a degraded map, not a complete one. Surface it so
        # the preflight refreshes the map with --embeddings.
        embeddings_count = stats.get("embeddings", 0) if isinstance(stats, dict) else 0
        try:
            needs_embeddings = int(embeddings_count) <= 0
        except (TypeError, ValueError):
            needs_embeddings = True
        return {
            "status": status,
            "meta_path": str(meta_path),
            "repo_path": str(meta.get("repoPath", "")),
            "indexed_at": str(meta.get("indexedAt", "")),
            "indexed_commit": indexed_commit,
            "head_commit": head_commit,
            "remote_url": str(meta.get("remoteUrl", "")),
            "stats": stats,
            "needs_embeddings": needs_embeddings,
            "usage": (
                "Use GitNexus MCP query/context for deeper semantic review; the evaluator "
                "reads only meta.json and never parses the binary local map."
            ),
        }
    return {
        "status": "missing",
        "meta_path": "",
        "repo_path": str(repo_path),
        "indexed_at": "",
        "indexed_commit": "",
        "head_commit": head_commit,
        "remote_url": "",
        "stats": {},
        "needs_embeddings": True,
        "usage": "No local GitNexus meta.json was found for this repo.",
    }


def run_gitnexus_analyze(
    repo_path: Path,
    gitnexus_bin: str,
    *,
    with_embeddings: bool = True,
    force: bool = False,
    timeout: int = 900,
) -> tuple[bool, str]:
    """Run `gitnexus analyze` for a repo.

    Embeddings are enabled by default because round-1 reviewer agents rely on
    natural-language `gitnexus query` to corroborate or contradict their
    direct-file inspection — a map without embeddings forces every reviewer to
    fall back to Cypher, which is fine but loses the easy-mode discovery path.

    `force=True` is required when the indexed commit already matches HEAD but
    the existing map is degraded (e.g., embeddings: 0); without it, analyze
    short-circuits with "Already up to date" and the degraded map is preserved.
    """
    cmd = [gitnexus_bin, "analyze", str(repo_path), "--skip-agents-md"]
    if with_embeddings:
        cmd.append("--embeddings")
    if force:
        cmd.append("--force")
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    return result.returncode == 0, output


def gitnexus_preflight(
    workspace_root: Path,
    repos: list[RepoConfig],
    statuses: set[str],
    *,
    refresh_stale: bool,
    gitnexus_bin: str,
) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    refreshed: list[str] = []
    attempted_refresh: list[str] = []
    gitnexus_available = shutil.which(gitnexus_bin) is not None
    for repo in repos:
        if repo.status not in statuses or repo.status != "active":
            continue
        repo_path = workspace_root / repo.local_path
        before = collect_gitnexus_map(workspace_root, repo_path, repo)
        after = before
        refresh_status = "not-needed"
        refresh_error = ""
        needs_refresh = before["status"] in GITNEXUS_REFRESH_STATUSES or before.get(
            "needs_embeddings", False
        )
        if needs_refresh:
            reason = (
                before["status"]
                if before["status"] in GITNEXUS_REFRESH_STATUSES
                else "missing-embeddings"
            )
            if not refresh_stale:
                refresh_status = "needed-not-requested"
                warnings.append(
                    f"{repo.repo} GitNexus map needs refresh ({reason}); run with stale-map refresh before relying on graph context."
                )
            elif not gitnexus_available:
                refresh_status = "skipped-missing-cli"
                warnings.append(
                    f"{repo.repo} GitNexus map is {before['status']}, but `{gitnexus_bin}` is not available."
                )
            else:
                attempted_refresh.append(repo.repo)
                # When the commit is already current but embeddings are absent,
                # `gitnexus analyze` short-circuits without rebuilding unless
                # we pass --force. Stale (commit-mismatched) maps don't need it.
                force_rebuild = before["status"] == "current" and before.get(
                    "needs_embeddings", False
                )
                ok, refresh_output = run_gitnexus_analyze(
                    repo_path, gitnexus_bin, force=force_rebuild
                )
                if ok:
                    after = collect_gitnexus_map(workspace_root, repo_path, repo)
                    refresh_status = "refreshed"
                    refreshed.append(repo.repo)
                    if after["status"] != "current":
                        warnings.append(
                            f"{repo.repo} GitNexus refresh completed but map status is {after['status']}."
                        )
                else:
                    refresh_status = "failed"
                    refresh_error = (
                        refresh_output.splitlines()[-1] if refresh_output else "unknown error"
                    )
                    warnings.append(f"{repo.repo} GitNexus refresh failed: {refresh_error}")
        records[repo.repo] = {
            "before": before,
            "after": after,
            "refresh_status": refresh_status,
            "refresh_error": refresh_error,
        }
    stale_after = [
        repo
        for repo, record in records.items()
        if record["after"]["status"] in GITNEXUS_REFRESH_STATUSES
    ]
    return {
        "enabled": True,
        "refresh_stale": refresh_stale,
        "gitnexus_bin": gitnexus_bin,
        "gitnexus_available": gitnexus_available,
        "records": records,
        "warnings": warnings,
        "refreshed": refreshed,
        "attempted_refresh": attempted_refresh,
        "stale_after": stale_after,
    }


def repo_aliases(repo: RepoConfig) -> set[str]:
    name = repo.repo.rsplit("/", 1)[-1]
    aliases = {
        name,
        name.replace("-", " "),
        name.replace("_", " "),
        name.replace("-", "_"),
        name.replace("_", "-"),
    }
    lower_name = name.lower()
    if lower_name == "travel-plan-permission":
        aliases.update({"TPP", "Travel Plan Permission"})
    elif lower_name == "trend_model_project":
        aliases.update({"Trend", "Trend Model", "Trend Modeling Project"})
    elif lower_name == "portable-alpha-extension-model":
        aliases.update({"Portable Alpha", "Portable Alpha Extension"})
    elif lower_name == "counter_risk":
        aliases.update({"Counter Risk"})
    elif lower_name == "manager-database":
        aliases.update({"Manager Database"})
    elif lower_name == "pension-data":
        aliases.update({"Pension Data"})
    elif lower_name == "trip-planner":
        aliases.update({"Trip Planner"})
    return {alias.lower() for alias in aliases if alias}


def repo_domain_keywords(repo: RepoConfig) -> set[str]:
    name = repo.repo.rsplit("/", 1)[-1].lower()
    keywords_by_repo = {
        "workflows": {
            "agents.md",
            "agent docs",
            "claude.md",
            "workflow",
            "workflow catalog",
            "sync manifest",
            "verify:create-new-pr",
            "agents-verifier",
            "reusable",
        },
        "travel-plan-permission": {
            "approval",
            "business proposal",
            "evaluation result",
            "langgraph",
            "mint/use a planner token",
            "orchestration",
            "planner token",
            "policy",
            "proposal",
            "tpp",
            "travel-plan-permission",
        },
        "trend_model_project": {
            "forecast",
            "monte carlo",
            "requests pin",
            "streamlit",
            "trend",
            "trend_model_project",
        },
        "portable-alpha-extension-model": {
            "extension model",
            "llm",
            "portable alpha",
            "reference pack",
        },
        "counter_risk": {
            "counterparty",
            "counter risk",
            "counter_risk",
            "date semantics",
            "reconciliation",
            "risk report",
            "vba",
        },
        "manager-database": {
            "alerts",
            "manager database",
            "query chain",
            "rag",
            "review follow-up",
        },
        "inv-man-intake": {
            "inv-man",
            "inv-man-intake",
            "investment manager",
            "manager intake",
        },
        "pension-data": {
            "extraction",
            "pension",
            "saved view",
            "source authority",
            "staging readiness",
            "ui/langchain",
        },
        "collab-admin": {"admin dashboard", "collab-admin"},
        "workflows-integration-tests": {"integration-test", "workflows-integration-tests"},
        "trip-planner": {
            "accommodations",
            "airfares",
            "business-mode",
            "business trip",
            "daily activities",
            "frontend conversation",
            "inventory",
            "leisure",
            "map",
            "planner",
            "preference",
            "recreational",
            "route geometry",
            "scenario",
            "travel",
            "traveler",
            "trip-planner",
            "workspace",
        },
    }
    return repo_aliases(repo) | keywords_by_repo.get(name, set())


def text_contains_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.lower()
    if not phrase:
        return False
    if re.fullmatch(r"[\w-]+", phrase):
        return re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", text) is not None
    return phrase in text


def candidate_matches_repo(candidate: ArchiveCandidate, repo: RepoConfig) -> bool:
    text = "\n".join([candidate.title, candidate.excerpt]).lower()
    return any(text_contains_phrase(text, keyword) for keyword in repo_domain_keywords(repo))


def is_repo_review_session(user_text: str) -> bool:
    if not REVIEW_PROMPT_RE.search(user_text):
        return False
    return not (
        MAINTENANCE_SESSION_RE.search(user_text) and not STRICT_REVIEW_PROMPT_RE.search(user_text)
    )


def content_text(content: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            parts.append(
                item.get("text") or item.get("input_text") or item.get("output_text") or ""
            )
    return "\n".join(part for part in parts if part)


def archive_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".jsonl":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.glob("*.jsonl")))
    return sorted(set(files))


def normalize_issue_title(text: str, max_length: int = 200) -> str:
    title = text.strip().rstrip(".")
    title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
    title = re.sub(r"`([^`]+)`", r"\1", title)
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"^(?:then\s+)", "", title, flags=re.I)
    title = title.strip(" -–—|:")
    if len(title) <= max_length:
        return title

    sentence = re.split(r"(?<=[.!?])\s+", title, maxsplit=1)[0].rstrip(".")
    if 12 <= len(sentence) <= max_length:
        return sentence

    shortened = title[:max_length].rsplit(" ", 1)[0].strip(" -–—|:")
    if shortened:
        return shortened
    return title


def title_from_recommendation(text: str) -> str:
    title = normalize_issue_title(text, max_length=400)
    first_sentence = re.split(r"(?<=[.!?])\s+", title, maxsplit=1)[0].rstrip(".")
    if 12 <= len(first_sentence) <= 200:
        return normalize_issue_title(first_sentence)
    return normalize_issue_title(title)


def extract_archive_candidates(
    text: str, source_file: Path, thread_name: str, timestamp: str
) -> list[ArchiveCandidate]:
    candidates: list[ArchiveCandidate] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        match = ARCHIVE_RECOMMENDATION_RE.match(stripped)
        if not match:
            continue
        title = title_from_recommendation(match.group("title"))
        lowered = title.lower()
        if not re.search(
            r"\b(add|define|wire|test|ship|replace|implement|persist|harden|document|create|fix)\b",
            lowered,
        ):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        candidates.append(
            ArchiveCandidate(
                title=title,
                source_file=str(source_file),
                thread_name=thread_name or "untitled",
                timestamp=timestamp,
                excerpt=stripped,
            )
        )
    return candidates


def collect_archive_candidates(
    archive_paths: list[Path], repos: list[RepoConfig]
) -> dict[str, list[ArchiveCandidate]]:
    candidates_by_repo: dict[str, list[ArchiveCandidate]] = {repo.repo: [] for repo in repos}
    for path in archive_files(archive_paths):
        timestamp = ""
        thread_name = ""
        user_texts: list[str] = []
        assistant_texts: list[str] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = item.get("payload") or {}
            if item.get("type") == "session_meta":
                timestamp = payload.get("timestamp", "")
            elif item.get("type") == "event_msg" and payload.get("type") == "thread_name_updated":
                thread_name = payload.get("thread_name", "")
            elif item.get("type") == "event_msg" and payload.get("type") == "user_message":
                message = payload.get("message", "")
                if not message.startswith("Automation:"):
                    user_texts.append(message)
            elif item.get("type") == "event_msg" and payload.get("type") == "agent_message":
                assistant_texts.append(payload.get("message", ""))
            elif (
                item.get("type") == "response_item"
                and payload.get("type") == "message"
                and payload.get("role") == "assistant"
            ):
                assistant_texts.append(content_text(payload.get("content") or []))

        user_text = "\n".join(user_texts)
        if not is_repo_review_session(user_text):
            continue
        session_candidates = extract_archive_candidates(
            "\n".join(assistant_texts), path, thread_name, timestamp
        )
        if not session_candidates:
            continue
        for repo in repos:
            matched_candidates = [
                candidate
                for candidate in session_candidates
                if candidate_matches_repo(candidate, repo)
            ]
            candidates_by_repo[repo.repo].extend(matched_candidates)

    deduped: dict[str, list[ArchiveCandidate]] = {}
    for repo_name, candidates in candidates_by_repo.items():
        seen_titles: set[str] = set()
        deduped[repo_name] = []
        for candidate in sorted(candidates, key=lambda item: item.timestamp, reverse=True):
            key = candidate.title.lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            deduped[repo_name].append(candidate)
    return deduped


def split_issue_entries(text: str) -> list[tuple[int, str, str]]:
    entries: list[tuple[int, str, str]] = []
    current_num: int | None = None
    current_title = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("# "):
            continue
        match = ISSUE_HEADING_RE.match(line.strip())
        if match:
            if current_num is not None:
                entries.append((current_num, current_title, "\n".join(current_lines).strip()))
            current_num = int(match.group("num"))
            current_title = match.group("title").strip().rstrip("|").strip()
            current_lines = [line]
            continue
        if current_num is not None:
            current_lines.append(line)

    if current_num is not None:
        entries.append((current_num, current_title, "\n".join(current_lines).strip()))
    return entries


def extract_issue_drafts(issues_path: Path) -> list[IssueDraft]:
    if not issues_path.is_file():
        return []
    text = issues_path.read_text(encoding="utf-8")
    drafts: list[IssueDraft] = []
    for number, title, body in split_issue_entries(text):
        open_tasks = len(re.findall(r"\[\s\]", body))
        done_tasks = len(re.findall(r"\[[xX]\]", body))
        if open_tasks == 0:
            continue
        drafts.append(
            IssueDraft(
                number=number,
                title=title,
                body=body,
                open_tasks=open_tasks,
                done_tasks=done_tasks,
            )
        )
    return drafts


def collect_repo_state(
    workspace_root: Path,
    repo: RepoConfig,
    archive_candidates: list[ArchiveCandidate] | None = None,
    review_profile: dict[str, Any] | None = None,
    feedback_decision: dict[str, Any] | None = None,
    gitnexus_preflight_record: dict[str, Any] | None = None,
    output_dir: Path | None = None,
    round1_findings: dict[str, Any] | None = None,
    remote_progress: dict[str, Any] | None = None,
    round2_converged: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo_path = workspace_root / repo.local_path
    status_lines = run_git(repo_path, ["status", "--short"]).splitlines()
    material_lines = material_status_lines(status_lines)
    helper_lines = helper_status_lines(status_lines, repo_path)
    blocking_lines = review_blocking_status_lines(status_lines, repo_path)
    branch = run_git(repo_path, ["branch", "--show-current"])
    origin = run_git(repo_path, ["remote", "get-url", "origin"])
    last_commit = run_git(repo_path, ["log", "-1", "--format=%cs %h %s"])
    # Issues.txt is intentionally NOT ingested as a candidate source under the
    # new design. It exists as template scratch for direct-on-repo work and is
    # irrelevant to weekly review evaluation. Helper-dirty classification still
    # ignores Issues.txt edits so they don't block review.
    design_files = collect_design_files(repo_path)
    implementation_areas = collect_implementation_areas(repo_path)
    report_files = (
        sorted((repo_path / "docs" / "reports").rglob("*.md"))
        if (repo_path / "docs" / "reports").is_dir()
        else []
    )

    # Archive items are now PROGRESS-RECOGNITION signal only (for dedup against
    # already-discussed/already-shipped work) — never a candidate source.
    archive_progress_items = archive_candidates or []
    review_profile = review_profile or {}
    feedback_decision = feedback_decision or {}
    gitnexus_preflight_record = gitnexus_preflight_record or {}
    if round2_converged is None:
        round2_converged = load_round2_converged(output_dir, repo.repo)
    if round1_findings is None:
        round1_findings = load_round1_findings(output_dir, repo.repo)
    if remote_progress is None and repo.status == "active":
        remote_progress = collect_remote_progress(repo.repo)
    elif remote_progress is None:
        remote_progress = {
            "available": False,
            "lookback_days": 0,
            "open_issues": [],
            "recent_merged_prs": [],
            "warnings": ["remote progress not collected for non-active repo"],
        }
    current_review_status = review_status(repo, repo_path, blocking_lines)
    current_issue_queue_status = issue_queue_status(round1_findings, round2_converged)

    state = {
        "repo": repo.repo,
        "local_path": str(repo_path),
        "status": repo.status,
        "cadence": repo.cadence,
        "decision_anchor": repo.decision_anchor,
        "review_profile": review_profile,
        "feedback_decision": feedback_decision,
        "gitnexus_preflight": gitnexus_preflight_record,
        "gitnexus_map": collect_gitnexus_map(workspace_root, repo_path, repo),
        "exists": repo_path.exists(),
        "origin": origin,
        "branch": branch,
        "last_commit": last_commit,
        "dirty_count": len(status_lines),
        "material_dirty_count": len(material_lines),
        "helper_dirty_count": len(helper_lines),
        "review_blocking_dirty_count": len(blocking_lines),
        "generated_dirty_count": len(status_lines) - len(material_lines),
        "dirty_preview": status_lines[:15],
        "material_dirty_preview": material_lines[:15],
        "helper_dirty_preview": helper_lines[:15],
        "review_blocking_dirty_preview": blocking_lines[:15],
        "remote_open_issue_count": (
            len(remote_progress.get("open_issues", []))
            if remote_progress.get("available")
            else None
        ),
        "remote_progress": remote_progress,
        "round1_findings": round1_findings,
        "round2_converged": round2_converged,
        "review_status": current_review_status,
        "issue_queue_status": current_issue_queue_status,
        "issue_draft_count": 0,
        "archive_progress_count": len(archive_progress_items),
        # Kept for backward-compat with downstream callers that read this name.
        "archive_candidate_count": len(archive_progress_items),
        "issue_open_task_count": 0,
        "issue_done_task_count": 0,
        "design_files": design_files,
        "design_source_count": len(design_files),
        "implementation_areas": implementation_areas,
        "report_files": [str(path.relative_to(repo_path)) for path in report_files[:10]],
        "decision": current_review_status,
        "review_dimensions": list(REVIEW_DIMENSIONS),
        # Always empty under the new design; preserved as a state field for
        # backward-compat with callers expecting the key.
        "drafts": [],
        # Archive items recorded for dedup/progress display, NOT as candidates.
        "archive_progress": [
            {
                "title": candidate.title,
                "source_file": candidate.source_file,
                "thread_name": candidate.thread_name,
                "timestamp": candidate.timestamp,
                "excerpt": candidate.excerpt,
            }
            for candidate in archive_progress_items
        ],
        # Backward-compat alias of archive_progress; downstream readers can
        # transition off of this name in a future cleanup.
        "archive_candidates": [
            {
                "title": candidate.title,
                "source_file": candidate.source_file,
                "thread_name": candidate.thread_name,
                "timestamp": candidate.timestamp,
                "excerpt": candidate.excerpt,
            }
            for candidate in archive_progress_items
        ],
    }
    state["review_execution"] = build_review_execution(state)
    if state["review_execution"]["status"] == "executed":
        state["review_status"] = EXECUTED_REVIEW_STATUS
        state["decision"] = EXECUTED_REVIEW_STATUS
    state["decision_brief"] = build_decision_brief(state)
    return state


def markdown_list(items: list[str], empty: str = "None found.") -> str:
    if not items:
        return empty
    return "\n".join(f"- `{item}`" for item in items)


def markdown_bullets(items: list[str], empty: str = "None recorded.") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def markdown_review_evidence_traces(traces: list[dict[str, Any]]) -> str:
    if not traces:
        return "None recorded."
    lines: list[str] = []
    for index, trace in enumerate(traces, start=1):
        design_refs = ", ".join(str(item) for item in trace.get("design_refs", [])) or "none"
        implementation_refs = (
            ", ".join(str(item) for item in trace.get("implementation_refs", [])) or "none"
        )
        test_values = trace.get("test_refs", [])
        readiness_values = trace.get("readiness_refs", [])
        if not isinstance(test_values, list):
            test_values = [test_values]
        if not isinstance(readiness_values, list):
            readiness_values = [readiness_values]
        test_refs = ", ".join(str(item) for item in [*test_values, *readiness_values]) or "none"
        lines.extend(
            [
                f"{index}. {trace.get('gap', 'No gap recorded.')}",
                f"   - Current state: {trace.get('current_state', 'None recorded.')}",
                f"   - Required change: {trace.get('required_change', 'None recorded.')}",
                f"   - Design refs: `{design_refs}`",
                f"   - Implementation refs: `{implementation_refs}`",
                f"   - Test/readiness refs: `{test_refs}`",
            ]
        )
    return "\n".join(lines)


def review_evidence_trace_template() -> str:
    return "\n".join(
        [
            '    "review_evidence_traces": [',
            "      {",
            '        "candidate_title_patterns": ["^Candidate title regex$"],',
            '        "gap": "Specific unmet design/readiness commitment.",',
            '        "current_state": "What the current code/tests actually prove today.",',
            '        "required_change": "What must change to close the gap.",',
            '        "design_refs": ["README.md", "docs/design.md"],',
            '        "implementation_refs": ["src/module.py"],',
            '        "test_refs": ["tests/test_expected_behavior.py"]',
            "      }",
            "    ]",
        ]
    )


def process_chain_checkpoint_lines() -> list[str]:
    return [
        "Before changing automation or approving issues, identify the earliest failed stage in this chain:",
        "",
        "1. Inputs: registry, repo status, synced local clone, remote issues, archives, GitNexus map, design docs.",
        "2. Review instructions: the worksheet/profile prompt must require design-vs-implementation comparison, not just file discovery.",
        "3. Evidence collection: the reviewer must inspect design, implementation, tests, integrations, and open issues.",
        "4. Human packet: progress/readiness output must be repo-specific and decision-useful.",
        "5. Issue drafting: every issue must be tied to a verified gap and include concrete agent-ready tasks and acceptance criteria.",
        "6. Upload gate: only approved, formatted, evidence-traced issues can reach GitHub.",
        "7. Coding-agent lanes: opener/closer automation should consume the prioritized issue set without repo-specific hardcoding.",
        "",
        "If a later stage fails, fix the earliest upstream cause that allowed the bad output, not only the visible symptom.",
    ]


def execution_dimension(state: dict[str, Any], dimension_id: str) -> dict[str, Any]:
    for dimension in state["review_execution"]["dimensions"]:
        if dimension["id"] == dimension_id:
            return dimension
    return {
        "id": dimension_id,
        "label": dimension_id,
        "evidence": [],
        "finding": "No automated evidence was recorded for this dimension.",
        "gap_severity": "needs human decision",
        "issue_draft_needed": "needs human decision",
    }


def task_preview(body: str, limit: int = 3) -> list[str]:
    tasks: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if re.search(r"\[\s\]", stripped):
            tasks.append(re.sub(r"^[-*]\s*\[\s\]\s*", "", stripped).strip())
        if len(tasks) >= limit:
            break
    return tasks


def _records_from_round2_candidates(
    raw_candidates: list[Any],
    converged: dict[str, Any],
    *,
    max_items: int | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    source_path = str(converged.get("__source_path", ""))
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue
        title = str(candidate.get("title") or "").strip()
        if not title:
            continue
        scope = str(candidate.get("scope") or "fix")
        origin = candidate.get("origin") if isinstance(candidate.get("origin"), dict) else {}
        agent = str(origin.get("source_agent") or "merged")
        type_label = "round 2 audit" if scope == "audit" else "round 2 finding"
        tasks = candidate.get("tasks") or []
        if not isinstance(tasks, list):
            tasks = []
        task_preview_lines = [str(task) for task in tasks[:3]]
        body = str(candidate.get("body") or "").strip()
        records.append(
            {
                "candidate_index": len(records) + 1,
                "type": type_label,
                "title": normalize_issue_title(title),
                "source": f"round 2 ({agent})",
                "source_detail": source_path,
                "task_count": len(tasks) if tasks else None,
                "task_preview": task_preview_lines,
                "body": body,
                "round1_candidate": candidate,
                "agent": agent,
                "scope": scope,
            }
        )
        if max_items is not None and len(records) >= max_items:
            return records
    return records


def issue_candidate_records(
    state: dict[str, Any], max_items: int | None = 8
) -> list[dict[str, Any]]:
    """Return candidate issue records sourced from the latest negotiated state.

    Precedence:
      1. Round-2 converged set (`converged_candidates` + optional `meta_candidate`).
      2. Round-1 single-agent findings (when round 2 hasn't completed).
      3. Empty (round 1 not yet run).

    Issues.txt drafts and archive entries are NOT candidate sources under the
    new design (Issues.txt is template scratch; archive entries are progress-
    recognition only).
    """
    converged = state.get("round2_converged")
    if isinstance(converged, dict):
        raw_candidates = list(converged.get("converged_candidates") or [])
        meta = converged.get("meta_candidate")
        if isinstance(meta, dict):
            raw_candidates.append(meta)
        return _records_from_round2_candidates(raw_candidates, converged, max_items=max_items)

    findings = state.get("round1_findings") or {}
    raw_candidates = findings.get("candidates") if isinstance(findings, dict) else None
    if not isinstance(raw_candidates, list):
        return []
    records: list[dict[str, Any]] = []
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue
        title = str(candidate.get("title", "")).strip()
        if not title:
            continue
        agent = str(findings.get("agent", "")).strip() or "round1"
        tasks = candidate.get("tasks") or []
        if not isinstance(tasks, list):
            tasks = []
        task_preview_lines = [str(task) for task in tasks[:3]]
        # Prefer an agent-supplied complete issue body when present (the
        # round-1 reviewer SHOULD produce a body that already follows
        # AGENT_ISSUE_FORMAT). Fall back to a placeholder; build_agent_issue_body
        # will then construct a full body from structured fields.
        body = str(candidate.get("body") or "").strip()
        records.append(
            {
                "candidate_index": len(records) + 1,
                "type": "round 1 finding",
                "title": normalize_issue_title(title),
                "source": f"round 1 ({agent})",
                "source_detail": str(findings.get("__source_path", "")),
                "task_count": len(tasks) if tasks else None,
                "task_preview": task_preview_lines,
                "body": body,
                "round1_candidate": candidate,
                "agent": agent,
            }
        )
        if max_items is not None and len(records) >= max_items:
            return records
    return records


def issue_candidate_summaries(
    state: dict[str, Any], max_items: int | None = 8
) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in candidate.items() if key != "body"}
        for candidate in issue_candidate_records(state, max_items=max_items)
    ]


def readiness_summary(state: dict[str, Any]) -> str:
    execution = state["review_execution"]
    if execution["status"] != "executed":
        return "Review execution is blocked; testing or implementation readiness cannot be decided."
    test_dimension = execution_dimension(state, "test_and_live_readiness")
    integration_dimension = execution_dimension(state, "integration_and_state")
    if test_dimension["gap_severity"] in {"material", "blocks testing", "blocks live use"}:
        return (
            "Not ready to approve testing/live implementation without issue work; "
            f"{test_dimension['finding']}"
        )
    return (
        "Testing/live-readiness evidence exists, but approval still requires confirming "
        "that the tests, smoke paths, integrations, and state behavior prove the documented user journey. "
        f"{test_dimension['finding']} {integration_dimension['finding']}"
    )


def issue_set_recommendation(state: dict[str, Any]) -> str:
    execution = state["review_execution"]
    if execution["gap_count"] > 0:
        return (
            "Create or approve issue drafts for the automated material/blocking gaps before "
            "treating the repo as ready."
        )
    converged = state.get("round2_converged")
    if isinstance(converged, dict):
        per_instance = converged.get("converged_candidates") or []
        meta = converged.get("meta_candidate")
        deadlocks = converged.get("deadlocked_candidates") or []
        no_new_work = converged.get("no_new_work_justifications") or []
        if not per_instance and not meta:
            # Both agents independently produced 0 candidates with substantive
            # no-new-work justifications. Review is complete; conclusion is
            # "no new gaps." Surface both agents' justifications for human
            # spot-check before accepting no-new-issues.
            if isinstance(no_new_work, list) and len(no_new_work) >= 2:
                return (
                    f"Round-2 negotiation produced 0 converged candidates. Both agents "
                    f"({', '.join(str(j.get('agent', '?')) for j in no_new_work)}) wrote "
                    "substantive `no_new_work_justification` arguing the active backlog "
                    "covers all design-vs-implementation gaps. Review the dual "
                    "justifications below and accept no-new-issues if the cited file/test "
                    "evidence holds; otherwise mark `revise` or `deeper-review`."
                )
            return (
                "Round-2 negotiation produced 0 converged candidates and the "
                "no_new_work_justifications field is missing or thin — verify the "
                "review actually completed before accepting no-new-issues."
            )
        parts: list[str] = [
            f"Round-2 negotiation produced {len(per_instance)} converged candidate(s)"
        ]
        if isinstance(meta, dict):
            parts.append("plus 1 meta-candidate (audit scope)")
        parts.append(
            "— review the set below, then approve, revise, merge, defer, or drop items repo-by-repo."
        )
        if deadlocks:
            parts.append(
                f"Note: {len(deadlocks)} deadlocked candidate(s) require human resolution; both "
                "agents' positions are surfaced in the deadlocked-candidates section."
            )
        return " ".join(parts)
    findings = state.get("round1_findings")
    if not findings:
        return (
            "Round 1 has not run for this repo. Run the round-1 reviewer agent against "
            "`review-inputs.md` to produce traced candidates; do not infer no-work from absence."
        )
    candidates = findings.get("candidates") or []
    if candidates:
        return (
            "Review the round-1 candidate set below, then approve, revise, merge, defer, or drop "
            "items repo-by-repo. Round-2 negotiation between agents (when both agents have run) "
            "produces the final converged set; this brief shows the latest available round-1 view."
        )
    if findings.get("deeper_review_needed"):
        reason = str(findings.get("deeper_review_reason") or "no reason recorded").strip()
        return f"Round 1 requested deeper review: {reason}"
    return (
        "Round 1 found no design-vs-implementation gaps. Review the round-1 "
        "`no_new_work_justification` against current code/tests before accepting no-new-issues."
    )


def progress_summary(state: dict[str, Any]) -> str:
    execution = state["review_execution"]
    return (
        f"No completed semantic progress review is recorded for {state['repo']}. The automated "
        f"preflight found {state['design_source_count']} design sources, "
        f"{execution['implementation_file_count']} source-like files, "
        f"{execution['test_file_count']} test files, and "
        f"{execution['workflow_file_count']} workflow files; these are review inputs, not a "
        "design-vs-implementation judgment. Run the standard semantic review prompt before "
        "approving issue drafts or deciding that no issues are needed."
    )


def review_summary_quality_errors(brief: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, label in (
        ("progress_summary", "progress summary"),
        ("readiness_summary", "readiness summary"),
    ):
        value = str(brief.get(key) or "").strip()
        if not value:
            errors.append(f"missing {label}")
            continue
        normalized = value.lower()
        for phrase in GENERIC_REVIEW_SUMMARY_PHRASES:
            if phrase in normalized:
                errors.append(f"{label} uses generic automated-review wording: {phrase}")
                break

    if not brief.get("review_focus"):
        errors.append("missing repo-specific review focus")
    if not brief.get("concerns"):
        errors.append("missing repo-specific concerns")
    traces = brief.get("review_evidence_traces") or []
    no_new_work = brief.get("no_new_work_justifications") or []
    # Round-2 may legitimately produce 0 candidates with both agents writing
    # substantive `no_new_work_justification` instead of evidence traces. Both
    # justifications passing the round-1 schema validator already certifies
    # they're concrete (file/test refs, ≥120 chars equivalent). Accept that as
    # an alternative to per-candidate traces — the review IS complete; the
    # conclusion is just "no new gaps."
    has_dual_no_new_work = (
        isinstance(no_new_work, list)
        and len(no_new_work) >= 2
        and all(
            isinstance(entry, dict)
            and entry.get("candidate_count") == 0
            and len(str(entry.get("justification") or "").strip()) >= 200
            for entry in no_new_work
        )
    )
    if not traces and not has_dual_no_new_work:
        errors.append("missing review evidence traces")
    for index, trace in enumerate(traces, start=1):
        for error in review_evidence_trace_errors(trace):
            errors.append(f"review evidence trace {index}: {error}")
    return errors


def review_evidence_traces_from_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    traces = profile.get("review_evidence_traces", profile.get("evidence_traces", []))
    if not isinstance(traces, list):
        return []
    return [trace for trace in traces if isinstance(trace, dict)]


def round1_candidate_to_trace(candidate: dict[str, Any]) -> dict[str, Any]:
    """Derive an evidence trace from a round-1 candidate's structured fields.

    Round-1 findings are themselves the evidence: each candidate carries gap,
    current_state, required_change, design_refs, implementation_refs, and
    test_refs. This mirrors the legacy profile-trace shape so the existing
    quality gate and approved-queue logic can treat the two sources uniformly.
    """
    title = str(candidate.get("title") or "").strip()
    pattern = f"^{re.escape(title)}$" if title else "^.*$"
    return {
        "candidate_title_patterns": [pattern],
        "gap": str(candidate.get("gap") or ""),
        "current_state": str(candidate.get("current_state") or ""),
        "required_change": str(candidate.get("required_change") or ""),
        "design_refs": list(candidate.get("design_refs") or []),
        "implementation_refs": list(candidate.get("implementation_refs") or []),
        "test_refs": list(candidate.get("test_refs") or []),
    }


def review_evidence_traces_for_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return evidence traces from profile + the latest negotiated state.

    Profile traces are hand-curated (legacy). Round-1 and round-2 candidates
    each carry their own structured fields (gap/refs/acceptance) — those become
    auto-generated traces. When round 2 has converged, its candidates are the
    authoritative source; round-1 is the fallback when round 2 hasn't run.
    The quality gate accepts traces from any of the three sources.
    """
    traces: list[dict[str, Any]] = list(
        review_evidence_traces_from_profile(state.get("review_profile") or {})
    )
    converged = state.get("round2_converged")
    if isinstance(converged, dict):
        for candidate in converged.get("converged_candidates") or []:
            if isinstance(candidate, dict):
                traces.append(round1_candidate_to_trace(candidate))
        meta = converged.get("meta_candidate")
        if isinstance(meta, dict):
            traces.append(round1_candidate_to_trace(meta))
        return traces
    findings = state.get("round1_findings") or {}
    if isinstance(findings, dict):
        for candidate in findings.get("candidates") or []:
            if isinstance(candidate, dict):
                traces.append(round1_candidate_to_trace(candidate))
    return traces


def build_decision_brief(state: dict[str, Any]) -> dict[str, Any]:
    implementation = execution_dimension(state, "implementation_coverage")
    testing = execution_dimension(state, "test_and_live_readiness")
    integration = execution_dimension(state, "integration_and_state")
    issue_generation = execution_dimension(state, "issue_generation")
    profile = state.get("review_profile") or {}
    feedback = state.get("feedback_decision") or {}
    gitnexus_map = state.get("gitnexus_map") or {}
    gitnexus_stats = gitnexus_map.get("stats") or {}
    gitnexus_summary = (
        f"{gitnexus_map.get('status', 'missing')} map; "
        f"indexed `{str(gitnexus_map.get('indexed_commit') or 'unknown')[:12]}`; "
        f"head `{str(gitnexus_map.get('head_commit') or 'unknown')[:12]}`; "
        f"files `{gitnexus_stats.get('files', 'unknown')}`, nodes `{gitnexus_stats.get('nodes', 'unknown')}`, "
        f"processes `{gitnexus_stats.get('processes', 'unknown')}`."
    )
    brief = {
        "design_target": state["decision_anchor"] or "No decision anchor recorded.",
        "progress_summary": profile.get("progress_summary") or implementation["finding"],
        "readiness_summary": profile.get("readiness_summary") or readiness_summary(state),
        "issue_set_recommendation": issue_set_recommendation(state),
        "review_focus": profile.get("review_focus", []),
        "concerns": profile.get("concerns", []),
        "review_evidence_traces": review_evidence_traces_for_state(state),
        "no_new_work_justifications": (
            (state.get("round2_converged") or {}).get("no_new_work_justifications") or []
        ),
        "recorded_feedback": feedback,
        "gitnexus_summary": gitnexus_summary,
        "design_evidence": execution_dimension(state, "design_contract")["evidence"],
        "implementation_evidence": implementation["evidence"],
        "testing_evidence": testing["evidence"],
        "integration_evidence": integration["evidence"],
        "issue_generation_evidence": issue_generation["evidence"],
        "issue_candidates": issue_candidate_summaries(state),
        "feedback_template": [
            "decision: approve | revise | defer | drop | deeper-review",
            "priority: high | normal | low",
            "approval prerequisite: add matching review_evidence_traces in config/repo_review_profiles.json",
            "notes: what to change before issue creation",
        ],
    }
    quality_errors = review_summary_quality_errors(brief)
    brief["review_quality_errors"] = quality_errors
    brief["review_quality_status"] = "pass" if not quality_errors else "fail"
    return brief


def deadlocked_candidates_section(state: dict[str, Any]) -> list[str]:
    """Render the deadlocked-candidates section for the per-repo packet.

    Each deadlocked candidate carries both agents' positions inline so the
    human reviewer can see the disagreement and break the tie without opening
    converged.json. Returns [] when no deadlocks exist.
    """
    converged = state.get("round2_converged") or {}
    deadlocked = converged.get("deadlocked_candidates") or []
    if not deadlocked:
        return []
    lines: list[str] = [
        "#### Deadlocked Candidates",
        "",
        "These candidates require human resolution — both agents' final-turn "
        "positions are inlined below. Approve, revise, or drop after reading both.",
        "",
    ]
    for index, item in enumerate(deadlocked, start=1):
        title = str(item.get("title") or "Untitled")
        lines.append(
            f"{index}. **{title}** (source: {item.get('source_agent', '?')}, round1 #{item.get('round1_index', '?')})"
        )
        for mark in item.get("marks_history") or []:
            agent = mark.get("from_agent", "?")
            mark_type = mark.get("mark", "?")
            turn = mark.get("turn", "?")
            reason = str(mark.get("reason") or "").strip()
            lines.append(f"   - **{agent}** (turn {turn}): `{mark_type}`")
            if reason:
                lines.append(f"     > {reason[:400]}{'...' if len(reason) > 400 else ''}")
        lines.append("")
    return lines


def deadlocked_meta_section(state: dict[str, Any]) -> list[str]:
    """Render the deadlocked meta-candidate section, if any.

    A meta-candidate is deadlocked when one agent proposed a systemic-pattern
    audit and the other rejected it. Surface both positions so the human can
    decide whether to open the audit anyway.
    """
    converged = state.get("round2_converged") or {}
    dm = converged.get("deadlocked_meta")
    if not isinstance(dm, dict):
        return []
    lines: list[str] = [
        "#### Deadlocked Meta-Candidate",
        "",
        f"**{dm.get('title', 'Untitled meta')}**",
        "",
        f"- Pattern: {dm.get('pattern', '')}",
        f"- Proposed by: `{dm.get('proposed_by', '?')}`",
        f"- Rejected by: `{', '.join(dm.get('rejected_by') or []) or '?'}`",
        f"- Priority/confidence: `{dm.get('priority', '?')}` / `{dm.get('confidence', '?')}`",
        "",
        "Rejection reasons:",
        "",
    ]
    for agent, reason in (dm.get("rejection_reasons") or {}).items():
        lines.append(f"- **{agent}**: {str(reason)[:400]}")
    lines.append("")
    return lines


def no_new_work_justifications_section(state: dict[str, Any]) -> list[str]:
    """Render dual no-new-work justifications when both agents reached that
    conclusion (round-2 converged with 0 candidates + ≥2 substantive
    justifications).
    """
    converged = state.get("round2_converged") or {}
    if (converged.get("converged_candidates") or []) or converged.get("meta_candidate"):
        return []
    justifications = [
        j
        for j in (converged.get("no_new_work_justifications") or [])
        if isinstance(j, dict)
        and j.get("candidate_count") == 0
        and len(str(j.get("justification") or "").strip()) >= 200
    ]
    if len(justifications) < 2:
        return []
    lines: list[str] = [
        "#### No-New-Work Justifications",
        "",
        "Both agents independently reached the same conclusion. Verify the cited "
        "file/test evidence below before accepting no-new-issues for this cycle.",
        "",
    ]
    for j in justifications:
        agent = j.get("agent", "?")
        text = str(j.get("justification") or "").strip()
        lines.extend([f"- **{agent}**:", f"  > {text}", ""])
    return lines


def markdown_candidate_list(candidates: list[dict[str, Any]], empty: str) -> str:
    if not candidates:
        return empty
    lines: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        task_count = candidate.get("task_count")
        task_note = f"; {task_count} open tasks" if task_count is not None else ""
        lines.append(
            f"{index}. **{candidate['title']}** ({candidate['type']}; {candidate['source']}{task_note})"
        )
        for task in candidate.get("task_preview", [])[:3]:
            lines.append(f"   - {task}")
    return "\n".join(lines)


def normalize_priority(value: Any) -> str:
    priority = str(value or "normal").lower().strip()
    return priority if priority in PRIORITY_ORDER else "normal"


def decision_parts(decision: Any) -> set[str]:
    return {
        part.strip().lower() for part in re.split(r"\s*\|\s*", str(decision or "")) if part.strip()
    }


def candidate_title_pattern_indexes(
    decision: dict[str, Any], key: str, candidates: list[dict[str, Any]]
) -> set[int]:
    patterns = decision.get(key, [])
    if not isinstance(patterns, list):
        return set()
    indexes: set[int] = set()
    for candidate in candidates:
        title = str(candidate.get("title", ""))
        for pattern in patterns:
            try:
                if re.search(str(pattern), title, flags=re.I):
                    indexes.add(int(candidate["candidate_index"]))
                    break
            except re.error:
                continue
    return indexes


def approved_candidate_indexes(
    decision: dict[str, Any],
    total_candidates: int,
    defaults: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> set[int]:
    title_pattern_indexes = candidate_title_pattern_indexes(
        decision, "approved_title_patterns", candidates
    )
    if title_pattern_indexes:
        return title_pattern_indexes
    approved = decision.get("approved_candidates", defaults.get("approved_candidates", []))
    if approved == "all":
        return set(range(1, total_candidates + 1))
    if not isinstance(approved, list):
        return set()
    indexes: set[int] = set()
    for item in approved:
        try:
            indexes.add(int(item))
        except (TypeError, ValueError):
            continue
    return indexes


def parse_candidate_indexes(value: Any) -> set[int]:
    if not isinstance(value, list):
        value = [value] if value else []
    indexes: set[int] = set()
    for item in value:
        try:
            indexes.add(int(item))
        except (TypeError, ValueError):
            continue
    return indexes


def dropped_candidate_indexes(
    decision: dict[str, Any], candidates: list[dict[str, Any]] | None = None
) -> set[int]:
    dropped = decision.get("dropped_candidates", [])
    if not isinstance(dropped, list):
        dropped = []
    indexes: set[int] = set()
    for item in dropped:
        try:
            indexes.add(int(item))
        except (TypeError, ValueError):
            continue
    if candidates is not None:
        indexes.update(
            candidate_title_pattern_indexes(decision, "dropped_title_patterns", candidates)
        )
    return indexes


def evidence_trace_title_patterns(trace: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "issue_title_pattern",
        "issue_title_patterns",
        "candidate_title_pattern",
        "candidate_title_patterns",
    ):
        value = trace.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif value:
            values.append(value)
    return [str(value) for value in values if str(value).strip()]


def candidate_matches_evidence_trace(candidate: dict[str, Any], trace: dict[str, Any]) -> bool:
    candidate_index = int(candidate.get("candidate_index", 0))
    trace_indexes = parse_candidate_indexes(trace.get("candidate_indexes", []))
    if candidate_index in trace_indexes:
        return True

    title = str(candidate.get("title", ""))
    candidate_titles = trace.get("candidate_titles", [])
    if not isinstance(candidate_titles, list):
        candidate_titles = [candidate_titles]
    if title in {str(item) for item in candidate_titles}:
        return True

    for pattern in evidence_trace_title_patterns(trace):
        try:
            if re.search(pattern, title, flags=re.I):
                return True
        except re.error:
            continue
    return False


def review_evidence_trace_for_candidate(
    state: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any] | None:
    traces = state["decision_brief"].get("review_evidence_traces", [])
    for trace in traces:
        if isinstance(trace, dict) and candidate_matches_evidence_trace(candidate, trace):
            return trace
    return None


def open_task_lines(body: str, limit: int = 8) -> list[str]:
    tasks: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not re.search(r"\[\s\]", stripped):
            continue
        tasks.append(re.sub(r"^[-*]\s*\[\s\]\s*", "", stripped).strip())
        if len(tasks) >= limit:
            break
    return tasks


def candidate_goal_text(candidate: dict[str, Any]) -> str:
    return normalize_issue_title(str(candidate["title"]).strip(), max_length=200)


def issue_task_lines(candidate: dict[str, Any]) -> list[str]:
    if candidate["type"] in ("round 1 finding", "round 2 finding", "round 2 audit"):
        source = candidate.get("round1_candidate") or {}
        tasks = source.get("tasks") or []
        if isinstance(tasks, list) and tasks:
            return [str(item) for item in tasks]
    if candidate["type"] == "local draft":
        tasks = open_task_lines(candidate.get("body", ""))
        if tasks:
            return tasks
    return [f"Implement the approved review gap: {candidate_goal_text(candidate)}"]


def build_agent_issue_body(state: dict[str, Any], candidate: dict[str, Any], priority: str) -> str:
    if candidate["type"] in (
        "local draft",
        "round 1 finding",
        "round 2 finding",
        "round 2 audit",
    ):
        local_body = str(candidate.get("body", "")).strip()
        local_lines = local_body.splitlines()
        if local_lines and ISSUE_HEADING_RE.match(local_lines[0].strip()):
            local_body = "\n".join(local_lines[1:]).strip()
        if issue_body_is_agent_ready(local_body):
            return local_body + "\n"

    brief = state["decision_brief"]
    design_sources = state["design_files"][:5]
    implementation_evidence = brief["implementation_evidence"][:4]
    testing_evidence = [*brief["testing_evidence"], *brief["integration_evidence"][:2]][:5]
    gitnexus = state["gitnexus_map"]
    candidate_goal = candidate_goal_text(candidate)
    tasks = issue_task_lines(candidate)
    design_source_lines = [f"  - `{path}`" for path in design_sources] or [
        "  - None found by the evaluator."
    ]
    implementation_evidence_lines = [f"  - {item}" for item in implementation_evidence] or [
        "  - None found by the evaluator."
    ]
    testing_evidence_lines = [f"  - {item}" for item in testing_evidence] or [
        "  - None found by the evaluator."
    ]
    task_lines = [f"- [ ] {task}" for task in tasks]
    task_lines.extend(
        [
            "- [ ] Add or update repo-local tests, smoke checks, or verifier documentation that prove the changed behavior.",
            "- [ ] Update user-facing docs or runbooks when the implemented behavior changes an expected workflow.",
        ]
    )
    body_lines = [
        "## Why",
        "",
        brief["progress_summary"],
        "",
        f"Design target: {brief['design_target']}",
        "",
        f"Readiness context: {brief['readiness_summary']}",
        "",
        "## Scope",
        "",
        f"- Approved weekly-review candidate: {candidate_goal}",
        f"- Candidate source: {candidate['source']} ({candidate['type']})",
        f"- Weekly priority: {priority}",
        "- Use the current repo design sources and implementation evidence before changing code.",
        "",
        "## Non-Goals",
        "",
        "- Do not do unrelated refactors or broad cleanup outside the reviewed gap.",
        "- Do not satisfy this issue with fixture-only, scaffold-only, or documentation-only behavior unless the scope is explicitly documentation.",
        "- Do not place Workflows maintenance, template sync, or cross-repo lane-management tasks in this consumer repo unless the work directly implements repo-local behavior required by the design.",
        "",
        "## Tasks",
        "",
        *task_lines,
        "",
        "## Acceptance Criteria",
        "",
        "- [ ] The reviewed design/readiness gap is implemented in repo-local code, docs, tests, or workflows as appropriate for the issue.",
        "- [ ] At least one targeted automated test, smoke check, verifier run, or documented live-verification gate proves the behavior and would have failed or been absent before the change.",
        "- [ ] The PR notes the design source or review evidence used to define completion.",
        "- [ ] No unrelated Workflows/template-sync maintenance is bundled into this repo issue.",
        "",
        "## Implementation Notes",
        "",
        f"- GitNexus map: {gitnexus['status']} ({gitnexus['meta_path'] or 'no meta.json'}).",
        f"- GitNexus indexed commit: {gitnexus['indexed_commit'] or 'unknown'}; repo head: {gitnexus['head_commit'] or 'unknown'}.",
        "- Design sources to inspect:",
        *design_source_lines,
        "- Key implementation evidence from the weekly review:",
        *implementation_evidence_lines,
        "- Key testing/integration evidence from the weekly review:",
        *testing_evidence_lines,
    ]
    return "\n".join(body_lines).strip() + "\n"


def issue_body_has_required_sections(body: str) -> bool:
    return issue_body_is_agent_ready(body)


def feedback_covers_converged(
    decision: dict[str, Any], feedback_generated_on: str, converged: Any
) -> bool:
    """Cycle-binding (#2272): does the recorded human feedback actually correspond to the
    current round-2 converged set, or does it predate it?

    A stale per-repo ``"approve all"`` decision otherwise auto-approves every *future*
    cycle's brand-new candidates that the human never saw. Feedback is treated as covering
    the current converged set when either:

      * the decision pins ``approved_converged_synthesized_at`` to the converged set's
        ``synthesized_at`` (explicit binding), or
      * the feedback's ``generated_on`` date is at least as new as the converged set's
        ``synthesized_at`` date.

    When there is no converged set to bind to (round-1-only path) prior behavior is kept.
    Unparseable dates fail closed (not covered) so a malformed stamp cannot auto-approve.
    """
    if not isinstance(converged, dict):
        return True
    synth = str(converged.get("synthesized_at") or "").strip()
    if not synth:
        return True
    pinned = str(decision.get("approved_converged_synthesized_at") or "").strip()
    if pinned:
        return pinned == synth
    from datetime import date

    try:
        fb = date.fromisoformat(str(feedback_generated_on or "")[:10])
        cv = date.fromisoformat(synth[:10])
    except ValueError:
        return False
    return fb >= cv


def build_approved_issue_queue(
    states: list[dict[str, Any]], feedback_config: dict[str, Any], generated_on: str
) -> dict[str, Any]:
    defaults = feedback_config.get("defaults", {}) if isinstance(feedback_config, dict) else {}
    decisions = feedback_config.get("decisions", {}) if isinstance(feedback_config, dict) else {}
    routing_rules = (
        feedback_config.get("routing_rules", []) if isinstance(feedback_config, dict) else []
    )
    issues: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    deeper_review: list[dict[str, Any]] = []
    warnings: list[str] = []

    for state in states:
        if state["status"] != "active":
            continue
        decision = decisions.get(state["repo"], {})
        if not isinstance(decision, dict):
            decision = {}
        repo_decision = str(
            decision.get("decision", defaults.get("omitted_repo_decision", "defer"))
        )
        parts = decision_parts(repo_decision)
        priority = normalize_priority(decision.get("priority", "normal"))
        candidates = issue_candidate_records(state, max_items=None)
        dropped_indexes = dropped_candidate_indexes(decision, candidates)

        if "deeper-review" in parts:
            deeper_review.append(
                {
                    "repo": state["repo"],
                    "priority": priority,
                    "decision": repo_decision,
                    "notes": decision.get("notes", ""),
                    "design_target": state["decision_brief"]["design_target"],
                    "review_focus": state["decision_brief"]["review_focus"],
                    "concerns": state["decision_brief"]["concerns"],
                    "gitnexus_map": state["gitnexus_map"],
                }
            )

        for candidate in candidates:
            if candidate["candidate_index"] in dropped_indexes:
                dropped.append(
                    {
                        "repo": state["repo"],
                        "candidate_index": candidate["candidate_index"],
                        "title": candidate["title"],
                        "reason": decision.get("notes", "Dropped by feedback."),
                    }
                )

        if "approve" not in parts:
            continue

        review_quality_errors = state["decision_brief"].get("review_quality_errors", [])
        if review_quality_errors:
            error_summary = "; ".join(str(error) for error in review_quality_errors[:5])
            warnings.append(
                f"{state['repo']} was approved but its review brief failed the quality gate: "
                f"{error_summary}"
            )
            deeper_review.append(
                {
                    "repo": state["repo"],
                    "priority": priority,
                    "decision": "deeper-review",
                    "notes": (
                        "Approved candidates were held back because the review brief did not "
                        f"contain a substantive repo-specific progress/readiness review: {error_summary}"
                    ),
                    "design_target": state["decision_brief"]["design_target"],
                    "review_focus": state["decision_brief"]["review_focus"],
                    "concerns": [
                        *state["decision_brief"]["concerns"],
                        "Complete a repo-specific design-vs-implementation review before upload.",
                    ],
                    "gitnexus_map": state["gitnexus_map"],
                }
            )
            continue

        # Cycle-binding (#2272): a blanket "approve all" only auto-approves the cycle the
        # human actually reviewed. If the feedback predates this converged set (and the
        # repo hasn't opted into unattended approval), route the new candidates to
        # deeper-review instead of materializing them. Explicitly listed approved_candidates
        # and repos with auto_approve_new:true are unaffected.
        approved_spec = decision.get("approved_candidates", defaults.get("approved_candidates", []))
        is_blanket = isinstance(approved_spec, str) and approved_spec.strip().lower() == "all"
        auto_approve_new = bool(decision.get("auto_approve_new", False))
        converged = state.get("round2_converged")
        if (
            is_blanket
            and not auto_approve_new
            and not feedback_covers_converged(
                decision, feedback_config.get("generated_on", ""), converged
            )
        ):
            synth = str((converged or {}).get("synthesized_at") or "").strip()
            warnings.append(
                f"{state['repo']}: blanket 'approve all' feedback is not bound to the current "
                f"converged set; routed to deeper-review (stale-feedback guard)."
            )
            deeper_review.append(
                {
                    "repo": state["repo"],
                    "priority": priority,
                    "decision": "deeper-review",
                    "notes": (
                        f"Blanket 'approve all' feedback (generated_on "
                        f"{feedback_config.get('generated_on', '?')}) predates this cycle's converged "
                        f"set (synthesized_at {synth or '?'}); new candidates need fresh human "
                        f"approval. To approve: set this repo's approved_converged_synthesized_at to "
                        f"the converged synthesized_at, list specific approved_candidates, or set "
                        f"auto_approve_new: true."
                    ),
                    "design_target": state["decision_brief"]["design_target"],
                    "review_focus": state["decision_brief"]["review_focus"],
                    "concerns": state["decision_brief"]["concerns"],
                    "gitnexus_map": state["gitnexus_map"],
                }
            )
            continue

        selected_indexes = approved_candidate_indexes(
            decision, len(candidates), defaults, candidates
        )
        missing_indexes = sorted(index for index in selected_indexes if index > len(candidates))
        if missing_indexes:
            warnings.append(
                f"{state['repo']} approved missing candidate indexes: {', '.join(map(str, missing_indexes))}"
            )
        for candidate in candidates:
            if candidate["candidate_index"] not in selected_indexes:
                continue
            if candidate["candidate_index"] in dropped_indexes:
                continue
            evidence_trace = review_evidence_trace_for_candidate(state, candidate)
            if evidence_trace is None:
                warnings.append(
                    f"{state['repo']} candidate {candidate['candidate_index']} was approved but "
                    "has no matching review evidence trace."
                )
                deeper_review.append(
                    {
                        "repo": state["repo"],
                        "priority": priority,
                        "decision": "deeper-review",
                        "notes": (
                            "Approved candidate was held back because no review evidence trace "
                            f"was tied to candidate {candidate['candidate_index']}: {candidate['title']}"
                        ),
                        "design_target": state["decision_brief"]["design_target"],
                        "review_focus": state["decision_brief"]["review_focus"],
                        "concerns": [
                            *state["decision_brief"]["concerns"],
                            f"Add a review evidence trace for candidate {candidate['candidate_index']}: {candidate['title']}",
                        ],
                        "gitnexus_map": state["gitnexus_map"],
                    }
                )
                continue
            body = build_agent_issue_body(state, candidate, priority)
            quality_errors = issue_body_quality_errors(body)
            if quality_errors:
                error_summary = "; ".join(quality_errors[:5])
                warnings.append(
                    f"{state['repo']} candidate {candidate['candidate_index']} "
                    f"was approved but needs issue-body revision before upload: {error_summary}"
                )
                deeper_review.append(
                    {
                        "repo": state["repo"],
                        "priority": priority,
                        "decision": "revise",
                        "notes": (
                            "Approved candidate did not pass the agent-ready issue-quality gate: "
                            f"{error_summary}"
                        ),
                        "design_target": state["decision_brief"]["design_target"],
                        "review_focus": state["decision_brief"]["review_focus"],
                        "concerns": [
                            *state["decision_brief"]["concerns"],
                            f"Revise candidate {candidate['candidate_index']}: {candidate['title']}",
                        ],
                        "gitnexus_map": state["gitnexus_map"],
                    }
                )
                continue
            issues.append(
                {
                    "repo": state["repo"],
                    "local_path": state["local_path"],
                    "priority": priority,
                    "priority_rank": PRIORITY_ORDER[priority],
                    "candidate_index": candidate["candidate_index"],
                    "source_type": candidate["type"],
                    "source": candidate["source"],
                    "title": normalize_issue_title(candidate["title"]),
                    "labels": ["repo-review-approved", f"priority:{priority}"],
                    "body_format": list(ISSUE_BODY_REQUIRED_SECTIONS),
                    "body_valid": True,
                    "body_quality_errors": [],
                    "review_evidence_trace": evidence_trace,
                    "body": body,
                    "feedback_notes": decision.get("notes", ""),
                    "gitnexus_status": state["gitnexus_map"]["status"],
                }
            )

    issues.sort(
        key=lambda item: (item["priority_rank"], item["repo"].lower(), item["candidate_index"])
    )
    deeper_review.sort(
        key=lambda item: (
            PRIORITY_ORDER[normalize_priority(item["priority"])],
            item["repo"].lower(),
        )
    )
    return {
        "generated_on": generated_on,
        "source_feedback_generated_on": feedback_config.get("generated_on", ""),
        "routing_rules": routing_rules,
        "issues": issues,
        "deeper_review": deeper_review,
        "dropped_candidates": dropped,
        "warnings": warnings,
    }


def write_approved_issue_queue(
    output_dir: Path,
    states: list[dict[str, Any]],
    feedback_config: dict[str, Any],
    generated_on: str,
) -> dict[str, Any]:
    queue = build_approved_issue_queue(states, feedback_config, generated_on)
    (output_dir / "approved-issue-queue.json").write_text(
        json.dumps(queue, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        f"# Approved Issue Queue - {generated_on}",
        "",
        "This queue is generated from the human feedback config. It is the handoff surface for coding-agent opener lanes; it does not create remote issues by itself.",
        "",
        "## Routing Rules",
        "",
        markdown_bullets(queue["routing_rules"], "No routing rules recorded."),
        "",
        "## Approved Issues",
        "",
    ]
    if not queue["issues"]:
        lines.extend(["No approved issue candidates are queued.", ""])
    for item in queue["issues"]:
        lines.extend(
            [
                f"### [{item['priority']}] {item['repo']} candidate {item['candidate_index']}: {item['title']}",
                "",
                f"- Source: `{item['source']}`",
                f"- Labels: `{', '.join(item['labels'])}`",
                f"- Body follows required issue sections: `{item['body_valid']}`",
                f"- Evidence gap: {item['review_evidence_trace']['gap']}",
                f"- Evidence design refs: `{', '.join(item['review_evidence_trace'].get('design_refs', []))}`",
                f"- Evidence implementation refs: `{', '.join(item['review_evidence_trace'].get('implementation_refs', []))}`",
                "",
                "```markdown",
                item["body"].strip(),
                "```",
                "",
            ]
        )
    lines.extend(["## Deeper Review Or Revision Required", ""])
    if not queue["deeper_review"]:
        lines.extend(["None.", ""])
    for item in queue["deeper_review"]:
        lines.extend(
            [
                f"### [{item['priority']}] {item['repo']}",
                "",
                f"- Decision: `{item['decision']}`",
                f"- Notes: {item['notes'] or 'None recorded.'}",
                f"- GitNexus map: `{item['gitnexus_map']['status']}` at `{item['gitnexus_map']['meta_path'] or 'not found'}`",
                "",
                "Review focus:",
                "",
                markdown_bullets(item["review_focus"]),
                "",
                "Concerns:",
                "",
                markdown_bullets(item["concerns"]),
                "",
            ]
        )
    lines.extend(["## Dropped Candidates", ""])
    if not queue["dropped_candidates"]:
        lines.extend(["None.", ""])
    for item in queue["dropped_candidates"]:
        lines.extend(
            [
                f"- `{item['repo']}` candidate `{item['candidate_index']}`: {item['title']}",
                f"  Reason: {item['reason']}",
            ]
        )
    if queue["warnings"]:
        lines.extend(["", "## Warnings", "", markdown_bullets(queue["warnings"]), ""])
    (output_dir / "approved-issue-queue.md").write_text("\n".join(lines), encoding="utf-8")
    return queue


def write_decision_brief(repo_dir: Path, state: dict[str, Any]) -> None:
    brief = state["decision_brief"]
    lines = [
        f"# Human Decision Brief: {state['repo']}",
        "",
        "Use this brief to decide whether the current issue set should be approved, revised, deferred, dropped, or sent back for deeper review.",
        "",
        "## Review Quality Gate",
        "",
        f"- Status: `{brief['review_quality_status']}`",
        "",
        "Quality findings:",
        "",
        markdown_bullets(brief["review_quality_errors"]),
        "",
        "## Process Chain Checkpoint",
        "",
        *process_chain_checkpoint_lines(),
        "",
        "## Current Progress Compared With Design",
        "",
        f"- Design target: {brief['design_target']}",
        f"- Progress summary: {brief['progress_summary']}",
        f"- GitNexus map: {brief['gitnexus_summary']}",
        "",
        "Review focus:",
        "",
        markdown_bullets(brief["review_focus"]),
        "",
        "Concerns to resolve:",
        "",
        markdown_bullets(brief["concerns"]),
        "",
        "Review evidence traces:",
        "",
        markdown_review_evidence_traces(brief["review_evidence_traces"]),
        "",
        "Required profile evidence trace shape:",
        "",
        "```json",
        review_evidence_trace_template(),
        "```",
        "",
        "Design evidence:",
        "",
        markdown_list(brief["design_evidence"]),
        "",
        "Implementation evidence:",
        "",
        markdown_list(brief["implementation_evidence"]),
        "",
        "## Readiness For Testing Or Live Implementation",
        "",
        brief["readiness_summary"],
        "",
        "Testing evidence:",
        "",
        markdown_list(brief["testing_evidence"]),
        "",
        "Integration/state evidence:",
        "",
        markdown_list(brief["integration_evidence"]),
        "",
        "## Candidate Issue Set",
        "",
        brief["issue_set_recommendation"],
        "",
        markdown_candidate_list(
            brief["issue_candidates"],
            "No local/archive issue candidates were generated for this cycle.",
        ),
        "",
        "Issue generation evidence:",
        "",
        markdown_list(brief["issue_generation_evidence"]),
        "",
        "## Feedback Slot",
        "",
        f"Recorded feedback: `{brief['recorded_feedback'].get('decision', 'none')}`"
        f" / priority `{brief['recorded_feedback'].get('priority', 'unset')}`",
        "",
        "```text",
        f"repo: {state['repo']}",
        *brief["feedback_template"],
        "```",
        "",
    ]
    (repo_dir / "decision-brief.md").write_text("\n".join(lines), encoding="utf-8")


def write_remote_progress(repo_dir: Path, state: dict[str, Any]) -> None:
    """Write `remote-progress.md` per repo for round-1 dedup reference."""
    progress = state.get("remote_progress") or {}
    open_issues = progress.get("open_issues") or []
    merged_prs = progress.get("recent_merged_prs") or []
    lookback = progress.get("lookback_days", 30)
    available = progress.get("available", False)
    warnings = progress.get("warnings") or []

    lines = [
        f"# Remote Progress: {state['repo']}",
        "",
        "This file is a dedup reference for the round-1 reviewer. Use it to "
        "recognize gaps that are already covered by an open GitHub issue or a "
        "recently-merged PR. Do NOT raise candidates that duplicate items here.",
        "",
        f"- gh CLI available: `{available}`",
        f"- Merged-PR lookback: `{lookback} days`",
        f"- Open issues recorded: `{len(open_issues)}`",
        f"- Recent merged PRs recorded: `{len(merged_prs)}`",
        "",
    ]
    if warnings:
        lines.extend(["## Warnings", "", markdown_bullets([str(w) for w in warnings]), ""])
    lines.extend(["## Open Issues", ""])
    if open_issues:
        for item in open_issues:
            label_str = ", ".join(item.get("labels") or []) or "—"
            lines.append(
                f"- #{item.get('number', '?')} `{item.get('created_at', '')}` "
                f"[{label_str}] {item.get('title', '')}"
            )
    else:
        lines.append("None recorded.")
    lines.extend(["", "## Recent Merged PRs", ""])
    if merged_prs:
        for item in merged_prs:
            lines.append(
                f"- #{item.get('number', '?')} merged `{item.get('merged_at', '')}` "
                f"{item.get('title', '')}"
            )
    else:
        lines.append("None recorded.")
    lines.append("")
    (repo_dir / "remote-progress.md").write_text("\n".join(lines), encoding="utf-8")


def write_archive_progress(repo_dir: Path, state: dict[str, Any]) -> None:
    """Write `archive-progress.md` — recently-discussed topics for dedup only.

    These entries are NOT candidate sources. They exist so the round-1
    reviewer can recognize a gap that has already been raised, shipped, or
    superseded in prior review work. If the only basis for a candidate is an
    archive entry, the candidate must be dropped.
    """
    items = state.get("archive_progress") or []
    lines = [
        f"# Archive Progress: {state['repo']}",
        "",
        "Recently-discussed topics from past review sessions. **For dedup only.** "
        "Do NOT raise a candidate whose sole basis is an entry here — the round-1 "
        "reviewer must verify the gap against current code, design, and tests.",
        "",
        f"- Entries recorded: `{len(items)}`",
        "",
    ]
    if not items:
        lines.append("None recorded.")
    else:
        for index, item in enumerate(items, start=1):
            lines.extend(
                [
                    f"## {index}. {item.get('title', 'Untitled')}",
                    "",
                    f"- Thread: `{item.get('thread_name', 'untitled')}`",
                    f"- Timestamp: `{item.get('timestamp', 'unknown')}`",
                    f"- Source file: `{item.get('source_file', 'unknown')}`",
                    "",
                    "```text",
                    item.get("excerpt", "").strip(),
                    "```",
                    "",
                ]
            )
    (repo_dir / "archive-progress.md").write_text("\n".join(lines), encoding="utf-8")


def design_source_sufficiency_hint(state: dict[str, Any]) -> str:
    design_files = state.get("design_files") or []
    count = len(design_files)
    if count == 0:
        return (
            "No design source files were detected. The reviewer must read the "
            "repo's README and any in-repo docs directly, and may need to "
            "infer the design from code if docs are absent."
        )
    if count <= 3:
        return (
            f"Only {count} design source file(s) were detected. The reviewer "
            "should not assume the docs cover the full design contract — read "
            "additional code paths to verify intent."
        )
    return (
        f"{count} design source file(s) detected. Read README plus the most "
        "load-bearing docs (architecture, integration, ops); deeper code "
        "inspection is only needed where docs and implementation appear to "
        "disagree."
    )


def write_review_inputs(repo_dir: Path, state: dict[str, Any]) -> None:
    """Write `review-inputs.md` — the consolidated round-1 reviewer brief.

    This is THE entry point for the round-1 reviewer agent. It pulls together
    the decision anchor, design sources, implementation areas, dirty state,
    GitNexus map status, and pointers to the dedup references (remote-progress
    + archive-progress). The agent reads this file first, then reads the
    referenced design sources and implementation paths from the actual repo.
    """
    profile = state.get("review_profile") or {}
    review_focus = profile.get("review_focus") or []
    concerns = profile.get("concerns") or []
    gitnexus = state.get("gitnexus_map") or {}
    progress = state.get("remote_progress") or {}
    findings = state.get("round1_findings")

    if findings:
        round1_status = (
            f"Round 1 already produced findings at `{findings.get('__source_path', 'unknown')}` "
            f"by agent `{findings.get('agent', 'unknown')}`. Re-running this brief is "
            "appropriate only if those findings are stale or were rejected."
        )
    else:
        round1_status = (
            "Round 1 has not run for this repo. After completing this brief, write "
            "your findings to "
            f"`<output_dir>/round1/<your_agent_name>/{state['repo'].replace('/', '__')}/findings.json` "
            "in the schema documented in `docs/ops/REPO_REVIEW_ROUND1_SCHEMA.md`."
        )

    lines = [
        f"# Round 1 Reviewer Brief: {state['repo']}",
        "",
        "You are running round 1 of the weekly design-vs-implementation review for "
        "this repository. Another quality professional will independently review "
        "the same repo with the same inputs; in round 2 you will negotiate toward "
        "a shared candidate set. Round 1 is your independent assessment.",
        "",
        "## Decision Anchor",
        "",
        state.get("decision_anchor") or "No decision anchor recorded.",
        "",
        "## Profile Review Focus",
        "",
        markdown_bullets([str(item) for item in review_focus]),
        "",
        "## Profile Concerns",
        "",
        markdown_bullets([str(item) for item in concerns]),
        "",
        "## Repository Location",
        "",
        f"- Local path: `{state['local_path']}`",
        f"- Origin: `{state.get('origin') or 'unknown'}`",
        f"- Branch: `{state.get('branch') or 'unknown'}`",
        f"- Last commit: `{state.get('last_commit') or 'unknown'}`",
        f"- Review-blocking local changes: `{state.get('review_blocking_dirty_count', 0)}` "
        "(if non-zero, do not produce candidates until the working tree is clean "
        "or document why review can proceed despite the dirty state)",
        "",
        "## Design Sources To Read",
        "",
        design_source_sufficiency_hint(state),
        "",
        markdown_list(state.get("design_files") or [], empty="None detected."),
        "",
        "## Implementation Areas To Inspect",
        "",
        markdown_list(
            format_implementation_areas(state.get("implementation_areas") or []),
            empty="None detected.",
        ),
        "",
        "## GitNexus Map",
        "",
        f"- Status: `{gitnexus.get('status', 'missing')}`",
        f"- Indexed at: `{gitnexus.get('indexed_at') or 'unknown'}`",
        f"- Indexed commit: `{(gitnexus.get('indexed_commit') or 'unknown')[:12]}`",
        f"- Head commit: `{(gitnexus.get('head_commit') or 'unknown')[:12]}`",
        "",
        "## Reports & Baseline Signals",
        "",
        "Generated reports under `docs/reports/` (coverage manifests, baseline-drift, "
        "test-quality signals). Treat a coverage regression, drift alarm, or an "
        "untested/unwired parameter flagged here as a VERIFIED candidate source when "
        "current code does not explain or correct it:",
        "",
        ("\n".join(f"- `{p}`" for p in (state.get("report_files") or [])) or "_None detected._"),
        "",
        "## Dedup References",
        "",
        f"- Remote progress: see `remote-progress.md` "
        f"({len(progress.get('open_issues') or [])} open issues, "
        f"{len(progress.get('recent_merged_prs') or [])} recent merged PRs).",
        f"- Archive progress: see `archive-progress.md` "
        f"({state.get('archive_progress_count', 0)} prior-discussion entries).",
        "",
        "**Use these for dedup only.** A candidate whose only basis is an archive "
        "entry must be dropped. A candidate that duplicates an open issue or a "
        "recently-merged PR must also be dropped (recognize completion / in-flight "
        "work; do not re-raise).",
        "",
        "## Out of Scope",
        "",
        "- `Issues.txt` in the repo root: ignore. It is template scratch for direct "
        "  on-repo work and is not a candidate source.",
        "- Workflow-sync, AGENTS.md / CLAUDE.md sync, template-sync, and lane-management "
        "  maintenance: route to `stranske/Workflows`, not to this repo, unless the "
        "  work directly implements behavior required by THIS repo's design.",
        "",
        "## Output",
        "",
        round1_status,
        "",
        "Schema reference: `docs/ops/REPO_REVIEW_ROUND1_SCHEMA.md` (see Phase 2).",
        "",
        "## Review Procedure",
        "",
        "Follow the canonical round-1 reviewer procedure documented in "
        "`docs/ops/REPO_REVIEW_ROUND1_PROMPT.md`. The coordinator hands that prompt "
        "to each agent (Codex + Claude) along with this `review-inputs.md` brief.",
        "",
    ]
    (repo_dir / "review-inputs.md").write_text("\n".join(lines), encoding="utf-8")


def write_repo_artifacts(output_dir: Path, state: dict[str, Any], max_drafts: int) -> None:
    safe_name = state["repo"].replace("/", "__")
    repo_dir = output_dir / "repos" / safe_name
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "decision.json").write_text(
        json.dumps({key: value for key, value in state.items() if key != "drafts"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    write_decision_brief(repo_dir, state)
    write_review_inputs(repo_dir, state)
    write_remote_progress(repo_dir, state)
    write_archive_progress(repo_dir, state)

    state_md = [
        f"# Repo Review State: {state['repo']}",
        "",
        f"- Status: `{state['status']}`",
        f"- Review status: `{state['review_status']}`",
        f"- Issue queue status: `{state['issue_queue_status']}`",
        f"- Review execution status: `{state['review_execution']['status']}`",
        f"- Automated material/blocking gaps: `{state['review_execution']['gap_count']}`",
        f"- Dimensions needing semantic decision: `{state['review_execution']['needs_decision_count']}`",
        f"- Local path: `{state['local_path']}`",
        f"- Origin: `{state['origin'] or 'unknown'}`",
        f"- Branch: `{state['branch'] or 'unknown'}`",
        f"- Last commit: `{state['last_commit'] or 'unknown'}`",
        f"- GitNexus map status: `{state['gitnexus_map']['status']}`",
        f"- GitNexus indexed at: `{state['gitnexus_map']['indexed_at'] or 'unknown'}`",
        f"- GitNexus meta path: `{state['gitnexus_map']['meta_path'] or 'not found'}`",
        f"- Dirty local changes: `{state['dirty_count']}`",
        f"- Non-generated local changes: `{state['material_dirty_count']}`",
        f"- Nonblocking helper local changes: `{state['helper_dirty_count']}`",
        f"- Review-blocking local changes: `{state['review_blocking_dirty_count']}`",
        f"- Generated/cache dirty local changes: `{state['generated_dirty_count']}`",
        f"- Remote open GitHub issues: `{state['remote_open_issue_count'] if state['remote_open_issue_count'] is not None else 'unknown'}`",
        f"- Recent merged PRs (last {state.get('remote_progress', {}).get('lookback_days', 30)}d): `{len((state.get('remote_progress') or {}).get('recent_merged_prs') or [])}`",
        f"- Round 1 findings: `{'present' if state.get('round1_findings') else 'not yet run'}`",
        f"- Round 1 candidate count: `{len((state.get('round1_findings') or {}).get('candidates') or [])}`",
        f"- Archive progress entries (dedup-only): `{state.get('archive_progress_count', 0)}`",
        f"- Design source files found: `{state['design_source_count']}`",
        "",
        "## Decision Anchor",
        "",
        state["decision_anchor"] or "No decision anchor recorded.",
        "",
        "## Design Sources",
        "",
        markdown_list(state["design_files"]),
        "",
        "## Implementation Areas",
        "",
        markdown_list(format_implementation_areas(state["implementation_areas"])),
        "",
        "## Standard Review Dimensions",
        "",
        "\n".join(
            f"- `{dimension['id']}`: {dimension['label']}"
            for dimension in state["review_dimensions"]
        ),
        "",
        "## Existing Reports",
        "",
        markdown_list(state["report_files"]),
        "",
        "## Non-Generated Dirty Preview",
        "",
        markdown_list(state["material_dirty_preview"]),
        "",
        "## Review-Blocking Dirty Preview",
        "",
        markdown_list(state["review_blocking_dirty_preview"]),
        "",
        "## Helper Dirty Preview",
        "",
        markdown_list(state["helper_dirty_preview"]),
        "",
    ]
    (repo_dir / "state.md").write_text("\n".join(state_md), encoding="utf-8")

    review_lines = [
        f"# Standard Design Review: {state['repo']}",
        "",
        "This worksheet is the standardized weekly design-vs-implementation review. Complete it before creating or approving new remote issues.",
        "",
        "## Review Contract",
        "",
        "- Primary goal: compare intended design to current implementation and testing readiness.",
        "- Secondary goal: turn verified gaps into issue drafts for human approval.",
        "- Current worksheet status: pending review until a human or automation fills in evidence traces and findings.",
        "- Completion standard: no issue should be considered ready unless the review identifies the design commitment, current evidence, missing behavior, and a test or live-smoke acceptance gate.",
        "- Approval standard: every approved issue candidate must have a matching `review_evidence_traces` entry in `config/repo_review_profiles.json`; polished prose without that trace is not uploadable.",
        "",
        "## Current Signals",
        "",
        f"- Review status: `{state['review_status']}`",
        f"- Issue queue status: `{state['issue_queue_status']}`",
        f"- Round 1 findings: `{'present' if state.get('round1_findings') else 'not yet run'}`",
        f"- Round 1 candidate count: `{len((state.get('round1_findings') or {}).get('candidates') or [])}`",
        f"- Archive progress entries (dedup-only): `{state.get('archive_progress_count', 0)}`",
        f"- Remote open GitHub issues: `{state['remote_open_issue_count'] if state['remote_open_issue_count'] is not None else 'unknown'}`",
        f"- Non-generated local changes: `{state['material_dirty_count']}`",
        f"- Nonblocking helper local changes: `{state['helper_dirty_count']}`",
        f"- Review-blocking local changes: `{state['review_blocking_dirty_count']}`",
        f"- GitNexus map status: `{state['gitnexus_map']['status']}`",
        "",
        "## Process Chain Checkpoint",
        "",
        *process_chain_checkpoint_lines(),
        "",
        "## Design Sources To Read",
        "",
        markdown_list(state["design_files"]),
        "",
        "## Implementation Areas To Inspect",
        "",
        markdown_list(format_implementation_areas(state["implementation_areas"])),
        "",
        "## Required Review Evidence Trace",
        "",
        "For every proposed issue, add a trace record to `config/repo_review_profiles.json` that links the candidate to the underlying design-vs-implementation finding:",
        "",
        "```json",
        review_evidence_trace_template(),
        "```",
        "",
        "The trace must be based on files actually inspected during the review. Do not use it as a wording exercise; the uploader validates that the trace exists, and the human packet shows it for review.",
        "",
        "## Review Dimensions",
        "",
    ]
    for dimension in state["review_dimensions"]:
        review_lines.extend(
            [
                f"### {dimension['label']}",
                "",
                dimension["prompt"],
                "",
                "- Evidence reviewed:",
                "- Finding:",
                "- Gap severity: `none | mop-up | material | blocks testing | blocks live use`",
                "- Issue draft needed: `yes | no | needs human decision`",
                "",
            ]
        )
    if state["archive_candidates"]:
        review_lines.extend(
            [
                "## Archive Review Precedent",
                "",
                "Use these prior design-review outputs as precedent, not as automatically approved issues.",
                "",
            ]
        )
        for index, candidate in enumerate(state["archive_candidates"][:max_drafts], start=1):
            review_lines.extend(
                [
                    f"### Precedent {index}: {candidate['title']}",
                    "",
                    f"- Thread: `{candidate['thread_name']}`",
                    f"- Timestamp: `{candidate['timestamp'] or 'unknown'}`",
                    f"- Source: `{candidate['source_file']}`",
                    "",
                    "```text",
                    candidate["excerpt"],
                    "```",
                    "",
                ]
            )
    review_lines.extend(
        [
            "## Issue Generation Gate",
            "",
            "Before approving issue creation, confirm each issue has:",
            "",
            "- a specific design commitment or readiness gap;",
            "- current implementation evidence;",
            "- a matching `review_evidence_traces` record with design, implementation, and test/readiness refs;",
            "- non-goals that prevent scaffold-only completion claims;",
            "- tasks that a coding agent can complete;",
            "- acceptance criteria with a failing test, smoke test, or documented live-verification gate.",
            "",
        ]
    )
    (repo_dir / "design-review.md").write_text("\n".join(review_lines), encoding="utf-8")

    execution = state["review_execution"]
    execution_lines = [
        f"# Review Execution: {state['repo']}",
        "",
        "This file is the automated execution phase of the standardized review. It gathers evidence and classifies preliminary gaps; it does not approve remote issue creation by itself.",
        "",
        "## Execution Summary",
        "",
        f"- Status: `{execution['status']}`",
        f"- Tracked files inspected: `{execution['tracked_file_count']}`",
        f"- Source-like implementation files: `{execution['implementation_file_count']}`",
        f"- Test files: `{execution['test_file_count']}`",
        f"- Workflow files: `{execution['workflow_file_count']}`",
        f"- Automated material/blocking gaps: `{execution['gap_count']}`",
        f"- Dimensions needing semantic decision: `{execution['needs_decision_count']}`",
        "",
        execution["summary"],
        "",
        "## Dimension Findings",
        "",
    ]
    for dimension in execution["dimensions"]:
        execution_lines.extend(
            [
                f"### {dimension['label']}",
                "",
                f"- Gap severity: `{dimension['gap_severity']}`",
                f"- Issue draft needed: `{dimension['issue_draft_needed']}`",
                f"- Finding: {dimension['finding']}",
                "",
                "Evidence:",
                "",
                markdown_list(dimension["evidence"]),
                "",
            ]
        )
    execution_lines.extend(
        [
            "## Review Rule",
            "",
            "A `needs human decision` dimension is not a finding that no work remains. It means the automated execution gathered evidence but still requires semantic comparison between the design and implementation before issue approval.",
            "",
        ]
    )
    (repo_dir / "review-execution.md").write_text("\n".join(execution_lines), encoding="utf-8")

    draft_lines = [
        f"# Issue Drafts: {state['repo']}",
        "",
        "These are inputs to the standardized design review. No remote issues were created.",
        "",
    ]
    for draft in state["drafts"][:max_drafts]:
        draft_lines.extend(
            [
                f"## Draft {draft['number']}: {draft['title']}",
                "",
                f"- Open checklist items: `{draft['open_tasks']}`",
                f"- Completed checklist items: `{draft['done_tasks']}`",
                "",
                "```markdown",
                draft["body"].strip(),
                "```",
                "",
            ]
        )
    if state["archive_candidates"]:
        draft_lines.extend(
            [
                "## Archive-Derived Candidates",
                "",
                "These candidates came from prior repo-review conversations and need human review before remote issue creation.",
                "",
            ]
        )
    for index, candidate in enumerate(state["archive_candidates"][:max_drafts], start=1):
        draft_lines.extend(
            [
                f"### Archive Candidate {index}: {candidate['title']}",
                "",
                f"- Thread: `{candidate['thread_name']}`",
                f"- Timestamp: `{candidate['timestamp'] or 'unknown'}`",
                f"- Source: `{candidate['source_file']}`",
                "",
                "```text",
                candidate["excerpt"],
                "```",
                "",
            ]
        )
    if state["archive_candidate_count"] > max_drafts:
        draft_lines.append(
            f"_Only the first {max_drafts} archive candidates are shown; {state['archive_candidate_count'] - max_drafts} additional candidates were found._"
        )
    if state["issue_draft_count"] > max_drafts:
        draft_lines.append(
            f"_Only the first {max_drafts} drafts are shown; {state['issue_draft_count'] - max_drafts} additional drafts remain in `Issues.txt`._"
        )
    (repo_dir / "issue-drafts.md").write_text("\n".join(draft_lines), encoding="utf-8")


def write_packet(
    output_dir: Path,
    states: list[dict[str, Any]],
    generated_on: str,
    gitnexus_preflight_result: dict[str, Any] | None = None,
) -> None:
    gitnexus_preflight_result = gitnexus_preflight_result or {"warnings": [], "refreshed": []}
    active = [state for state in states if state["status"] == "active"]
    paused = [state for state in states if state["status"] == "paused"]
    ignored = [state for state in states if state["status"] == "ignored"]
    review_pending = [state for state in active if state["review_status"] == PENDING_REVIEW_STATUS]
    blocked = [
        state for state in active if str(state["review_execution"]["status"]).startswith("blocked")
    ]
    issue_candidate_repos = [
        state
        for state in active
        if state["issue_queue_status"] in {"round 1 candidates present", "round 2 converged"}
    ]
    executed_reviews = [
        state for state in active if state["review_execution"]["status"] == "executed"
    ]
    automated_gap_repos = [state for state in active if state["review_execution"]["gap_count"] > 0]

    lines = [
        f"# Weekly Design Review Decision Packet - {generated_on}",
        "",
        "This packet standardizes design-vs-implementation review before any remote issue creation.",
        "",
        "## Summary",
        "",
        f"- Active repos scheduled for review: `{len(active)}`",
        f"- Active repos pending automated review execution: `{len(review_pending)}`",
        f"- Active repos with automated review execution: `{len(executed_reviews)}`",
        f"- Active repos blocked before review: `{len(blocked)}`",
        f"- Active repos with issue-draft inputs: `{len(issue_candidate_repos)}`",
        f"- Active repos with automated material/blocking gaps: `{len(automated_gap_repos)}`",
        f"- GitNexus maps refreshed before review: `{len(gitnexus_preflight_result.get('refreshed', []))}`",
        f"- GitNexus preflight warnings: `{len(gitnexus_preflight_result.get('warnings', []))}`",
        f"- Paused repos tracked: `{len(paused)}`",
        f"- Ignored repos tracked: `{len(ignored)}`",
        "",
        "## Standard Review Process",
        "",
        "Before changing automation or approving issues, use the process-chain checkpoint: inputs -> review instructions -> evidence collection -> human packet -> issue drafting -> upload gate -> coding-agent lanes. Fix the earliest upstream cause of a failure, not only the visible symptom.",
        "",
        "1. Read the design sources and registry decision anchor.",
        "2. Inspect implementation areas and distinguish real behavior from scaffolds or fixtures.",
        "3. Check tests, smoke paths, persistence, integrations, and workflow handoffs.",
        "4. For each proposed issue, write a `review_evidence_traces` record in `config/repo_review_profiles.json` tying the candidate to design refs, implementation refs, and test/readiness refs.",
        "5. Use archive-derived candidates as precedent, not as automatically approved issues.",
        "6. Generate or approve issue drafts only for verified design/readiness gaps with evidence traces.",
        "7. Route Workflows/template-sync maintenance into Workflows unless the work directly implements repo-local behavior.",
        "8. Feed approved, formatted, evidence-traced issues into `approved-issue-queue.json` for opener-lane automation.",
        "",
        "## Human Review Queue",
        "",
        "Use each repo section to make one weekly decision: approve the issue set, revise it, defer it, drop it, or request deeper review.",
        "",
    ]
    if gitnexus_preflight_result.get("warnings"):
        lines.extend(
            [
                "## GitNexus Preflight Warnings",
                "",
                markdown_bullets(gitnexus_preflight_result["warnings"]),
                "",
            ]
        )
    for state in active:
        safe_name = state["repo"].replace("/", "__")
        brief = state["decision_brief"]
        if state["review_execution"]["status"] == "executed":
            if brief["review_quality_status"] == "pass":
                human_action = (
                    "review execution complete; make the semantic human decision, then "
                    "approve/edit/defer issue drafts."
                )
            else:
                human_action = (
                    "review quality gate failed; complete a repo-specific semantic review before "
                    "approving or uploading issue drafts."
                )
        elif str(state["review_execution"]["status"]).startswith("blocked"):
            human_action = (
                "resolve the blocker, rerun review execution, then queue the human decision."
            )
        else:
            human_action = "conduct the standardized review, then approve/edit/defer issue drafts."
        lines.extend(
            [
                f"### {state['repo']}",
                "",
                f"- Review status: `{state['review_status']}`",
                f"- Review execution status: `{state['review_execution']['status']}`",
                f"- Review quality gate: `{brief['review_quality_status']}`",
                f"- Automated material/blocking gaps: `{state['review_execution']['gap_count']}`",
                f"- Dimensions needing semantic decision: `{state['review_execution']['needs_decision_count']}`",
                f"- Issue queue status: `{state['issue_queue_status']}`",
                f"- Design source files: `{state['design_source_count']}`",
                f"- Round 1 findings: `{'present' if state.get('round1_findings') else 'not yet run'}`",
                f"- Round 1 candidate count: `{len((state.get('round1_findings') or {}).get('candidates') or [])}`",
                f"- Round 2 converged: `{'present' if state.get('round2_converged') else 'not yet run'}`",
                f"- Round 2 candidates: `{len((state.get('round2_converged') or {}).get('converged_candidates') or [])}`"
                + (
                    " (+ meta-candidate)"
                    if isinstance((state.get("round2_converged") or {}).get("meta_candidate"), dict)
                    else ""
                ),
                f"- Round 2 deadlocked: `{len((state.get('round2_converged') or {}).get('deadlocked_candidates') or [])}`",
                f"- Round 2 meta status: `{(state.get('round2_converged') or {}).get('meta_status', 'n/a')}`"
                + (
                    " (meta proposal deadlocked — see deadlocked_meta in converged.json)"
                    if (state.get("round2_converged") or {}).get("deadlocked_meta")
                    else ""
                ),
                f"- Round 2 dual no-new-work justifications: `{sum(1 for j in ((state.get('round2_converged') or {}).get('no_new_work_justifications') or []) if isinstance(j, dict) and j.get('candidate_count') == 0 and str(j.get('justification') or '').strip())}`",
                f"- Archive progress entries (dedup-only): `{state.get('archive_progress_count', 0)}`",
                f"- Remote open GitHub issues: `{state['remote_open_issue_count'] if state['remote_open_issue_count'] is not None else 'unknown'}`",
                f"- Recent merged PRs (last {state.get('remote_progress', {}).get('lookback_days', 30)}d): `{len((state.get('remote_progress') or {}).get('recent_merged_prs') or [])}`",
                f"- Non-generated local changes: `{state['material_dirty_count']}`",
                f"- Nonblocking helper local changes: `{state['helper_dirty_count']}`",
                f"- Review-blocking local changes: `{state['review_blocking_dirty_count']}`",
                f"- Generated/cache dirty local changes: `{state['generated_dirty_count']}`",
                f"- GitNexus map: `{state['gitnexus_map']['status']}`",
                f"- GitNexus preflight: `{state.get('gitnexus_preflight', {}).get('refresh_status', 'not-run')}`",
                f"- Review artifacts: `repos/{safe_name}/review-inputs.md` (round-1 brief), `repos/{safe_name}/remote-progress.md`, `repos/{safe_name}/archive-progress.md`, `repos/{safe_name}/decision-brief.md`, `repos/{safe_name}/review-execution.md`, `repos/{safe_name}/design-review.md`, `repos/{safe_name}/state.md`",
                f"- Human action: {human_action}",
                "",
                "#### Current Progress Compared With Design",
                "",
                f"- Design target: {brief['design_target']}",
                f"- Progress summary: {brief['progress_summary']}",
                f"- GitNexus map: {brief['gitnexus_summary']}",
                f"- Review quality findings: {', '.join(brief['review_quality_errors']) if brief['review_quality_errors'] else 'none'}",
                "",
                "Review focus:",
                "",
                markdown_bullets(brief["review_focus"]),
                "",
                "Concerns to resolve:",
                "",
                markdown_bullets(brief["concerns"]),
                "",
                "Review evidence traces:",
                "",
                markdown_review_evidence_traces(brief["review_evidence_traces"]),
                "",
                "Key implementation evidence:",
                "",
                markdown_list(brief["implementation_evidence"]),
                "",
                "#### Readiness For Testing Or Live Implementation",
                "",
                brief["readiness_summary"],
                "",
                "Key testing/integration evidence:",
                "",
                markdown_list([*brief["testing_evidence"], *brief["integration_evidence"][:2]]),
                "",
                "#### Candidate Issue Set",
                "",
                brief["issue_set_recommendation"],
                "",
                markdown_candidate_list(
                    brief["issue_candidates"],
                    "No local/archive issue candidates were generated for this cycle.",
                ),
                "",
                *deadlocked_candidates_section(state),
                *deadlocked_meta_section(state),
                *no_new_work_justifications_section(state),
                "#### Feedback Slot",
                "",
                f"Recorded feedback: `{brief['recorded_feedback'].get('decision', 'none')}`"
                f" / priority `{brief['recorded_feedback'].get('priority', 'unset')}`",
                "",
                "```text",
                f"repo: {state['repo']}",
                *brief["feedback_template"],
                "```",
                "",
            ]
        )

    lines.extend(["## Paused Repos", "", markdown_list([state["repo"] for state in paused]), ""])
    lines.extend(["## Ignored Repos", "", markdown_list([state["repo"] for state in ignored]), ""])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "human-decision-packet.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "repo-review-summary.json").write_text(
        json.dumps(
            {
                "generated_on": generated_on,
                "active_count": len(active),
                "review_pending_count": len(review_pending),
                "review_execution_count": len(executed_reviews),
                "blocked_review_count": len(blocked),
                "issue_candidate_repo_count": len(issue_candidate_repos),
                "automated_gap_repo_count": len(automated_gap_repos),
                "gitnexus_preflight": gitnexus_preflight_result,
                "repos": [
                    {
                        key: value
                        for key, value in state.items()
                        if key not in {"drafts", "archive_candidates"}
                    }
                    for state in states
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="config/repo_review_registry.json")
    parser.add_argument("--profiles", default="config/repo_review_profiles.json")
    parser.add_argument("--feedback", default="config/repo_review_feedback.json")
    parser.add_argument("--output-dir", default="docs/reports/repo-review")
    parser.add_argument(
        "--status",
        action="append",
        choices=sorted(VALID_STATUSES),
        help="Status to include. Defaults to active, paused, and ignored for packet visibility.",
    )
    parser.add_argument("--max-drafts-per-repo", type=int, default=8)
    parser.add_argument("--date", default=None, help="Override generated date, YYYY-MM-DD.")
    parser.add_argument(
        "--skip-gitnexus-preflight",
        action="store_true",
        help="Skip active-repo GitNexus freshness checks before generating the packet.",
    )
    parser.add_argument(
        "--no-refresh-stale-gitnexus",
        action="store_true",
        help="Report stale/missing active GitNexus maps but do not refresh them.",
    )
    parser.add_argument("--gitnexus-bin", default="gitnexus")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry_path = Path(args.registry)
    profiles_path = Path(args.profiles)
    feedback_path = Path(args.feedback)
    output_dir = Path(args.output_dir)
    statuses = set(args.status or ["active", "paused", "ignored"])
    generated_on = args.date or date.today().isoformat()

    workspace_root, _excluded, repos, archive_paths = load_registry(registry_path)
    profiles = load_json_config(profiles_path)
    feedback_config = load_json_config(feedback_path)
    feedback_decisions = feedback_config.get("decisions", {})
    if not isinstance(feedback_decisions, dict):
        feedback_decisions = {}
    preflight_result: dict[str, Any] = {
        "enabled": False,
        "warnings": [],
        "refreshed": [],
        "records": {},
        "stale_after": [],
    }
    if not args.skip_gitnexus_preflight:
        preflight_result = gitnexus_preflight(
            workspace_root,
            repos,
            statuses,
            refresh_stale=not args.no_refresh_stale_gitnexus,
            gitnexus_bin=args.gitnexus_bin,
        )
    archive_candidates = collect_archive_candidates(archive_paths, repos)
    states = [
        collect_repo_state(
            workspace_root,
            repo,
            archive_candidates.get(repo.repo, []),
            profiles.get(repo.repo, {}) if isinstance(profiles.get(repo.repo, {}), dict) else {},
            (
                feedback_decisions.get(repo.repo, {})
                if isinstance(feedback_decisions.get(repo.repo, {}), dict)
                else {}
            ),
            preflight_result.get("records", {}).get(repo.repo, {}),
            output_dir=output_dir,
        )
        for repo in repos
        if repo.status in statuses
    ]
    for state in states:
        write_repo_artifacts(output_dir, state, max_drafts=args.max_drafts_per_repo)
    write_packet(output_dir, states, generated_on, preflight_result)
    approved_queue = write_approved_issue_queue(output_dir, states, feedback_config, generated_on)

    print(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "generated_on": generated_on,
                "output_dir": str(output_dir),
                "repo_count": len(states),
                "active_count": sum(1 for state in states if state["status"] == "active"),
                "review_pending_count": sum(
                    1
                    for state in states
                    if state["status"] == "active"
                    and state["review_status"] == PENDING_REVIEW_STATUS
                ),
                "review_execution_count": sum(
                    1
                    for state in states
                    if state["status"] == "active"
                    and state["review_execution"]["status"] == "executed"
                ),
                "issue_candidate_repo_count": sum(
                    1
                    for state in states
                    if state["status"] == "active"
                    and state["issue_queue_status"]
                    in {"round 1 candidates present", "round 2 converged"}
                ),
                "automated_gap_repo_count": sum(
                    1
                    for state in states
                    if state["status"] == "active" and state["review_execution"]["gap_count"] > 0
                ),
                "approved_issue_count": len(approved_queue["issues"]),
                "deeper_review_count": len(approved_queue["deeper_review"]),
                "gitnexus_preflight_warning_count": len(preflight_result.get("warnings", [])),
                "gitnexus_refreshed_count": len(preflight_result.get("refreshed", [])),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
