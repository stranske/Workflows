#!/usr/bin/env python3
"""
Analyze issue bodies for optimization suggestions.

Run with:
    python scripts/langchain/issue_optimizer.py --input-file issue.md --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AGENT_LIMITATIONS = [
    "Cannot modify .github/workflows/*.yml (protected)",
    "Cannot change repository settings",
    "Cannot guarantee specific coverage percentages",
    "Cannot make subjective design decisions",
    "Cannot retry CI pipelines",
]

ANALYZE_ISSUE_PROMPT = """
Analyze this issue for agent compatibility and formatting quality.

Issue body:
{issue_body}

Identify:
1. Tasks that are too broad (should be split)
2. Tasks the agent cannot complete (use AGENT_LIMITATIONS)
3. Subjective acceptance criteria (suggest objective alternatives)
4. Missing sections (why, scope, non-goals, implementation notes)
5. Formatting issues (bullets used for non-tasks, etc.)

AGENT_LIMITATIONS:
{agent_limitations}

Output JSON with this shape:
{{
  "task_splitting": [{{"task": "...", "reason": "...", "split_suggestions": ["..."]}}],
  "blocked_tasks": [{{"task": "...", "reason": "...", "suggested_action": "..."}}],
  "objective_criteria": [{{"criterion": "...", "issue": "...", "suggestion": "..."}}],
  "missing_sections": ["Scope", "Implementation Notes"],
  "formatting_issues": ["..."],
  "overall_notes": "..."
}}
""".strip()

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "analyze_issue.md"
APPLY_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "apply_suggestions.md"

APPLY_SUGGESTIONS_PROMPT = """
Reformat this issue applying the approved suggestions.

Original issue:
{original_body}

Approved suggestions:
{suggestions_json}

Apply ALL suggestions and output the complete reformatted issue
following AGENT_ISSUE_TEMPLATE structure. Move blocked tasks to
a "## Deferred Tasks (Requires Human)" section.
""".strip()

SECTION_ALIASES = {
    "why": ["why", "motivation", "summary"],
    "scope": ["scope", "context", "background"],
    "non_goals": ["non-goals", "nongoals", "out of scope"],
    "tasks": ["tasks", "task list", "todo", "to do"],
    "acceptance": ["acceptance criteria", "acceptance", "definition of done"],
    "implementation": ["implementation notes", "implementation note", "notes"],
}

SECTION_TITLES = {
    "why": "Why",
    "scope": "Scope",
    "non_goals": "Non-Goals",
    "tasks": "Tasks",
    "acceptance": "Acceptance Criteria",
    "implementation": "Implementation Notes",
}

LIST_ITEM_REGEX = re.compile(r"^\s*[-*+]\s+(.*)$")
CHECKBOX_REGEX = re.compile(r"^\[[ xX]\]\s*(.*)$")

SUBJECTIVE_CRITERIA = ("clean", "nice", "good", "fast", "better", "intuitive", "polished")
SUGGESTIONS_MARKER_PREFIX = "Updated WORKFLOW_OUTPUTS.md suggestions-json:"


@dataclass
class IssueOptimizationResult:
    task_splitting: list[dict[str, Any]]
    blocked_tasks: list[dict[str, str]]
    objective_criteria: list[dict[str, str]]
    missing_sections: list[str]
    formatting_issues: list[str]
    overall_notes: str | None
    provider_used: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_splitting": self.task_splitting,
            "blocked_tasks": self.blocked_tasks,
            "objective_criteria": self.objective_criteria,
            "missing_sections": self.missing_sections,
            "formatting_issues": self.formatting_issues,
            "overall_notes": self.overall_notes or "",
            "provider_used": self.provider_used,
        }


def _format_list_section(title: str, items: list[str]) -> list[str]:
    lines = [f"### {title}"]
    if not items:
        lines.append("- None")
        return lines
    lines.extend(f"- {item}" for item in items)
    return lines


def _format_task_splitting(task_splitting: list[dict[str, Any]]) -> list[str]:
    entries: list[str] = []
    for item in task_splitting:
        if not isinstance(item, dict):
            continue
        task = str(item.get("task") or "").strip()
        reason = str(item.get("reason") or "").strip()
        suggestions = item.get("split_suggestions") if isinstance(item, dict) else None
        suggestion_text = ""
        if isinstance(suggestions, list) and suggestions:
            suggestion_text = f" Suggested split: {', '.join(str(s) for s in suggestions)}."
        if task:
            detail = f"{task} ({reason})" if reason else task
            entries.append(f"{detail}.{suggestion_text}".strip())
    return entries


def _format_blocked_tasks(blocked_tasks: list[dict[str, str]]) -> list[str]:
    entries: list[str] = []
    for item in blocked_tasks:
        if not isinstance(item, dict):
            continue
        task = str(item.get("task") or "").strip()
        reason = str(item.get("reason") or "").strip()
        action = str(item.get("suggested_action") or "").strip()
        detail_parts = [part for part in (reason, action) if part]
        detail = f" ({' | '.join(detail_parts)})" if detail_parts else ""
        if task:
            entries.append(f"{task}{detail}")
    return entries


def _format_objective_criteria(objective_criteria: list[dict[str, str]]) -> list[str]:
    entries: list[str] = []
    for item in objective_criteria:
        if not isinstance(item, dict):
            continue
        criterion = str(item.get("criterion") or "").strip()
        issue = str(item.get("issue") or "").strip()
        suggestion = str(item.get("suggestion") or "").strip()
        if not criterion:
            continue
        detail_parts = [part for part in (issue, suggestion) if part]
        detail = f" ({' | '.join(detail_parts)})" if detail_parts else ""
        entries.append(f"{criterion}{detail}")
    return entries


def format_suggestions_comment(result: IssueOptimizationResult) -> str:
    data = result.to_dict()
    data.pop("provider_used", None)
    suggestions_json = json.dumps(data, ensure_ascii=True)

    sections: list[str] = [
        "## Issue Optimization Suggestions",
        "",
        "Review the suggestions below. If you want the agent to apply them, add the",
        "`agents:apply-suggestions` label to this issue.",
        "",
    ]
    sections.extend(
        _format_list_section(
            "Task splitting",
            _format_task_splitting(result.task_splitting),
        )
    )
    sections.append("")
    sections.extend(
        _format_list_section(
            "Blocked tasks",
            _format_blocked_tasks(result.blocked_tasks),
        )
    )
    sections.append("")
    sections.extend(
        _format_list_section(
            "Objective acceptance criteria",
            _format_objective_criteria(result.objective_criteria),
        )
    )
    sections.append("")
    sections.extend(_format_list_section("Missing sections", result.missing_sections))
    sections.append("")
    sections.extend(_format_list_section("Formatting issues", result.formatting_issues))
    if result.overall_notes:
        sections.extend(["", "### Notes", f"- {result.overall_notes.strip()}"])

    sections.append("")
    sections.append(f"<!-- {SUGGESTIONS_MARKER_PREFIX} {suggestions_json} -->")
    return "\n".join(sections).strip()


def _load_prompt() -> str:
    if PROMPT_PATH.is_file():
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    return ANALYZE_ISSUE_PROMPT


def _load_apply_prompt() -> str:
    if APPLY_PROMPT_PATH.is_file():
        return APPLY_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return APPLY_SUGGESTIONS_PROMPT


def _get_llm_client(force_openai: bool = False) -> tuple[object, str] | None:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")
    if not github_token and not openai_token:
        return None

    from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL

    # If force_openai is True, skip GitHub Models and use OpenAI directly
    if force_openai and openai_token:
        return (
            ChatOpenAI(
                model=DEFAULT_MODEL,
                api_key=openai_token,
                temperature=0.1,
            ),
            "openai",
        )

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


def _parse_sections(body: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {key: [] for key in SECTION_TITLES}
    current: str | None = None
    for line in body.splitlines():
        heading_match = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if heading_match:
            section_key = _resolve_section(heading_match.group(1))
            if section_key:
                current = section_key
                continue
        if current:
            sections[current].append(line)
    return sections


def _strip_checkbox(line: str) -> str:
    stripped = line.strip()
    match = LIST_ITEM_REGEX.match(stripped)
    if not match:
        return stripped
    content = match.group(1).strip()
    checkbox = CHECKBOX_REGEX.match(content)
    if checkbox:
        return checkbox.group(1).strip()
    return content


def _parse_checklist(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        if LIST_ITEM_REGEX.match(line.strip()):
            value = _strip_checkbox(line)
            if value:
                items.append(value)
    return items


def _detect_blocked_tasks(tasks: list[str]) -> list[dict[str, str]]:
    blocked: list[dict[str, str]] = []
    for task in tasks:
        lowered = task.lower()
        if ".github/workflows" in lowered or "workflow" in lowered:
            blocked.append(
                {
                    "task": task,
                    "reason": "Requires workflow changes, which are protected",
                    "suggested_action": "Request a human to apply workflow updates",
                }
            )
        if "coverage" in lowered and "%" in lowered:
            blocked.append(
                {
                    "task": task,
                    "reason": "Coverage targets are not guaranteed",
                    "suggested_action": "Convert to adding tests and report achieved coverage",
                }
            )
    return blocked


def _detect_objective_criteria(criteria: list[str]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for criterion in criteria:
        lowered = criterion.lower()
        if any(word in lowered for word in SUBJECTIVE_CRITERIA):
            results.append(
                {
                    "criterion": criterion,
                    "issue": "Subjective wording",
                    "suggestion": "Replace with a measurable check (tests, lint, command output)",
                }
            )
    return results


def _detect_formatting_issues(section_lines: list[str]) -> list[str]:
    issues: list[str] = []
    for line in section_lines:
        stripped = line.strip()
        if stripped and not LIST_ITEM_REGEX.match(stripped):
            issues.append("Non-bulleted content found in checklist section")
            break
    return issues


def _fallback_analysis(issue_body: str) -> IssueOptimizationResult:
    sections = _parse_sections(issue_body)

    tasks = _parse_checklist(sections["tasks"])
    acceptance = _parse_checklist(sections["acceptance"])

    missing_sections = [
        title
        for key, title in SECTION_TITLES.items()
        if key != "tasks" and key != "acceptance" and not sections[key]
    ]
    if not tasks:
        missing_sections.append("Tasks")
    if not acceptance:
        missing_sections.append("Acceptance Criteria")

    formatting_issues = []
    formatting_issues.extend(_detect_formatting_issues(sections["tasks"]))
    formatting_issues.extend(_detect_formatting_issues(sections["acceptance"]))

    return IssueOptimizationResult(
        task_splitting=_detect_task_splitting(tasks, use_llm=False),
        blocked_tasks=_detect_blocked_tasks(tasks),
        objective_criteria=_detect_objective_criteria(acceptance),
        missing_sections=missing_sections,
        formatting_issues=formatting_issues,
        overall_notes="Fallback analysis used (LLM unavailable).",
        provider_used=None,
    )


def _extract_json_payload(text: str) -> str | None:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return stripped[start : end + 1]


def _extract_suggestions_json(comment_body: str) -> dict[str, Any] | None:
    if not comment_body:
        return None
    marker = "suggestions-json:"
    start = comment_body.find(marker)
    if start == -1:
        return None
    payload = _extract_json_payload(comment_body[start + len(marker) :])
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _formatted_output_valid(text: str) -> bool:
    if not text:
        return False
    required = ["## Tasks", "## Acceptance Criteria"]
    return all(section in text for section in required)


def _strip_task_marker(text: str) -> str:
    cleaned = re.sub(r"^\s*[-*+]\s*", "", text)
    cleaned = re.sub(r"^\s*\[[ xX]\]\s*", "", cleaned)
    return cleaned.strip()


def _normalize_task_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned.lower()


def _coerce_split_suggestions(entry: dict[str, Any]) -> list[str]:
    suggestions = entry.get("split_suggestions")
    if not isinstance(suggestions, list):
        return []
    items: list[str] = []
    for suggestion in suggestions:
        value = str(suggestion).strip()
        if value:
            items.append(value)
    return items


def _is_large_task(task: str) -> bool:
    lowered = task.lower()
    if len(task.split()) >= 14:
        return True
    if any(sep in lowered for sep in (" and ", " + ", " & ", " then ", "; ")):
        return True
    return bool(re.search(r"\s\+\s", lowered) or ", " in task or " / " in task)


def _detect_task_splitting(tasks: list[str], *, use_llm: bool = False) -> list[dict[str, Any]]:
    try:
        from scripts.langchain import task_decomposer
    except ModuleNotFoundError:
        import task_decomposer

    results: list[dict[str, Any]] = []
    for task in tasks:
        if not _is_large_task(task):
            continue
        decomposition = task_decomposer.decompose_task(task, use_llm=use_llm)
        split_suggestions = decomposition.get("sub_tasks") or []
        if not split_suggestions:
            split_suggestions = ["Split into smaller, single-action tasks"]
        results.append(
            {
                "task": task,
                "reason": "Task combines multiple actions",
                "split_suggestions": split_suggestions,
            }
        )
    return results


def _ensure_task_decomposition(
    task_splitting: list[dict[str, Any]], *, use_llm: bool
) -> list[dict[str, Any]]:
    if not task_splitting:
        return task_splitting

    try:
        from scripts.langchain import task_decomposer
    except ModuleNotFoundError:
        import task_decomposer

    updated: list[dict[str, Any]] = []
    for entry in task_splitting:
        if not isinstance(entry, dict):
            continue
        task = str(entry.get("task") or "").strip()
        if not task:
            continue
        suggestions = _coerce_split_suggestions(entry)
        if not suggestions:
            decomposition = task_decomposer.decompose_task(task, use_llm=use_llm)
            suggestions = decomposition.get("sub_tasks") or []
        normalized = task_decomposer.normalize_subtasks(suggestions)
        updated_entry = dict(entry)
        if normalized:
            updated_entry["split_suggestions"] = normalized
        updated.append(updated_entry)
    return updated


def _normalize_result(
    payload: dict[str, Any], provider_used: str | None
) -> IssueOptimizationResult:
    task_splitting = payload.get("task_splitting") if isinstance(payload, dict) else []
    blocked_tasks = payload.get("blocked_tasks") if isinstance(payload, dict) else []
    objective_criteria = payload.get("objective_criteria") if isinstance(payload, dict) else []
    missing_sections = payload.get("missing_sections") if isinstance(payload, dict) else []
    formatting_issues = payload.get("formatting_issues") if isinstance(payload, dict) else []
    overall_notes = payload.get("overall_notes")

    def _coerce_list(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    return IssueOptimizationResult(
        task_splitting=_coerce_list(task_splitting),
        blocked_tasks=_coerce_list(blocked_tasks),
        objective_criteria=_coerce_list(objective_criteria),
        missing_sections=[
            str(item) for item in _coerce_list(missing_sections) if str(item).strip()
        ],
        formatting_issues=[
            str(item) for item in _coerce_list(formatting_issues) if str(item).strip()
        ],
        overall_notes=str(overall_notes).strip() if overall_notes else "",
        provider_used=provider_used,
    )


def _process_llm_response(
    response: Any, provider: str, use_llm: bool
) -> IssueOptimizationResult | None:
    """Process LLM response and return normalized result, or None if processing fails."""
    content = getattr(response, "content", None) or str(response)
    payload = _extract_json_payload(content)
    if payload:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            result = _normalize_result(data, provider)
            result.task_splitting = _ensure_task_decomposition(
                result.task_splitting, use_llm=use_llm
            )
            return result
    return None


def analyze_issue(issue_body: str, *, use_llm: bool = True) -> IssueOptimizationResult:
    if not issue_body:
        issue_body = ""

    if use_llm:
        from tools.llm_provider import _is_token_limit_error

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
                            "agent_limitations": "\n".join(
                                f"- {item}" for item in AGENT_LIMITATIONS
                            ),
                        }
                    )
                    result = _process_llm_response(response, provider, use_llm)
                    if result:
                        return result
                except Exception as e:
                    # If GitHub Models hit token limit, retry with OpenAI API
                    if _is_token_limit_error(e) and provider == "github-models":
                        print(
                            "GitHub Models token limit hit, retrying with OpenAI API...",
                            file=sys.stderr,
                        )
                        openai_client_info = _get_llm_client(force_openai=True)
                        if openai_client_info:
                            openai_client, openai_provider = openai_client_info
                            openai_chain = template | openai_client
                            try:
                                response = openai_chain.invoke(
                                    {
                                        "issue_body": issue_body,
                                        "agent_limitations": "\n".join(
                                            f"- {item}" for item in AGENT_LIMITATIONS
                                        ),
                                    }
                                )
                                result = _process_llm_response(
                                    response, openai_provider, use_llm=use_llm
                                )
                                if result is not None:
                                    print(
                                        "Successfully analyzed with OpenAI API",
                                        file=sys.stderr,
                                    )
                                    return result
                            except Exception as openai_error:
                                err_type = type(openai_error).__name__
                                print(
                                    f"OpenAI API also failed "
                                    f"({err_type}: {openai_error}), using fallback",
                                    file=sys.stderr,
                                )
                        else:
                            print(
                                "OPENAI_API_KEY not available, using fallback",
                                file=sys.stderr,
                            )
                    else:
                        # Other error types - fall back immediately
                        print(
                            f"LLM analysis failed ({type(e).__name__}: {e}), using fallback",
                            file=sys.stderr,
                        )

    result = _fallback_analysis(issue_body)
    result.task_splitting = _ensure_task_decomposition(result.task_splitting, use_llm=False)
    return result


def _blocked_task_lines(suggestions: dict[str, Any]) -> list[str]:
    blocked = suggestions.get("blocked_tasks")
    if not isinstance(blocked, list):
        return []
    lines: list[str] = []
    for entry in blocked:
        if not isinstance(entry, dict):
            continue
        task = str(entry.get("task") or "").strip()
        reason = str(entry.get("reason") or "").strip()
        action = str(entry.get("suggested_action") or "").strip()
        if not task:
            continue
        suffix_parts = [part for part in (reason, action) if part]
        suffix = f" ({' | '.join(suffix_parts)})" if suffix_parts else ""
        lines.append(f"- [ ] {task}{suffix}")
    return lines


def _append_deferred_tasks(formatted_body: str, suggestions: dict[str, Any]) -> str:
    blocked_lines = _blocked_task_lines(suggestions)
    if not blocked_lines:
        return formatted_body
    header = "## Deferred Tasks (Requires Human)"
    if header in formatted_body:
        return formatted_body
    parts = [
        formatted_body.rstrip(),
        "",
        header,
        "",
        "\n".join(blocked_lines),
    ]
    return "\n".join(parts).strip()


def _apply_task_decomposition(formatted_body: str, suggestions: dict[str, Any]) -> str:
    raw_entries = suggestions.get("task_splitting")
    if not isinstance(raw_entries, list) or not raw_entries:
        return formatted_body

    try:
        from scripts.langchain import task_decomposer
    except ModuleNotFoundError:
        import task_decomposer

    decomposition_map: dict[str, list[str]] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        task = str(entry.get("task") or "").strip()
        if not task:
            continue
        sub_tasks = _coerce_split_suggestions(entry)
        if not sub_tasks:
            continue
        normalized = task_decomposer.normalize_subtasks(sub_tasks)
        if not normalized:
            continue
        decomposition_map[_normalize_task_text(task)] = normalized

    if not decomposition_map:
        return formatted_body

    lines = formatted_body.splitlines()
    header = "## Tasks"
    try:
        header_idx = next(i for i, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        return formatted_body

    end_idx = next(
        (
            i
            for i in range(header_idx + 1, len(lines))
            if lines[i].startswith("## ") and lines[i].strip() != header
        ),
        len(lines),
    )

    updated: list[str] = []
    updated.extend(lines[: header_idx + 1])
    task_lines = lines[header_idx + 1 : end_idx]
    for line in task_lines:
        updated.append(line)
        if not line.strip() or not LIST_ITEM_REGEX.match(line.strip()):
            continue
        task_text = _strip_task_marker(line)
        sub_tasks = decomposition_map.get(_normalize_task_text(task_text))
        if not sub_tasks:
            continue
        indent = re.match(r"^\s*", line).group(0)
        sub_indent = f"{indent}  "
        for sub_task in sub_tasks:
            cleaned = _strip_task_marker(sub_task)
            if cleaned:
                updated.append(f"{sub_indent}- [ ] {cleaned}")

    updated.extend(lines[end_idx:])
    return "\n".join(updated).strip()


def apply_suggestions(
    issue_body: str, suggestions: dict[str, Any], *, use_llm: bool = True
) -> dict[str, Any]:
    if not issue_body:
        issue_body = ""

    if use_llm:
        from tools.llm_provider import _is_token_limit_error

        client_info = _get_llm_client()
        if client_info:
            client, provider = client_info
            try:
                from langchain_core.prompts import ChatPromptTemplate
            except ImportError:
                client_info = None
            else:
                prompt = _load_apply_prompt()
                template = ChatPromptTemplate.from_template(prompt)
                chain = template | client
                try:
                    response = chain.invoke(
                        {
                            "original_body": issue_body,
                            "suggestions_json": json.dumps(
                                suggestions, ensure_ascii=True, indent=2
                            ),
                        }
                    )
                    content = getattr(response, "content", None) or str(response)
                    formatted = content.strip()
                    if _formatted_output_valid(formatted):
                        return {
                            "formatted_body": formatted,
                            "provider_used": provider,
                            "used_llm": True,
                        }
                except Exception as e:
                    # If GitHub Models hit token limit, retry with OpenAI API
                    if _is_token_limit_error(e) and provider == "github-models":
                        print(
                            "GitHub Models token limit hit in apply_suggestions, "
                            "retrying with OpenAI API...",
                            file=sys.stderr,
                        )
                        openai_client_info = _get_llm_client(force_openai=True)
                        if openai_client_info:
                            openai_client, openai_provider = openai_client_info
                            openai_chain = template | openai_client
                            try:
                                response = openai_chain.invoke(
                                    {
                                        "original_body": issue_body,
                                        "suggestions_json": json.dumps(
                                            suggestions, ensure_ascii=True, indent=2
                                        ),
                                    }
                                )
                                content = getattr(response, "content", None) or str(response)
                                formatted = content.strip()
                                if _formatted_output_valid(formatted):
                                    print(
                                        "Successfully applied suggestions with OpenAI API",
                                        file=sys.stderr,
                                    )
                                    return {
                                        "formatted_body": formatted,
                                        "provider_used": openai_provider,
                                        "used_llm": True,
                                    }
                            except Exception as openai_error:
                                err_type = type(openai_error).__name__
                                print(
                                    f"OpenAI API also failed "
                                    f"({err_type}: {openai_error}), using fallback",
                                    file=sys.stderr,
                                )
                        else:
                            print(
                                "OPENAI_API_KEY not available, using fallback",
                                file=sys.stderr,
                            )
                    else:
                        # Other error types - fall back immediately
                        print(
                            f"LLM apply failed ({type(e).__name__}: {e}), using fallback",
                            file=sys.stderr,
                        )

    try:
        from scripts.langchain import issue_formatter
    except ModuleNotFoundError:
        import issue_formatter

    fallback = issue_formatter.format_issue_body(issue_body, use_llm=False)
    formatted = _apply_task_decomposition(fallback["formatted_body"], suggestions)
    formatted = _append_deferred_tasks(formatted, suggestions)
    return {
        "formatted_body": formatted,
        "provider_used": None,
        "used_llm": False,
    }


def _load_input(args: argparse.Namespace) -> str:
    if args.input_file:
        return Path(args.input_file).read_text(encoding="utf-8")
    if args.input_text:
        return args.input_text
    return sys.stdin.read()


def _load_suggestions(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.suggestions_json:
        try:
            data = json.loads(args.suggestions_json)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    if args.suggestions_file:
        try:
            raw = Path(args.suggestions_file).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    if args.suggestions_comment_file:
        try:
            raw = Path(args.suggestions_comment_file).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return _extract_suggestions_json(raw)
    if args.suggestions_comment_text:
        return _extract_suggestions_json(args.suggestions_comment_text)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze issue text for optimization suggestions.")
    parser.add_argument("--input-file", help="Path to raw issue text.")
    parser.add_argument("--input-text", help="Raw issue text (inline).")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload to stdout.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM usage.")
    parser.add_argument(
        "--apply-suggestions",
        action="store_true",
        help="Apply suggestions JSON to the issue body and format the result.",
    )
    parser.add_argument("--suggestions-json", help="Suggestions JSON string.")
    parser.add_argument("--suggestions-file", help="Path to suggestions JSON file.")
    parser.add_argument(
        "--suggestions-comment-file",
        help="Path to comment text containing a suggestions-json marker.",
    )
    parser.add_argument(
        "--suggestions-comment-text",
        help="Comment text containing a suggestions-json marker.",
    )
    args = parser.parse_args()

    raw = _load_input(args)
    if args.apply_suggestions:
        suggestions = _load_suggestions(args)
        if suggestions is None:
            print("Failed to load suggestions JSON.", file=sys.stderr)
            sys.exit(1)
        result = apply_suggestions(raw, suggestions, use_llm=not args.no_llm)
        if args.json:
            payload = {
                "formatted_body": result["formatted_body"],
                "provider_used": result.get("provider_used"),
                "used_llm": result.get("used_llm", False),
            }
            print(json.dumps(payload, ensure_ascii=True))
        else:
            print(result["formatted_body"])
    else:
        result = analyze_issue(raw, use_llm=not args.no_llm)
        if args.json:
            print(json.dumps(result.to_dict(), ensure_ascii=True, indent=2))
        else:
            print(json.dumps(result.to_dict(), ensure_ascii=True))


if __name__ == "__main__":
    main()
