#!/usr/bin/env python3
"""
Extract contextual details from an issue body (and optional comments).

Run with:
    python scripts/langchain/context_extractor.py --input-file issue.md --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path

CONTEXT_EXTRACTOR_PROMPT = """
From this issue and related discussion, extract:
1. Design constraints or decisions made
2. Related issues/PRs that provide context
3. External references (docs, APIs, specifications)
4. Known blockers or dependencies

Format as a "## Context for Agent" section that provides helpful background
without creating actionable tasks.

Issue body:
{issue_body}

Related comments (if any):
{comments}
""".strip()

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "context_extract.md"

REFERENCE_REGEX = re.compile(r"https?://[^\s)>\"]+")
ISSUE_REF_REGEX = re.compile(r"\b[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+\b|(?<!\w)#\d+\b")
LIST_ITEM_REGEX = re.compile(r"^\s*[-*+]\s+(.*)$")
CHECKBOX_REGEX = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+")

DECISION_KEYWORDS = (
    "decision",
    "decided",
    "constraint",
    "must",
    "should",
    "cannot",
    "can't",
    "requirement",
    "requires",
    "limit",
    "avoid",
    "keep",
)
BLOCKER_KEYWORDS = (
    "blocked",
    "depends on",
    "dependency",
    "dependent on",
    "waiting on",
    "after",
    "until",
    "blocked by",
)

SECTION_TITLE = "## Context for Agent"


def _load_prompt() -> str:
    if PROMPT_PATH.is_file():
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    return CONTEXT_EXTRACTOR_PROMPT


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


def _strip_code_fences(lines: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        cleaned.append(line)
    return cleaned


def _normalize_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    if stripped.startswith("#"):
        return ""
    if CHECKBOX_REGEX.match(stripped):
        return ""
    match = LIST_ITEM_REGEX.match(stripped)
    if match:
        stripped = match.group(1).strip()
    return stripped


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _extract_keyword_lines(lines: Iterable[str], keywords: tuple[str, ...]) -> list[str]:
    results: list[str] = []
    for line in lines:
        normalized = _normalize_line(line)
        if not normalized:
            continue
        lowered = normalized.lower()
        if any(keyword in lowered for keyword in keywords):
            results.append(normalized)
    return _unique(results)


def _extract_issue_refs(text: str) -> list[str]:
    return _unique([match.group(0) for match in ISSUE_REF_REGEX.finditer(text)])


def _extract_references(text: str) -> list[str]:
    refs: list[str] = []
    for match in REFERENCE_REGEX.finditer(text):
        candidate = match.group(0).rstrip(".,;:)")
        refs.append(candidate)
    return _unique(refs)


def _format_context_section(
    *,
    decisions: list[str],
    related: list[str],
    references: list[str],
    blockers: list[str],
) -> str:
    if not any((decisions, related, references, blockers)):
        return ""
    lines: list[str] = [SECTION_TITLE]
    if decisions:
        lines.extend(["", "### Design Decisions & Constraints"])
        lines.extend(f"- {entry}" for entry in decisions)
    if related:
        lines.extend(["", "### Related Issues/PRs"])
        lines.extend(f"- {entry}" for entry in related)
    if references:
        lines.extend(["", "### References"])
        lines.extend(f"- {entry}" for entry in references)
    if blockers:
        lines.extend(["", "### Blockers & Dependencies"])
        lines.extend(f"- {entry}" for entry in blockers)
    return "\n".join(lines).strip()


def _fallback_extract(issue_body: str, comments: list[str] | None) -> str:
    combined_lines = issue_body.splitlines()
    if comments:
        for comment in comments:
            combined_lines.extend(comment.splitlines())

    filtered_lines = _strip_code_fences(combined_lines)
    decisions = _extract_keyword_lines(filtered_lines, DECISION_KEYWORDS)
    blockers = _extract_keyword_lines(filtered_lines, BLOCKER_KEYWORDS)

    combined_text = "\n".join(filtered_lines)
    related = _extract_issue_refs(combined_text)
    references = _extract_references(combined_text)

    return _format_context_section(
        decisions=decisions,
        related=related,
        references=references,
        blockers=blockers,
    )


def _is_github_models_auth_error(exc: Exception) -> bool:
    """Check if exception is a GitHub Models authentication error (401)."""
    exc_str = str(exc).lower()
    return "401" in exc_str and "models" in exc_str


def extract_context(
    issue_body: str,
    comments: list[str] | None = None,
    *,
    use_llm: bool = True,
) -> dict[str, str | bool | None]:
    if not issue_body:
        issue_body = ""

    comments = comments or []

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
                    response = chain.invoke(
                        {
                            "issue_body": issue_body,
                            "comments": "\n\n".join(comments) if comments else "_None._",
                        }
                    )
                except Exception as e:
                    # If GitHub Models fails with 401, retry with OpenAI
                    if provider == "github-models" and _is_github_models_auth_error(e):
                        fallback_info = _get_llm_client(force_openai=True)
                        if fallback_info:
                            client, provider = fallback_info
                            chain = template | client
                            response = chain.invoke(
                                {
                                    "issue_body": issue_body,
                                    "comments": "\n\n".join(comments) if comments else "_None._",
                                }
                            )
                        else:
                            raise
                    else:
                        raise
                content = (getattr(response, "content", None) or str(response)).strip()
                return {
                    "context_section": content,
                    "provider_used": provider,
                    "used_llm": True,
                }

    return {
        "context_section": _fallback_extract(issue_body, comments),
        "provider_used": None,
        "used_llm": False,
    }


def _load_input(args: argparse.Namespace) -> str:
    if args.input_file:
        return Path(args.input_file).read_text(encoding="utf-8")
    if args.input_text:
        return args.input_text
    return sys.stdin.read()


def _load_comments(args: argparse.Namespace) -> list[str]:
    if args.comments_file:
        return json.loads(Path(args.comments_file).read_text(encoding="utf-8"))
    if args.comments_text:
        return [args.comments_text]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract contextual notes for agent PRs.")
    parser.add_argument("--input-file", help="Path to raw issue text.")
    parser.add_argument("--input-text", help="Raw issue text (inline).")
    parser.add_argument(
        "--comments-file",
        help="Path to JSON array of comments to enrich context extraction.",
    )
    parser.add_argument("--comments-text", help="Inline comment text.")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload to stdout.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM usage.")
    args = parser.parse_args()

    raw = _load_input(args)
    comments = _load_comments(args)
    result = extract_context(raw, comments=comments, use_llm=not args.no_llm)

    if args.json:
        print(json.dumps(result, ensure_ascii=True))
    else:
        print(result["context_section"])


if __name__ == "__main__":
    main()
