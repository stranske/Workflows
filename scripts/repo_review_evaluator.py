#!/usr/bin/env python3
"""Generate local weekly repo review packets and issue drafts.

This script is intentionally local-first. It reads a registry of repos, inspects
local clones, extracts unresolved draft issues from Issues.txt, and writes a
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
ISSUE_HEADING_RE = re.compile(
    r"^(?:#+\s*)?(?:Issue\s+)?(?P<num>\d+)(?:[\).:]|\s+[-–—])\s*(?P<title>.+)$",
    re.I,
)
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
    return result.stdout.strip()


def status_path(status_line: str) -> str:
    return status_line[3:].strip() if len(status_line) > 3 else status_line.strip()


def is_generated_dirty_path(status_line: str) -> bool:
    path = status_path(status_line)
    return (
        path.startswith(GENERATED_DIRTY_PATH_PREFIXES)
        or any(part in path for part in GENERATED_DIRTY_PATH_PARTS)
        or path.endswith(GENERATED_DIRTY_SUFFIXES)
    )


def material_status_lines(status_lines: list[str]) -> list[str]:
    return [line for line in status_lines if not is_generated_dirty_path(line)]


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


def load_registry(path: Path) -> tuple[Path, list[str], list[RepoConfig]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    workspace_root = Path(data.get("workspace_root", "."))
    if not workspace_root.is_absolute():
        workspace_root = (path.parent.parent / workspace_root).resolve()

    excluded = [str(item).lower() for item in data.get("excluded_repo_names", [])]
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
    return workspace_root, excluded, repos


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


def collect_repo_state(workspace_root: Path, repo: RepoConfig) -> dict[str, Any]:
    repo_path = workspace_root / repo.local_path
    status_lines = run_git(repo_path, ["status", "--short"]).splitlines()
    material_lines = material_status_lines(status_lines)
    branch = run_git(repo_path, ["branch", "--show-current"])
    origin = run_git(repo_path, ["remote", "get-url", "origin"])
    last_commit = run_git(repo_path, ["log", "-1", "--format=%cs %h %s"])
    drafts = extract_issue_drafts(repo_path / "Issues.txt")
    design_files = [
        rel
        for rel in ["README.md", "docs/DEVELOPMENT_PLAN.md", "docs/plans/LONG_TERM_PLAN.md"]
        if (repo_path / rel).is_file()
    ]
    report_files = (
        sorted((repo_path / "docs" / "reports").glob("*.md"))
        if (repo_path / "docs" / "reports").is_dir()
        else []
    )

    decision = "not scheduled"
    if repo.status != "active":
        decision = "not scheduled"
    elif not repo_path.exists():
        decision = "needs human"
    elif drafts:
        decision = "productive"
    elif material_lines:
        decision = "needs human"
    else:
        decision = "not productive"

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
        "generated_dirty_count": len(status_lines) - len(material_lines),
        "dirty_preview": status_lines[:15],
        "material_dirty_preview": material_lines[:15],
        "remote_open_issue_count": remote_open_issue_count(repo.repo),
        "issue_draft_count": len(drafts),
        "issue_open_task_count": sum(draft.open_tasks for draft in drafts),
        "issue_done_task_count": sum(draft.done_tasks for draft in drafts),
        "design_files": design_files,
        "report_files": [str(path.relative_to(repo_path)) for path in report_files[:10]],
        "decision": decision,
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
        f"- Decision: `{state['decision']}`",
        f"- Local path: `{state['local_path']}`",
        f"- Origin: `{state['origin'] or 'unknown'}`",
        f"- Branch: `{state['branch'] or 'unknown'}`",
        f"- Last commit: `{state['last_commit'] or 'unknown'}`",
        f"- Dirty local changes: `{state['dirty_count']}`",
        f"- Material dirty local changes: `{state['material_dirty_count']}`",
        f"- Generated/cache dirty local changes: `{state['generated_dirty_count']}`",
        f"- Remote open GitHub issues: `{state['remote_open_issue_count'] if state['remote_open_issue_count'] is not None else 'unknown'}`",
        f"- Issue drafts found: `{state['issue_draft_count']}`",
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
        "## Existing Reports",
        "",
        markdown_list(state["report_files"]),
        "",
        "## Dirty Preview",
        "",
        markdown_list(state["material_dirty_preview"]),
        "",
    ]
    (repo_dir / "state.md").write_text("\n".join(state_md), encoding="utf-8")

    draft_lines = [
        f"# Issue Drafts: {state['repo']}",
        "",
        "These are local drafts for human approval. No remote issues were created.",
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
    if state["issue_draft_count"] > max_drafts:
        draft_lines.append(
            f"_Only the first {max_drafts} drafts are shown; {state['issue_draft_count'] - max_drafts} additional drafts remain in `Issues.txt`._"
        )
    (repo_dir / "issue-drafts.md").write_text("\n".join(draft_lines), encoding="utf-8")


def write_packet(output_dir: Path, states: list[dict[str, Any]], generated_on: str) -> None:
    active = [state for state in states if state["status"] == "active"]
    paused = [state for state in states if state["status"] == "paused"]
    ignored = [state for state in states if state["status"] == "ignored"]
    productive = [state for state in active if state["decision"] == "productive"]
    needs_human = [state for state in active if state["decision"] == "needs human"]

    lines = [
        f"# Weekly Repo Review Decision Packet - {generated_on}",
        "",
        "This packet queues human decisions before any remote issue creation.",
        "",
        "## Summary",
        "",
        f"- Active repos evaluated: `{len(active)}`",
        f"- Productive issue-draft repos: `{len(productive)}`",
        f"- Active repos needing human clarification: `{len(needs_human)}`",
        f"- Paused repos tracked: `{len(paused)}`",
        f"- Ignored repos tracked: `{len(ignored)}`",
        "",
        "## Human Approval Queue",
        "",
    ]
    for state in active:
        safe_name = state["repo"].replace("/", "__")
        lines.extend(
            [
                f"### {state['repo']}",
                "",
                f"- Decision: `{state['decision']}`",
                f"- Drafts: `{state['issue_draft_count']}`",
                f"- Remote open GitHub issues: `{state['remote_open_issue_count'] if state['remote_open_issue_count'] is not None else 'unknown'}`",
                f"- Unchecked checklist boxes in local `Issues.txt` drafts: `{state['issue_open_task_count']}`",
                f"- Material dirty local changes: `{state['material_dirty_count']}`",
                f"- Generated/cache dirty local changes: `{state['generated_dirty_count']}`",
                f"- Review artifacts: `repos/{safe_name}/state.md`, `repos/{safe_name}/issue-drafts.md`",
                "- Human action: approve drafts, edit drafts, pause repo, or mark needs-human.",
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
                "productive_count": len(productive),
                "needs_human_count": len(needs_human),
                "repos": [
                    {key: value for key, value in state.items() if key != "drafts"}
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

    workspace_root, _excluded, repos = load_registry(registry_path)
    states = [collect_repo_state(workspace_root, repo) for repo in repos if repo.status in statuses]
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
                "productive_count": sum(
                    1
                    for state in states
                    if state["status"] == "active" and state["decision"] == "productive"
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
