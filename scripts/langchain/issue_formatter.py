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

try:
    from scripts.langchain.injection_guard import check_prompt_injection
    from scripts.langchain.issue_pr_context import (
        ContextOptions,
        already_conformant,
        build_formatted_body_marker,
        build_issue_context,
        reuse_formatted_body,
    )
    from scripts.langchain.trace_utils import TraceInfo, invoke_with_trace
except ImportError:  # pragma: no cover - fallback for direct invocation
    from injection_guard import check_prompt_injection
    from issue_pr_context import (
        ContextOptions,
        already_conformant,
        build_formatted_body_marker,
        build_issue_context,
        reuse_formatted_body,
    )
    from trace_utils import TraceInfo, invoke_with_trace

# Maximum issue body size to prevent OpenAI rate limit errors (30k TPM limit)
# ~4 chars per token, so 50k chars ≈ 12.5k tokens, leaving headroom for prompt + output
MAX_ISSUE_BODY_SIZE = 50000

# Workflow tags written into the reuse marker. Tagging every stage of the
# auto-pilot format -> optimize -> apply chain lets any stage detect a body it (or
# a sibling stage) already formatted and skip re-deriving it, which is the
# primary defense against re-run amplification.
REUSE_MARKER_WORKFLOWS = (
    "agents-auto-pilot",
    "agents-issue-optimizer",
    "agents-63-issue-intake",
    "issue_formatter",
    "issue_optimizer",
)


def _with_reuse_marker(formatted: str) -> str:
    """Append (or refresh) the reuse marker that lets later stages skip re-formatting.

    The marker stores a sha256 fingerprint of the formatted body (hash-only). A
    stale marker (body edited after formatting) simply fails the hash check
    downstream and is ignored, so this is always safe to (re)write.
    """
    body = _strip_reuse_marker(formatted).rstrip()
    marker = build_formatted_body_marker(
        workflows=list(REUSE_MARKER_WORKFLOWS),
        formatted_body=body,
        embed_body=False,  # hash-only: the formatted body is written back in full anyway
    )
    return f"{body}\n\n{marker}\n"


def _strip_reuse_marker(text: str) -> str:
    try:
        from scripts.langchain.issue_pr_context import MARKER_RE
    except ImportError:  # pragma: no cover - fallback for direct invocation
        from issue_pr_context import MARKER_RE

    return MARKER_RE.sub("", text).rstrip()


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

Length & scope discipline (improve clarity, do NOT inflate):
- Improve clarity WITHOUT increasing total length. Do not add a task, criterion,
  or sentence unless it fills a genuinely missing mandatory section.
- Preserve scope; do NOT invent file paths, functions, tests, or criteria the
  source does not imply, and do NOT manufacture prose to fill placeholders.
- Never restate the same point under two headings; never split a task that is
  already a single ~10-minute action.

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

LIST_ITEM_REGEX = re.compile(r"^(\s*)([-*+]|\d+[.)]|[A-Za-z][.)])\s+(.*)$")
CHECKBOX_REGEX = re.compile(r"^\[([ xX])\]\s*(.*)$")


def _context_token_budget() -> int:
    raw = os.environ.get("ISSUE_PR_CONTEXT_TOKEN_BUDGET", "")
    return int(raw) if raw.isdigit() and int(raw) > 0 else 4000


def _context_workflow(default: str) -> str:
    return os.environ.get("ISSUE_PR_CONTEXT_WORKFLOW") or default


def _capped_issue_body(issue_body: str, workflow: str) -> str:
    context = build_issue_context(
        {"body": issue_body},
        ContextOptions(
            token_budget=_context_token_budget(),
            downstream_workflow=workflow,
        ),
    )
    return context["formatted_body"]


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


def _get_llm_client(force_openai: bool = False) -> tuple[object, str] | None:
    """Get LLM client, trying GitHub Models first (cheaper), then OpenAI.

    Args:
        force_openai: If True, skip GitHub Models and use OpenAI directly.
                      Use this for retry after GitHub Models 401 error.
    """
    try:
        from tools.langchain_client import build_chat_client
    except ImportError:
        return None

    resolved = build_chat_client(force_openai=force_openai)
    if not resolved:
        return None
    return resolved.client, resolved.provider


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
            continue
        if in_fence:
            continue
        if stripped in {"---", "<details>", "</details>"}:
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
    code_fence_marker: str | None = None  # exact opening fence (e.g. ```, ````)
    in_details_block = False
    for line in body.splitlines():
        stripped = line.strip()
        # Track code fences — match the exact opening fence length to avoid
        # being fooled by nested fences of different lengths (e.g. ``` inside ````)
        fence_match = re.match(r"^(`{3,})", stripped)
        if fence_match:
            if code_fence_marker is None:
                code_fence_marker = fence_match.group(1)
            elif len(fence_match.group(1)) >= len(code_fence_marker):
                code_fence_marker = None
        if code_fence_marker is not None:
            if current:
                sections[current].append(line)
            else:
                preamble.append(line)
            continue
        # Stop parsing at <details> blocks (Original Issue metadata).
        # Handle both multi-line and inline <details>...</details> on one line.
        lower_stripped = stripped.lower()
        if lower_stripped.startswith("<details") and not in_details_block:
            # Check if </details> also appears on the same line (inline block)
            if "</details" in lower_stripped:
                # Entire block on one line — preserve it but don't enter state
                if current:
                    sections[current].append(line)
                else:
                    preamble.append(line)
                continue
            in_details_block = True
        if in_details_block:
            if "</details" in lower_stripped:
                in_details_block = False
            # Preserve <details> content under the current section so it
            # survives the round-trip, but don't parse headings from it.
            if current:
                sections[current].append(line)
            else:
                preamble.append(line)
            continue
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


ORIGINAL_ISSUE_SUMMARY = "<summary>Original Issue</summary>"
# Matches an Original-Issue <details> block (and trailing whitespace) so it can
# be replaced rather than nested. Non-greedy body, anchored to the closing tag.
_ORIGINAL_ISSUE_BLOCK_RE = re.compile(
    r"<details>\s*<summary>Original Issue</summary>.*?</details>[ \t]*\n?",
    re.DOTALL | re.IGNORECASE,
)
# Captures the verbatim text fenced inside an Original-Issue block, so an
# already-embedded original can be recovered (and re-embedded once) instead of
# being wrapped again.
_ORIGINAL_ISSUE_INNER_RE = re.compile(
    r"<details>\s*<summary>Original Issue</summary>\s*"
    r"(?P<fence>`{3,})text\n(?P<inner>.*?)\n(?P=fence)\s*</details>",
    re.DOTALL | re.IGNORECASE,
)


def _strip_original_issue_blocks(text: str) -> str:
    """Remove any embedded Original-Issue <details> block(s) from ``text``."""
    return _ORIGINAL_ISSUE_BLOCK_RE.sub("", text).rstrip()


def _innermost_original_issue(text: str) -> str | None:
    """Return the deepest verbatim Original-Issue payload embedded in ``text``.

    Nested blocks (from prior runaway cycles) are unwrapped layer by layer so the
    true original is recovered, not a copy-of-a-copy.
    """
    inner: str | None = None
    current = text
    while True:
        match = _ORIGINAL_ISSUE_INNER_RE.search(current)
        if not match:
            break
        inner = match.group("inner")
        current = inner
    return inner


def _append_raw_issue_section(formatted: str, issue_body: str) -> str:
    """Embed the verbatim original issue once, idempotently.

    Earlier behavior only checked whether the *input* already contained an
    Original-Issue block, which let the block nest across auto-pilot cycles
    (each pass re-wrapped the whole prior body — the 5-level nesting seen in
    incident #1135). This version is idempotent: it recovers the innermost
    verbatim original (from either the raw source or an already-embedded block),
    strips every Original-Issue block from the formatted output, then appends
    exactly one fresh block. Re-running on already-embedded output reproduces the
    same single block.
    """
    # Recover the verbatim original, preferring the most authoritative source:
    #   1. the innermost embedded original in the raw source (the canonical input),
    #   2. the raw source minus any Original-Issue wrapper,
    #   3. the innermost embedded original in the formatted output (covers the
    #      edge where the output already carries a block but the raw arg does not
    #      — the exact pre-fix nesting vector).
    # This preserves the true original instead of re-embedding reformatted text.
    raw = _innermost_original_issue(issue_body)
    if raw is None:
        raw = _strip_original_issue_blocks(issue_body.strip())
    raw = raw.strip()
    if not raw:
        recovered = _innermost_original_issue(formatted)
        raw = recovered.strip() if recovered else ""
    formatted_wo_block = _strip_original_issue_blocks(formatted)
    if not raw:
        # Nothing to embed. If the formatted body already had a block it has been
        # stripped above; return the cleaned form so no stale nested copy remains.
        return formatted_wo_block if ORIGINAL_ISSUE_SUMMARY in formatted else formatted
    fence = _select_code_fence(raw)
    details = (
        "\n\n<details>\n"
        "<summary>Original Issue</summary>\n\n"
        f"{fence}text\n{raw}\n{fence}\n"
        "</details>"
    )
    return f"{formatted_wo_block.rstrip()}{details}\n"


def _extract_tasks_from_formatted(body: str) -> list[str]:
    lines = body.splitlines()
    header = "## Tasks"
    try:
        header_idx = next(i for i, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        return []
    end_idx = next(
        (
            i
            for i in range(header_idx + 1, len(lines))
            if lines[i].startswith("## ") and lines[i].strip() != header
        ),
        len(lines),
    )
    tasks: list[str] = []
    for line in lines[header_idx + 1 : end_idx]:
        if not line.strip():
            continue
        match = LIST_ITEM_REGEX.match(line)
        if not match:
            continue
        indent, _, remainder = match.groups()
        if indent.strip():
            continue
        text = remainder.strip()
        checkbox = CHECKBOX_REGEX.match(text)
        if checkbox:
            text = checkbox.group(2).strip()
        if not text or text == "_Not provided._":
            continue
        tasks.append(text)
    return tasks


def _validate_and_refine_tasks(formatted: str, *, use_llm: bool) -> tuple[str, str | None]:
    """
    Validate tasks using two-pass heuristic + LLM refinement.

    Returns:
        Tuple of (updated_formatted_body, audit_summary)
    """
    tasks = _extract_tasks_from_formatted(formatted)
    if not tasks:
        return formatted, None

    try:
        from scripts.langchain import task_validator
    except ImportError:
        try:
            import task_validator
        except ImportError:
            return formatted, None

    # Run validation
    result = task_validator.validate_tasks(tasks, context=formatted, use_llm=use_llm)

    # If no changes, return original
    if set(result.tasks) == set(tasks) and len(result.tasks) == len(tasks):
        return formatted, result.audit_summary

    # Replace tasks section with validated tasks
    lines = formatted.splitlines()
    header = "## Tasks"
    try:
        header_idx = next(i for i, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        return formatted, result.audit_summary

    # Find end of Tasks section
    end_idx = next(
        (
            i
            for i in range(header_idx + 1, len(lines))
            if lines[i].startswith("## ") and lines[i].strip() != header
        ),
        len(lines),
    )

    # Build new tasks section
    new_task_lines = [f"- [ ] {task}" for task in result.tasks]
    if not new_task_lines:
        new_task_lines = ["- [ ] _Not provided._"]

    # Reconstruct formatted body
    new_lines = lines[: header_idx + 1]
    new_lines.append("")  # blank line after header
    new_lines.extend(new_task_lines)
    new_lines.append("")  # blank line before next section
    new_lines.extend(lines[end_idx:])

    return "\n".join(new_lines).strip(), result.audit_summary


def _is_github_models_auth_error(exc: Exception) -> bool:
    """Check if exception is a GitHub Models authentication error (401)."""
    exc_str = str(exc).lower()
    return "401" in exc_str and "models" in exc_str


def _reuse_already_formatted(issue_body: str, workflow: str) -> dict[str, Any] | None:
    """Return a short-circuit result if ``issue_body`` is already formatted.

    Two idempotency signals, in order of trust:

    1. A reuse marker whose embedded hash matches the visible body — the body is
       byte-identical to a prior formatter output for this workflow chain.
    2. The body is structurally conformant (all template sections + an embedded
       Original-Issue block).

    In either case the body is returned unchanged (modulo a refreshed marker) so
    no LLM rewrite occurs. Returns ``None`` when the body still needs formatting.
    """
    reused = reuse_formatted_body({"body": issue_body}, workflow)
    if reused is not None:
        return {
            "formatted_body": _with_reuse_marker(reused),
            "provider_used": None,
            "used_llm": False,
            "skipped": "reused_marker",
            "validation_audit": None,
        }
    if already_conformant(issue_body):
        return {
            "formatted_body": _with_reuse_marker(issue_body),
            "provider_used": None,
            "used_llm": False,
            "skipped": "already_conformant",
            "validation_audit": None,
        }
    return None


def format_issue_body(issue_body: str, *, use_llm: bool = True) -> dict[str, Any]:
    if not issue_body:
        issue_body = ""

    guard_result = check_prompt_injection(issue_body)
    if guard_result["blocked"]:
        return {
            "formatted_body": issue_body,
            "provider_used": None,
            "used_llm": False,
            "guard_blocked": True,
            "guard_reason": guard_result["reason"],
        }

    # Idempotency / anti-amplification: before re-deriving anything, check whether
    # this body has already been formatted. Re-formatting an already-conformant
    # body only paraphrases prior output and is the primary runaway-expansion
    # vector (incidents #1135/#1143). Done on the *uncapped* body so detection
    # still works on large already-formatted issues.
    workflow = _context_workflow("issue_formatter")
    reuse = _reuse_already_formatted(issue_body, workflow)
    if reuse is not None:
        return reuse

    issue_body = _capped_issue_body(issue_body, workflow)

    # Check size before processing to avoid rate limit errors
    if len(issue_body) > MAX_ISSUE_BODY_SIZE:
        err_msg = (
            f"Issue body too large ({len(issue_body):,} chars). "
            f"Max is {MAX_ISSUE_BODY_SIZE:,}. "
            "Recursive task decomposition spam suspected; needs manual cleanup."
        )
        return {
            "error": err_msg,
            "formatted_body": None,
            "provider_used": None,
            "used_llm": False,
        }

    if use_llm:
        client_info = _get_llm_client()
        if client_info:
            client, provider = client_info
            try:
                from langchain_core.prompts import ChatPromptTemplate

                prompt = _load_prompt()
                template = ChatPromptTemplate.from_template(prompt)
                chain = template | client
                trace = TraceInfo()
                try:
                    response, trace = invoke_with_trace(
                        chain,
                        {"issue_body": issue_body},
                        operation="issue_formatter",
                    )
                except Exception as e:
                    # If GitHub Models fails with 401, retry with OpenAI
                    if provider == "github-models" and _is_github_models_auth_error(e):
                        fallback_info = _get_llm_client(force_openai=True)
                        if fallback_info:
                            client, provider = fallback_info
                            chain = template | client
                            response, trace = invoke_with_trace(
                                chain,
                                {"issue_body": issue_body},
                                operation="issue_formatter",
                            )
                        else:
                            raise
                    else:
                        raise
                content = getattr(response, "content", None) or str(response)
                formatted = content.strip()
                if _formatted_output_valid(formatted):
                    # NOTE: Task decomposition is now handled by agents:optimize step
                    # which uses LLM for intelligent splitting. Don't do heuristic
                    # splitting here - it causes task explosion (issue #805, #1143).
                    formatted, audit = _validate_and_refine_tasks(formatted, use_llm=use_llm)
                    formatted = _append_raw_issue_section(formatted, issue_body)
                    formatted = _with_reuse_marker(formatted)
                    result = {
                        "formatted_body": formatted,
                        "provider_used": provider,
                        "used_llm": True,
                        "validation_audit": audit,
                    }
                    result.update(trace.as_dict())
                    return result
            except ImportError:
                # Fall through to fallback if imports fail
                pass

    formatted = _format_issue_fallback(issue_body)
    # NOTE: Task decomposition is now handled by agents:optimize step
    # which uses LLM for intelligent splitting. Don't do heuristic
    # splitting here - it causes task explosion (issue #805, #1143).
    formatted, audit = _validate_and_refine_tasks(formatted, use_llm=use_llm)
    formatted = _append_raw_issue_section(formatted, issue_body)
    formatted = _with_reuse_marker(formatted)
    return {
        "formatted_body": formatted,
        "provider_used": None,
        "used_llm": False,
        "validation_audit": audit,
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
        if result.get("guard_blocked"):
            payload["guard_blocked"] = True
            payload["guard_reason"] = result.get("guard_reason") or ""
        if result.get("langsmith_trace_id"):
            payload["langsmith_trace_id"] = result["langsmith_trace_id"]
        if result.get("langsmith_trace_url"):
            payload["langsmith_trace_url"] = result["langsmith_trace_url"]
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print(result["formatted_body"])


if __name__ == "__main__":
    main()
