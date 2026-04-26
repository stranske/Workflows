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
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

VALID_STATUSES = {"active", "paused", "ignored", "needs-human"}
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
GENERATED_DIRTY_FILENAMES = {"workloop-state.md"}
HELPER_DIRTY_FILENAMES = {"Issues.txt"}
DESIGN_DOC_EXCLUDED_PREFIXES = (
    ".github/",
    ".venv/",
    "archive/",
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
    "src",
    "app",
    "lib",
    "packages",
    "dashboard",
    "frontend",
    "trip_planner",
    "scripts",
    "tests",
    ".github/workflows",
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


def run_git(repo_path: Path, args: list[str]) -> str:
    if not (repo_path / ".git").exists() and not (repo_path / ".git").is_file():
        return ""
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=False,
        capture_output=True,
        text=True,
    )
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


def is_helper_dirty_path(status_line: str) -> bool:
    return status_path(status_line) in HELPER_DIRTY_FILENAMES


def helper_status_lines(status_lines: list[str]) -> list[str]:
    return [
        line
        for line in status_lines
        if not is_generated_dirty_path(line) and is_helper_dirty_path(line)
    ]


def review_blocking_status_lines(status_lines: list[str]) -> list[str]:
    return [
        line
        for line in status_lines
        if not is_generated_dirty_path(line) and not is_helper_dirty_path(line)
    ]


def issue_queue_status(drafts: list[IssueDraft], archive_candidates: list[ArchiveCandidate]) -> str:
    if drafts or archive_candidates:
        return "draft candidates present"
    return "no current draft candidates"


def review_status(repo: RepoConfig, repo_path: Path, blocking_lines: list[str]) -> str:
    if repo.status != "active":
        return "not scheduled"
    if not repo_path.exists():
        return "missing local clone"
    if blocking_lines:
        return "blocked by non-helper local changes"
    return "pending standardized review"


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


def remote_open_issue_count(repo: str) -> int | None:
    if shutil.which("gh") is None:
        return None
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
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    return len(payload)


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


def title_from_recommendation(text: str) -> str:
    title = text.strip().rstrip(".")
    title = re.sub(r"\s+", " ", title)
    if len(title) > 140:
        title = title[:137].rstrip() + "..."
    return title


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
) -> dict[str, Any]:
    repo_path = workspace_root / repo.local_path
    status_lines = run_git(repo_path, ["status", "--short"]).splitlines()
    material_lines = material_status_lines(status_lines)
    helper_lines = helper_status_lines(status_lines)
    blocking_lines = review_blocking_status_lines(status_lines)
    branch = run_git(repo_path, ["branch", "--show-current"])
    origin = run_git(repo_path, ["remote", "get-url", "origin"])
    last_commit = run_git(repo_path, ["log", "-1", "--format=%cs %h %s"])
    drafts = extract_issue_drafts(repo_path / "Issues.txt")
    design_files = collect_design_files(repo_path)
    implementation_areas = collect_implementation_areas(repo_path)
    report_files = (
        sorted((repo_path / "docs" / "reports").glob("*.md"))
        if (repo_path / "docs" / "reports").is_dir()
        else []
    )

    archive_candidates = archive_candidates or []
    current_review_status = review_status(repo, repo_path, blocking_lines)
    current_issue_queue_status = issue_queue_status(drafts, archive_candidates)

    return {
        "repo": repo.repo,
        "local_path": str(repo_path),
        "status": repo.status,
        "cadence": repo.cadence,
        "decision_anchor": repo.decision_anchor,
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
        "remote_open_issue_count": remote_open_issue_count(repo.repo),
        "review_status": current_review_status,
        "issue_queue_status": current_issue_queue_status,
        "issue_draft_count": len(drafts),
        "archive_candidate_count": len(archive_candidates),
        "issue_open_task_count": sum(draft.open_tasks for draft in drafts),
        "issue_done_task_count": sum(draft.done_tasks for draft in drafts),
        "design_files": design_files,
        "design_source_count": len(design_files),
        "implementation_areas": implementation_areas,
        "report_files": [str(path.relative_to(repo_path)) for path in report_files[:10]],
        "decision": current_review_status,
        "review_dimensions": list(REVIEW_DIMENSIONS),
        "drafts": [
            {
                "number": draft.number,
                "title": draft.title,
                "open_tasks": draft.open_tasks,
                "done_tasks": draft.done_tasks,
                "body": draft.body,
            }
            for draft in drafts
        ],
        "archive_candidates": [
            {
                "title": candidate.title,
                "source_file": candidate.source_file,
                "thread_name": candidate.thread_name,
                "timestamp": candidate.timestamp,
                "excerpt": candidate.excerpt,
            }
            for candidate in archive_candidates
        ],
    }


def markdown_list(items: list[str], empty: str = "None found.") -> str:
    if not items:
        return empty
    return "\n".join(f"- `{item}`" for item in items)


def write_repo_artifacts(output_dir: Path, state: dict[str, Any], max_drafts: int) -> None:
    safe_name = state["repo"].replace("/", "__")
    repo_dir = output_dir / "repos" / safe_name
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "decision.json").write_text(
        json.dumps({key: value for key, value in state.items() if key != "drafts"}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    state_md = [
        f"# Repo Review State: {state['repo']}",
        "",
        f"- Status: `{state['status']}`",
        f"- Review status: `{state['review_status']}`",
        f"- Issue queue status: `{state['issue_queue_status']}`",
        f"- Local path: `{state['local_path']}`",
        f"- Origin: `{state['origin'] or 'unknown'}`",
        f"- Branch: `{state['branch'] or 'unknown'}`",
        f"- Last commit: `{state['last_commit'] or 'unknown'}`",
        f"- Dirty local changes: `{state['dirty_count']}`",
        f"- Non-generated local changes: `{state['material_dirty_count']}`",
        f"- Nonblocking helper local changes: `{state['helper_dirty_count']}`",
        f"- Review-blocking local changes: `{state['review_blocking_dirty_count']}`",
        f"- Generated/cache dirty local changes: `{state['generated_dirty_count']}`",
        f"- Remote open GitHub issues: `{state['remote_open_issue_count'] if state['remote_open_issue_count'] is not None else 'unknown'}`",
        f"- Issue drafts found: `{state['issue_draft_count']}`",
        f"- Archive-derived candidates found: `{state['archive_candidate_count']}`",
        f"- Design source files found: `{state['design_source_count']}`",
        f"- Unchecked checklist boxes in local `Issues.txt` drafts: `{state['issue_open_task_count']}`",
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
        "- Current worksheet status: pending review until a human or automation fills in evidence and findings.",
        "- Completion standard: no issue should be considered ready unless the review identifies the design commitment, current evidence, missing behavior, and a test or live-smoke acceptance gate.",
        "",
        "## Current Signals",
        "",
        f"- Review status: `{state['review_status']}`",
        f"- Issue queue status: `{state['issue_queue_status']}`",
        f"- Existing local issue drafts: `{state['issue_draft_count']}`",
        f"- Archive-derived candidates: `{state['archive_candidate_count']}`",
        f"- Remote open GitHub issues: `{state['remote_open_issue_count'] if state['remote_open_issue_count'] is not None else 'unknown'}`",
        f"- Non-generated local changes: `{state['material_dirty_count']}`",
        f"- Nonblocking helper local changes: `{state['helper_dirty_count']}`",
        f"- Review-blocking local changes: `{state['review_blocking_dirty_count']}`",
        "",
        "## Design Sources To Read",
        "",
        markdown_list(state["design_files"]),
        "",
        "## Implementation Areas To Inspect",
        "",
        markdown_list(format_implementation_areas(state["implementation_areas"])),
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
            "- non-goals that prevent scaffold-only completion claims;",
            "- tasks that a coding agent can complete;",
            "- acceptance criteria with a failing test, smoke test, or documented live-verification gate.",
            "",
        ]
    )
    (repo_dir / "design-review.md").write_text("\n".join(review_lines), encoding="utf-8")

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


def write_packet(output_dir: Path, states: list[dict[str, Any]], generated_on: str) -> None:
    active = [state for state in states if state["status"] == "active"]
    paused = [state for state in states if state["status"] == "paused"]
    ignored = [state for state in states if state["status"] == "ignored"]
    review_pending = [
        state for state in active if state["review_status"] == "pending standardized review"
    ]
    blocked = [state for state in active if state["review_status"] != "pending standardized review"]
    issue_candidate_repos = [
        state for state in active if state["issue_queue_status"] == "draft candidates present"
    ]

    lines = [
        f"# Weekly Design Review Decision Packet - {generated_on}",
        "",
        "This packet standardizes design-vs-implementation review before any remote issue creation.",
        "",
        "## Summary",
        "",
        f"- Active repos scheduled for review: `{len(active)}`",
        f"- Active repos pending standardized review: `{len(review_pending)}`",
        f"- Active repos blocked before review: `{len(blocked)}`",
        f"- Active repos with issue-draft inputs: `{len(issue_candidate_repos)}`",
        f"- Paused repos tracked: `{len(paused)}`",
        f"- Ignored repos tracked: `{len(ignored)}`",
        "",
        "## Standard Review Process",
        "",
        "1. Read the design sources and registry decision anchor.",
        "2. Inspect implementation areas and distinguish real behavior from scaffolds or fixtures.",
        "3. Check tests, smoke paths, persistence, integrations, and workflow handoffs.",
        "4. Use archive-derived candidates as precedent, not as automatically approved issues.",
        "5. Generate or approve issue drafts only for verified design/readiness gaps.",
        "",
        "## Human Review Queue",
        "",
    ]
    for state in active:
        safe_name = state["repo"].replace("/", "__")
        lines.extend(
            [
                f"### {state['repo']}",
                "",
                f"- Review status: `{state['review_status']}`",
                f"- Issue queue status: `{state['issue_queue_status']}`",
                f"- Design source files: `{state['design_source_count']}`",
                f"- Existing local issue drafts: `{state['issue_draft_count']}`",
                f"- Archive-derived candidates: `{state['archive_candidate_count']}`",
                f"- Remote open GitHub issues: `{state['remote_open_issue_count'] if state['remote_open_issue_count'] is not None else 'unknown'}`",
                f"- Non-generated local changes: `{state['material_dirty_count']}`",
                f"- Nonblocking helper local changes: `{state['helper_dirty_count']}`",
                f"- Review-blocking local changes: `{state['review_blocking_dirty_count']}`",
                f"- Generated/cache dirty local changes: `{state['generated_dirty_count']}`",
                f"- Review artifacts: `repos/{safe_name}/design-review.md`, `repos/{safe_name}/state.md`, `repos/{safe_name}/issue-drafts.md`",
                "- Human action: conduct the standardized review, then approve/edit/defer issue drafts.",
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
                "blocked_review_count": len(blocked),
                "issue_candidate_repo_count": len(issue_candidate_repos),
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
    parser.add_argument("--output-dir", default="docs/reports/repo-review")
    parser.add_argument(
        "--status",
        action="append",
        choices=sorted(VALID_STATUSES),
        help="Status to include. Defaults to active, paused, and ignored for packet visibility.",
    )
    parser.add_argument("--max-drafts-per-repo", type=int, default=8)
    parser.add_argument("--date", default=None, help="Override generated date, YYYY-MM-DD.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry_path = Path(args.registry)
    output_dir = Path(args.output_dir)
    statuses = set(args.status or ["active", "paused", "ignored"])
    generated_on = args.date or date.today().isoformat()

    workspace_root, _excluded, repos, archive_paths = load_registry(registry_path)
    archive_candidates = collect_archive_candidates(archive_paths, repos)
    states = [
        collect_repo_state(workspace_root, repo, archive_candidates.get(repo.repo, []))
        for repo in repos
        if repo.status in statuses
    ]
    for state in states:
        write_repo_artifacts(output_dir, state, max_drafts=args.max_drafts_per_repo)
    write_packet(output_dir, states, generated_on)

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
                    and state["review_status"] == "pending standardized review"
                ),
                "issue_candidate_repo_count": sum(
                    1
                    for state in states
                    if state["status"] == "active"
                    and state["issue_queue_status"] == "draft candidates present"
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
