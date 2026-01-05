#!/usr/bin/env python3
"""
Format raw issue text into the AGENT_ISSUE_TEMPLATE structure.

Run with:
    python scripts/langchain/issue_formatter.py \
        --input-file issue.md --output-file formatted.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ISSUE_FORMATTER_PROMPT = """
You are a formatting assistant. Convert the raw GitHub issue body into the
AGENT_ISSUE_TEMPLATE format with the exact section headers in order:

## Why
## Scope
## Non-Goals
## Tasks
## Acceptance Criteria
## Implementation Notes

Rules:
- Use bullet points ONLY in Tasks and Acceptance Criteria.
- Every task/criterion must be specific, verifiable, and sized for ~10 minutes.
- Use unchecked checkboxes: "- [ ]".
- Preserve file paths and concrete details when mentioned.
- If a section lacks content, use "_Not provided._" (or "- [ ] _Not provided._"
  for Tasks/Acceptance).
- Output ONLY the formatted markdown with these sections (no extra commentary).

Raw issue body:
{issue_body}
""".strip()

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "format_issue.md"
FEEDBACK_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "format_issue_feedback.md"

SECTION_ALIASES = {
    "why": ["why", "motivation", "summary", "goals"],
    "scope": ["scope", "background", "context", "overview"],
    "non_goals": ["non-goals", "nongoals", "out of scope", "constraints", "exclusions"],
    "tasks": ["tasks", "task list", "tasklist", "todo", "to do", "implementation"],
    "acceptance": [
        "acceptance criteria",
        "acceptance",
        "definition of done",
        "done criteria",
        "success criteria",
    ],
    "implementation": [
        "implementation notes",
        "implementation note",
        "notes",
        "details",
        "technical notes",
    ],
}

SECTION_TITLES = {
    "why": "Why",
    "scope": "Scope",
    "non_goals": "Non-Goals",
    "tasks": "Tasks",
    "acceptance": "Acceptance Criteria",
    "implementation": "Implementation Notes",
}

LIST_ITEM_REGEX = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
CHECKBOX_REGEX = re.compile(r"^\[([ xX])\]\s*(.*)$")


def _load_prompt() -> str:
    if PROMPT_PATH.is_file():
        base_prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    else:
        base_prompt = ISSUE_FORMATTER_PROMPT

    if FEEDBACK_PROMPT_PATH.is_file():
        feedback = FEEDBACK_PROMPT_PATH.read_text(encoding="utf-8").strip()
        if feedback:
            return f"{base_prompt}\n\n{feedback}\n"
    return base_prompt


def _get_llm_client() -> tuple[object, str] | None:
    try:
        from langchain_openai import ChatOpenAI

        from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL
    except ImportError:
        return None

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")
    if not github_token and not openai_token:
        return None

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


def _normalize_heading(text: str) -> str:
    cleaned = re.sub(r"[#*_:]+", " ", text).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _resolve_section(label: str) -> str | None:
    normalized = _normalize_heading(label)
    for key, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            if normalized == _normalize_heading(alias):
                return key
    return None


def _strip_list_marker(line: str) -> str:
    match = LIST_ITEM_REGEX.match(line)
    if not match:
        return line
    return match.group(3).strip()


def _normalize_non_action_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    in_fence = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            cleaned.append(raw)
            continue
        if in_fence:
            cleaned.append(raw)
            continue
        if not stripped:
            cleaned.append("")
            continue
        cleaned.append(_strip_list_marker(raw))
    return cleaned


def _normalize_checklist_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    in_fence = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            cleaned.append(raw)
            continue
        if in_fence:
            cleaned.append(raw)
            continue
        if not stripped:
            continue
        match = LIST_ITEM_REGEX.match(raw)
        if match:
            indent, _, remainder = match.groups()
            checkbox = CHECKBOX_REGEX.match(remainder.strip())
            if checkbox:
                mark = "x" if checkbox.group(1).lower() == "x" else " "
                text = checkbox.group(2).strip()
                if text:
                    cleaned.append(f"{indent}- [{mark}] {text}")
                continue
            cleaned.append(f"{indent}- [ ] {remainder.strip()}")
        else:
            cleaned.append(f"- [ ] {stripped}")
    return cleaned


def _parse_sections(body: str) -> tuple[dict[str, list[str]], list[str]]:
    sections: dict[str, list[str]] = {key: [] for key in SECTION_TITLES}
    preamble: list[str] = []
    current: str | None = None
    for line in body.splitlines():
        heading_match = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if heading_match:
            section_key = _resolve_section(heading_match.group(1))
            if section_key:
                current = section_key
                continue
        if re.match(r"^\s*(?:\*\*|__)(.+?)(?:\*\*|__)\s*:?\s*$", line):
            inner = re.sub(r"^\s*(?:\*\*|__)(.+?)(?:\*\*|__)\s*:?\s*$", r"\1", line)
            section_key = _resolve_section(inner)
            if section_key:
                current = section_key
                continue
        if re.match(r"^\s*[A-Za-z][A-Za-z0-9\s-]{2,}:\s*$", line):
            label = line.split(":", 1)[0]
            section_key = _resolve_section(label)
            if section_key:
                current = section_key
                continue
        if current:
            sections[current].append(line)
        else:
            preamble.append(line)
    return sections, preamble


def _format_issue_fallback(issue_body: str) -> str:
    body = issue_body.strip()
    sections, preamble = _parse_sections(body)

    if preamble and not sections["scope"]:
        sections["scope"] = preamble

    why_lines = _normalize_non_action_lines(sections["why"])
    scope_lines = _normalize_non_action_lines(sections["scope"])
    non_goals_lines = _normalize_non_action_lines(sections["non_goals"])
    impl_lines = _normalize_non_action_lines(sections["implementation"])

    tasks_lines = _normalize_checklist_lines(sections["tasks"])
    acceptance_lines = _normalize_checklist_lines(sections["acceptance"])

    def join_or_placeholder(lines: list[str], placeholder: str) -> str:
        content = "\n".join(line for line in lines).strip()
        return content if content else placeholder

    why_text = join_or_placeholder(why_lines, "_Not provided._")
    scope_text = join_or_placeholder(scope_lines, "_Not provided._")
    non_goals_text = join_or_placeholder(non_goals_lines, "_Not provided._")
    impl_text = join_or_placeholder(impl_lines, "_Not provided._")
    tasks_text = join_or_placeholder(tasks_lines, "- [ ] _Not provided._")
    acceptance_text = join_or_placeholder(acceptance_lines, "- [ ] _Not provided._")

    parts = [
        "## Why",
        "",
        why_text,
        "",
        "## Scope",
        "",
        scope_text,
        "",
        "## Non-Goals",
        "",
        non_goals_text,
        "",
        "## Tasks",
        "",
        tasks_text,
        "",
        "## Acceptance Criteria",
        "",
        acceptance_text,
        "",
        "## Implementation Notes",
        "",
        impl_text,
    ]
    return "\n".join(parts).strip()


def _formatted_output_valid(text: str) -> bool:
    if not text:
        return False
    required = ["## Tasks", "## Acceptance Criteria"]
    return all(section in text for section in required)


def _select_code_fence(text: str) -> str:
    runs = [len(match.group(0)) for match in re.finditer(r"`+", text)]
    fence_len = max(3, max(runs, default=0) + 1)
    return "`" * fence_len


def _append_raw_issue_section(formatted: str, issue_body: str) -> str:
    raw = issue_body.strip()
    if not raw:
        return formatted
    marker = "<summary>Original Issue</summary>"
    if marker in formatted:
        return formatted
    fence = _select_code_fence(raw)
    details = (
        "\n\n<details>\n"
        "<summary>Original Issue</summary>\n\n"
        f"{fence}text\n{raw}\n{fence}\n"
        "</details>"
    )
    return f"{formatted.rstrip()}{details}\n"


def format_issue_body(issue_body: str, *, use_llm: bool = True) -> dict[str, Any]:
    if not issue_body:
        issue_body = ""

    if use_llm:
        client_info = _get_llm_client()
        if client_info:
            client, provider = client_info
            try:
                from langchain_core.prompts import ChatPromptTemplate

                prompt = _load_prompt()
                template = ChatPromptTemplate.from_template(prompt)
                chain = template | client
                response = chain.invoke({"issue_body": issue_body})
                content = getattr(response, "content", None) or str(response)
                formatted = content.strip()
                if _formatted_output_valid(formatted):
                    formatted = _append_raw_issue_section(formatted, issue_body)
                    return {
                        "formatted_body": formatted,
                        "provider_used": provider,
                        "used_llm": True,
                    }
            except (ImportError, Exception):
                # Fall through to fallback if LLM fails (import, auth, API errors)
                pass

    formatted = _append_raw_issue_section(_format_issue_fallback(issue_body), issue_body)
    return {
        "formatted_body": formatted,
        "provider_used": None,
        "used_llm": False,
    }


def build_label_transition() -> dict[str, list[str]]:
    return {
        "add": ["agents:formatted"],
        "remove": ["agents:format"],
    }


def _load_input(args: argparse.Namespace) -> str:
    if args.input_file:
        return Path(args.input_file).read_text(encoding="utf-8")
    if args.input_text:
        return args.input_text
    return sys.stdin.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Format issues into AGENT_ISSUE_TEMPLATE.")
    parser.add_argument("--input-file", help="Path to raw issue text.")
    parser.add_argument("--input-text", help="Raw issue text (inline).")
    parser.add_argument("--output-file", help="Path to write formatted output.")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload to stdout.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM usage.")
    args = parser.parse_args()

    raw = _load_input(args)
    result = format_issue_body(raw, use_llm=not args.no_llm)

    if args.output_file:
        Path(args.output_file).write_text(result["formatted_body"], encoding="utf-8")

    if args.json:
        payload = {
            "formatted_body": result["formatted_body"],
            "provider_used": result.get("provider_used"),
            "used_llm": result.get("used_llm", False),
            "labels": build_label_transition(),
        }
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print(result["formatted_body"])


if __name__ == "__main__":
    main()
