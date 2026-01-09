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

LIST_ITEM_REGEX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
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
MAX_CHILD_TITLE_LEN = 96


def _load_prompt() -> str:
    if PROMPT_PATH.is_file():
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    return TASK_DECOMPOSITION_PROMPT


def _get_llm_client() -> tuple[object, str] | None:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")
    if not github_token and not openai_token:
        return None

    from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL

    if github_token:
        return (
            ChatOpenAI(
                model=DEFAULT_MODEL,
                base_url=GITHUB_MODELS_BASE_URL,
                api_key=github_token,
                temperature=0.1,
            ),
            "github-models",
        )
    return (
        ChatOpenAI(
            model=DEFAULT_MODEL,
            api_key=openai_token,
            temperature=0.1,
        ),
        "openai",
    )


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
    for marker in (" with ", " including "):
        if marker in task:
            base, suffix = task.split(marker, 1)
            base = base.strip()
            items = [
                item.strip()
                for item in re.split(r"\s*,\s*|\s+and\s+", suffix)
                if item.strip()
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
    elif " / " in task or "/" in task:
        parts = [part.strip() for part in re.split(r"\s*/\s*", task) if part.strip()]
    else:
        parts = [task]
    return [part for part in parts if part]


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _is_large_task(task: str) -> bool:
    lowered = task.lower().strip()
    has_large_keyword = any(keyword in lowered for keyword in LARGE_TASK_KEYWORDS)
    if lowered.startswith(LARGE_TASK_PREFIXES):
        return has_large_keyword or _word_count(task) > MAX_SUBTASK_WORDS
    if _word_count(task) > MAX_SUBTASK_WORDS:
        return True
    return has_large_keyword


def _expand_large_task(task: str) -> list[str]:
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


def build_child_issues(
    sub_tasks: list[str],
    *,
    parent_title: str,
    parent_number: int | None = None,
    parent_url: str | None = None,
    labels: list[str] | None = None,
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
    preserved_labels = list(labels) if labels else []
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
            payload["labels"] = preserved_labels
        if milestone is not None:
            payload["milestone"] = milestone
        child_issues.append(payload)
    return child_issues


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


def decompose_task(task: str, *, use_llm: bool = True) -> dict[str, Any]:
    if not task or not task.strip():
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
                response = chain.invoke({"large_task": task})
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
