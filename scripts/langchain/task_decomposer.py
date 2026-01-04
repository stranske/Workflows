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
    return f"{text} (verify: confirm completion in repo)"


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
    if " and " in task:
        parts = re.split(r"\s+and\s+", task)
    elif ", " in task:
        parts = [part.strip() for part in task.split(",") if part.strip()]
    elif " / " in task or "/" in task:
        parts = [part.strip() for part in re.split(r"\s*/\s*", task) if part.strip()]
    else:
        parts = [task]
    return [part for part in parts if part]


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
                sub_tasks = [_ensure_verification(item) for item in _parse_subtasks(content)]
                if sub_tasks:
                    return {
                        "sub_tasks": sub_tasks,
                        "provider_used": provider,
                        "used_llm": True,
                    }

    return {"sub_tasks": _fallback_decompose(task), "provider_used": None, "used_llm": False}


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
