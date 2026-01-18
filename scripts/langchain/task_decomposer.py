#!/usr/bin/env python3
"""
Decompose large tasks into smaller, verifiable sub-tasks.

Run with:
    python scripts/langchain/task_decomposer.py --task "..." --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

TASK_DECOMPOSITION_PROMPT = """
This task is too large for a single agent iteration (~10 minutes):

{large_task}

Decompose into smaller, independently verifiable sub-tasks.
Each sub-task should:
- Be completable in one iteration
- Have a clear verification condition
- Not depend on un-merged work from other sub-tasks

Return the sub-tasks as a markdown bullet list.
""".strip()

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "decompose_task.md"

LIST_ITEM_REGEX = re.compile(r"^\s*(?:[-*+]|\d+[.)]|[A-Za-z][.)])\s+(.*)$")
DEPENDENCY_PHRASE_REGEX = re.compile(
    r"\b(depends on|blocked by|waiting for|post-merge|"
    r"(?:after|once|when)\b[^,]*\bmerge\b|requires\b[^.]*\bmerge\b)\b",
    re.IGNORECASE,
)
LEADING_DEPENDENCY_CLAUSE_REGEX = re.compile(r"^(?:after|once|when)\b[^,]+,\s*(.+)$", re.IGNORECASE)
LARGE_TASK_KEYWORDS = (
    "end-to-end",
    "end to end",
    "full",
    "entire",
    "overall",
    "across",
    "overhaul",
    "rewrite",
    "redesign",
    "refactor",
    "migrate",
    "migration",
    "consolidate",
    "rollout",
)
MAX_SUBTASK_WORDS = 12
LARGE_TASK_PREFIXES = (
    "define ",
    "implement ",
    "validate ",
    "document ",
    "scope ",
    "outline ",
    "plan ",
)

# Prefixes that indicate already-expanded tasks (never re-expand these)
EXPANSION_PREFIXES = (
    "define scope for:",
    "implement focused slice for:",
    "validate focused slice for:",
    "define approach for:",
)
MAX_CHILD_TITLE_LEN = 96


def _load_prompt() -> str:
    if PROMPT_PATH.is_file():
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    return TASK_DECOMPOSITION_PROMPT


def _get_llm_client(force_openai: bool = False) -> tuple[object, str] | None:
    """Get LLM client, trying GitHub Models first (cheaper), then OpenAI.

    Args:
        force_openai: If True, skip GitHub Models and use OpenAI directly.
                      Use this for retry after GitHub Models 401 error.
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")
    if not github_token and not openai_token:
        return None

    from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL

    # Try GitHub Models first (cheaper) unless forced to use OpenAI
    if github_token and not force_openai:
        return (
            ChatOpenAI(
                model=DEFAULT_MODEL,
                base_url=GITHUB_MODELS_BASE_URL,
                api_key=github_token,
                temperature=0.1,
            ),
            "github-models",
        )
    if openai_token:
        return (
            ChatOpenAI(
                model=DEFAULT_MODEL,
                api_key=openai_token,
                temperature=0.1,
            ),
            "openai",
        )
    return None


def _ensure_verification(text: str) -> str:
    if re.search(r"\bverify\b", text, re.IGNORECASE):
        return text
    inferred = _infer_verification(text)
    if inferred:
        return f"{text} (verify: {inferred})"
    return f"{text} (verify: confirm completion in repo)"


def _infer_verification(text: str) -> str | None:
    lowered = text.lower()
    if "add test" in lowered or "tests" in lowered:
        return "tests pass"
    if "update doc" in lowered or "docs" in lowered or "documentation" in lowered:
        return "docs updated"
    if "format" in lowered or "black" in lowered or "ruff format" in lowered:
        return "formatter passes"
    if "lint" in lowered or "ruff" in lowered:
        return "lint passes"
    if "typecheck" in lowered or "mypy" in lowered:
        return "typecheck passes"
    if "dependency" in lowered or "dependencies" in lowered or "bump" in lowered:
        return "dependencies updated"
    if "config" in lowered:
        return "config validated"
    return None


def _parse_subtasks(text: str) -> list[str]:
    entries: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = LIST_ITEM_REGEX.match(stripped)
        if match:
            stripped = match.group(1).strip()
        if stripped:
            entries.append(stripped)
    return entries


def _split_task_parts(task: str) -> list[str]:
    # Handle parenthesized lists intelligently: "Add stats (mean, p50, p90)" becomes
    # ["Add stats for mean", "Add stats for p50", "Add stats for p90"]
    # NOT garbage like ["Add stats (mean", "p50", "p90)"]
    paren_match = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", task)
    if paren_match:
        base = paren_match.group(1).strip()
        paren_content = paren_match.group(2).strip()
        # Check if parentheses contain a comma-separated list
        if ", " in paren_content or " and " in paren_content:
            items = [
                item.strip()
                for item in re.split(r"\s*,\s*|\s+and\s+", paren_content)
                if item.strip()
            ]
            if len(items) > 1:
                # Create meaningful sub-tasks: "Add stats for mean", "Add stats for p50", etc.
                return [f"{base} for {item}" for item in items]

    for marker in (" with ", " including "):
        if marker in task:
            base, suffix = task.split(marker, 1)
            base = base.strip()
            items = [
                item.strip() for item in re.split(r"\s*,\s*|\s+and\s+", suffix) if item.strip()
            ]
            if base and len(items) > 1:
                keyword = marker.strip()
                return [f"{base} {keyword} {item}" for item in items]
    if " and " in task:
        parts = re.split(r"\s+and\s+", task)
    elif " then " in task:
        parts = re.split(r"\s+then\s+", task)
    elif ";" in task:
        parts = [part.strip() for part in task.split(";") if part.strip()]
    elif ", " in task:
        parts = [part.strip() for part in task.split(",") if part.strip()]
    elif " / " in task:
        # Only split on spaced slashes to avoid splitting compound words
        # like "additions/removals" or paths like "src/utils"
        parts = [part.strip() for part in task.split(" / ") if part.strip()]
    else:
        parts = [task]
    return [part for part in parts if part]


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _is_large_task(task: str) -> bool:
    lowered = task.lower().strip()
    # Never re-expand already-expanded tasks (prevents recursive explosion)
    if _is_already_expanded(task):
        return False
    has_large_keyword = any(keyword in lowered for keyword in LARGE_TASK_KEYWORDS)
    if lowered.startswith(LARGE_TASK_PREFIXES):
        return has_large_keyword or _word_count(task) > MAX_SUBTASK_WORDS
    if _word_count(task) > MAX_SUBTASK_WORDS:
        return True
    return has_large_keyword


def _should_decompose(task: str) -> bool:
    parts = _split_task_parts(task)
    if len(parts) > 1:
        return True
    return _is_large_task(task)


def _is_already_expanded(task: str) -> bool:
    """Check if task already has expansion prefix (prevent recursion)."""
    lowered = task.lower().strip()
    return any(lowered.startswith(prefix) for prefix in EXPANSION_PREFIXES)


def _expand_large_task(task: str) -> list[str]:
    """Expand a large task into scope/implement/validate sub-tasks.

    Returns the original task unchanged if it already has expansion prefix
    to prevent recursive expansion (which caused issue #873, #4191).
    """
    # Guard against recursive expansion
    if _is_already_expanded(task):
        return [task]
    return [
        f"Define scope for: {task}",
        f"Implement focused slice for: {task}",
        f"Validate focused slice for: {task}",
    ]


def _strip_dependency_clause(task: str) -> str:
    match = LEADING_DEPENDENCY_CLAUSE_REGEX.match(task)
    if match:
        return match.group(1).strip()
    return task


def _contains_dependency_phrase(task: str) -> bool:
    return bool(DEPENDENCY_PHRASE_REGEX.search(task))


def _rewrite_dependency_task(task: str) -> str:
    cleaned = DEPENDENCY_PHRASE_REGEX.sub("", task).strip(" ,.-")
    if not cleaned:
        cleaned = "dependency details"
    return f"Document dependency for: {cleaned} (verify: dependency recorded)"


def _normalize_subtasks(sub_tasks: list[str]) -> list[str]:
    normalized: list[str] = []
    for task in sub_tasks:
        cleaned_task = _strip_dependency_clause(task.strip())
        for part in _split_task_parts(cleaned_task):
            cleaned = _strip_dependency_clause(part.strip())
            if not cleaned:
                continue
            if _contains_dependency_phrase(cleaned):
                cleaned = _rewrite_dependency_task(cleaned)
            if _is_large_task(cleaned) and not cleaned.lower().startswith("document dependency"):
                for scoped_task in _expand_large_task(cleaned):
                    normalized.append(_ensure_verification(scoped_task))
                continue
            normalized.append(_ensure_verification(cleaned))
    return normalized


def normalize_subtasks(sub_tasks: list[str]) -> list[str]:
    return _normalize_subtasks(sub_tasks)


def _truncate_title(text: str, max_len: int = MAX_CHILD_TITLE_LEN) -> str:
    if len(text) <= max_len:
        return text
    trimmed = text[: max_len - 3].rstrip()
    return f"{trimmed}..."


def _format_parent_reference(
    *, parent_title: str, parent_number: int | None, parent_url: str | None
) -> str:
    if parent_number is not None and parent_url:
        return f"[#{parent_number}]({parent_url})"
    if parent_number is not None:
        return f"#{parent_number}"
    if parent_url:
        return parent_url
    return parent_title or "parent issue"


def _coerce_label_names(labels: list[Any] | None) -> list[str]:
    if not labels:
        return []
    names: list[str] = []
    for label in labels:
        if isinstance(label, str):
            name = label
        elif isinstance(label, dict):
            name = label.get("name")
        else:
            name = getattr(label, "name", None)
        if name:
            cleaned = str(name).strip()
            if cleaned:
                names.append(cleaned)
    return names


def _coerce_assignee_logins(assignees: list[Any] | None) -> list[str]:
    if not assignees:
        return []
    logins: list[str] = []
    for assignee in assignees:
        if isinstance(assignee, str):
            login = assignee
        elif isinstance(assignee, dict):
            login = assignee.get("login")
        else:
            login = getattr(assignee, "login", None)
        if login:
            cleaned = str(login).strip()
            if cleaned:
                logins.append(cleaned)
    return logins


def _coerce_milestone_value(milestone: Any) -> str | int | None:
    if milestone is None:
        return None
    if isinstance(milestone, (str, int)):
        return milestone
    if isinstance(milestone, dict):
        number = milestone.get("number")
        if isinstance(number, int):
            return number
        title = milestone.get("title")
        if title:
            return str(title)
        return None
    number = getattr(milestone, "number", None)
    if isinstance(number, int):
        return number
    title = getattr(milestone, "title", None)
    if title:
        return str(title)
    return None


def build_child_issues(
    sub_tasks: list[str],
    *,
    parent_title: str,
    parent_number: int | None = None,
    parent_url: str | None = None,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    milestone: str | int | None = None,
    max_children: int | None = None,
) -> list[dict[str, Any]]:
    normalized = _normalize_subtasks(sub_tasks)
    if len(normalized) <= 1:
        return []
    if max_children is not None:
        normalized = normalized[:max_children]

    parent_ref = _format_parent_reference(
        parent_title=parent_title, parent_number=parent_number, parent_url=parent_url
    )
    child_issues: list[dict[str, Any]] = []
    preserved_labels = _coerce_label_names(labels)
    preserved_assignees = _coerce_assignee_logins(assignees)
    preserved_milestone = _coerce_milestone_value(milestone)
    for task in normalized:
        title = (
            _truncate_title(f"{parent_title}: {task}") if parent_title else _truncate_title(task)
        )
        body_lines = [
            f"Parent issue: {parent_ref}",
            "",
            "Task:",
            f"- [ ] {task}",
            "",
            "*Auto-generated by task decomposer*",
        ]
        payload: dict[str, Any] = {
            "title": title,
            "body": "\n".join(body_lines),
        }
        if preserved_labels:
            payload["labels"] = list(preserved_labels)
        if preserved_assignees:
            payload["assignees"] = list(preserved_assignees)
        if preserved_milestone is not None:
            payload["milestone"] = preserved_milestone
        child_issues.append(payload)
    return child_issues


def build_child_issues_from_parent(
    sub_tasks: list[str],
    *,
    parent_issue: dict[str, Any],
    max_children: int | None = None,
) -> list[dict[str, Any]]:
    return build_child_issues(
        sub_tasks,
        parent_title=str(parent_issue.get("title") or "").strip(),
        parent_number=parent_issue.get("number"),
        parent_url=parent_issue.get("html_url") or parent_issue.get("url"),
        labels=parent_issue.get("labels"),
        assignees=parent_issue.get("assignees"),
        milestone=parent_issue.get("milestone"),
        max_children=max_children,
    )


def _format_child_reference(child_issue: dict[str, Any]) -> str | None:
    number = child_issue.get("number") or child_issue.get("issue_number")
    url = child_issue.get("html_url") or child_issue.get("url")
    if number is None and not url:
        return None
    ref = f"[#{number}]({url})" if number is not None else str(url)
    title = child_issue.get("title")
    return f"{ref} - {title}" if title else ref


def build_parent_issue_update(parent_body: str, child_issues: list[dict[str, Any]]) -> str:
    child_refs: list[str] = []
    seen: set[str] = set()
    for child in child_issues:
        if not isinstance(child, dict):
            continue
        ref = _format_child_reference(child)
        if not ref or ref in seen:
            continue
        seen.add(ref)
        child_refs.append(ref)
    if not child_refs:
        return parent_body

    list_lines = [f"- {ref}" for ref in child_refs]
    header = "## Child Issues"
    lines = parent_body.splitlines() if parent_body else []
    if header in lines:
        header_idx = lines.index(header)
        end_idx = next(
            (
                i
                for i in range(header_idx + 1, len(lines))
                if lines[i].startswith("## ") and lines[i].strip() != header
            ),
            len(lines),
        )
        updated = []
        updated.extend(lines[:header_idx])
        updated.append(header)
        updated.append("")
        updated.extend(list_lines)
        updated.extend(lines[end_idx:])
        return "\n".join(updated).strip()

    parts = [parent_body.rstrip(), "", header, "", "\n".join(list_lines)]
    return "\n".join(part for part in parts if part).strip()


def _fallback_decompose(task: str) -> list[str]:
    task = task.strip()
    if not task:
        return []
    parts = _split_task_parts(task)
    if len(parts) > 1:
        return [_ensure_verification(f"{part}") for part in parts if part.strip()]
    return [
        _ensure_verification(f"Define approach for: {task}"),
        _ensure_verification(f"Implement: {task}"),
        _ensure_verification(f"Validate: {task}"),
    ]


def _is_github_models_auth_error(exc: Exception) -> bool:
    """Check if exception is a GitHub Models authentication error (401)."""
    exc_str = str(exc).lower()
    return "401" in exc_str and "models" in exc_str


def decompose_task(task: str, *, use_llm: bool = True) -> dict[str, Any]:
    if not task or not task.strip():
        return {"sub_tasks": [], "provider_used": None, "used_llm": False}
    if not _should_decompose(task):
        return {"sub_tasks": [], "provider_used": None, "used_llm": False}

    if use_llm:
        client_info = _get_llm_client()
        if client_info:
            client, provider = client_info
            try:
                from langchain_core.prompts import ChatPromptTemplate
            except ImportError:
                client_info = None
            else:
                prompt = _load_prompt()
                template = ChatPromptTemplate.from_template(prompt)
                chain = template | client
                try:
                    response = chain.invoke({"large_task": task})
                except Exception as e:
                    # If GitHub Models fails with 401, retry with OpenAI
                    if provider == "github-models" and _is_github_models_auth_error(e):
                        fallback_info = _get_llm_client(force_openai=True)
                        if fallback_info:
                            client, provider = fallback_info
                            chain = template | client
                            response = chain.invoke({"large_task": task})
                        else:
                            raise
                    else:
                        raise
                content = getattr(response, "content", None) or str(response)
                sub_tasks = _normalize_subtasks(_parse_subtasks(content))
                if sub_tasks:
                    return {
                        "sub_tasks": sub_tasks,
                        "provider_used": provider,
                        "used_llm": True,
                    }

    return {
        "sub_tasks": _normalize_subtasks(_fallback_decompose(task)),
        "provider_used": None,
        "used_llm": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Decompose a large task into sub-tasks.")
    parser.add_argument("--task", help="Task text to decompose.")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload to stdout.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM usage.")
    args = parser.parse_args()

    result = decompose_task(args.task or "", use_llm=not args.no_llm)
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print("\n".join(f"- {task}" for task in result["sub_tasks"]))


if __name__ == "__main__":
    main()
