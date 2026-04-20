#!/usr/bin/env python3
"""
Analyze issue bodies for optimization suggestions.

Run with:
    python scripts/langchain/issue_optimizer.py --input-file issue.md --json
"""

# ruff: noqa: I001

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from scripts.langchain.structured_output import (
    DEFAULT_REPAIR_PROMPT,
    build_repair_callback,
    parse_structured_output,
)

try:
    from scripts.langchain.injection_guard import check_prompt_injection
except ModuleNotFoundError:
    from injection_guard import check_prompt_injection

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

CRITICAL rules for split_suggestions:
- Each item MUST be a complete, independently understandable sentence
- Each item MUST start with an action verb (Create, Add, Update, Fix, Implement, Define, Test)
- Do NOT split a sentence at commas into fragments
- Do NOT return single words or noun phrases as sub-tasks
- BAD: ["methods", "input/output types", "metadata contract"]
- GOOD: [
    "Define the EmbeddingProvider interface methods",
    "Define input/output types",
    "Define metadata contract"
  ]

Output JSON with this shape:
{{
  "task_splitting": [{{
    "task": "...",
    "reason": "...",
    "split_suggestions": ["Complete actionable sub-task description"]
  }}],
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

ISSUE_OPTIMIZER_REPAIR_PROMPT = DEFAULT_REPAIR_PROMPT

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

LIST_ITEM_REGEX = re.compile(r"^\s*([-*+]|\d+[.)]|[A-Za-z][.)])\s+(.*)$")
CHECKBOX_REGEX = re.compile(r"^\[[ xX]\]\s*(.*)$")

SUBJECTIVE_CRITERIA = ("clean", "nice", "good", "fast", "better", "intuitive", "polished")
SUGGESTIONS_MARKER_PREFIX = "suggestions-json:"


@dataclass
class IssueOptimizationResult:
    task_splitting: list[dict[str, Any]]
    blocked_tasks: list[dict[str, str]]
    objective_criteria: list[dict[str, str]]
    missing_sections: list[str]
    formatting_issues: list[str]
    overall_notes: str | None
    provider_used: str | None = None
    guard_blocked: bool = False
    guard_reason: str = ""
    langsmith_trace_id: str | None = None
    langsmith_trace_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task_splitting": self.task_splitting,
            "blocked_tasks": self.blocked_tasks,
            "objective_criteria": self.objective_criteria,
            "missing_sections": self.missing_sections,
            "formatting_issues": self.formatting_issues,
            "overall_notes": self.overall_notes or "",
            "provider_used": self.provider_used,
        }
        if self.guard_blocked:
            payload["guard_blocked"] = True
            payload["guard_reason"] = self.guard_reason
        if self.langsmith_trace_id:
            payload["langsmith_trace_id"] = self.langsmith_trace_id
        if self.langsmith_trace_url:
            payload["langsmith_trace_url"] = self.langsmith_trace_url
        return payload


class IssueOptimizationPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task_splitting: list[dict[str, Any]] = Field(default_factory=list)
    blocked_tasks: list[dict[str, Any]] = Field(default_factory=list)
    objective_criteria: list[dict[str, Any]] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    formatting_issues: list[str] = Field(default_factory=list)
    overall_notes: str | None = None


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
        from tools.langchain_client import build_chat_client
    except ImportError:
        return None

    resolved = build_chat_client(force_openai=force_openai)
    if not resolved:
        return None
    return resolved.client, resolved.provider


def _build_llm_config(
    *,
    operation: str,
    issue_number: int | None = None,
) -> dict[str, object]:
    """Build LangSmith metadata/tags for LLM call."""
    import os

    try:
        from tools.llm_provider import build_langsmith_metadata

        return build_langsmith_metadata(
            operation=operation,
            issue_number=issue_number,
        )
    except ImportError:
        pass

    # Inline fallback when tools.llm_provider is unavailable
    repo = os.environ.get("GITHUB_REPOSITORY", "unknown")
    run_id = os.environ.get("GITHUB_RUN_ID") or os.environ.get("RUN_ID") or "unknown"
    env_issue = os.environ.get("ISSUE_NUMBER", "")
    issue_or_pr = (
        str(issue_number)
        if issue_number is not None
        else env_issue if env_issue.isdigit() else "unknown"
    )
    metadata = {
        "repo": repo,
        "run_id": run_id,
        "issue_or_pr_number": issue_or_pr,
        "operation": operation,
        "issue_number": str(issue_number) if issue_number is not None else None,
    }
    tags = [
        "workflows-agents",
        f"operation:{operation}",
        f"repo:{repo}",
        f"issue_or_pr:{issue_or_pr}",
        f"run_id:{run_id}",
    ]
    return {"metadata": metadata, "tags": tags}


def _invoke_llm_with_trace(
    chain: object,
    inputs: dict[str, Any],
    *,
    operation: str,
    issue_number: int | None = None,
) -> tuple[object, str | None, str | None]:
    """Invoke LLM chain and extract trace information.

    Returns:
        Tuple of (response, trace_id, trace_url)
    """
    config = _build_llm_config(operation=operation, issue_number=issue_number)

    try:
        response = chain.invoke(inputs, config=config)
    except TypeError:
        # Fallback if config not supported
        response = chain.invoke(inputs)

    # Extract trace ID from response if available
    trace_id = None
    trace_url = None
    try:
        from tools.llm_provider import derive_langsmith_trace_url, extract_trace_id

        trace_id = extract_trace_id(response)
        if trace_id:
            trace_url = derive_langsmith_trace_url(trace_id)
    except ImportError:
        pass

    return response, trace_id, trace_url


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
    in_code_block = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
        if in_code_block:
            if current:
                sections[current].append(line)
            continue
        heading_match = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if heading_match:
            section_key = _resolve_section(heading_match.group(1))
            if section_key:
                current = section_key
                continue
        section_key = _resolve_section(stripped)
        if section_key and stripped:
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
    content = match.group(2).strip()  # Group 2 is the content after list marker
    checkbox = CHECKBOX_REGEX.match(content)
    if checkbox:
        return checkbox.group(1).strip()
    return content


def _parse_checklist(lines: list[str]) -> list[str]:
    items: list[str] = []
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not stripped:
            continue
        if LIST_ITEM_REGEX.match(stripped):
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
    marker = SUGGESTIONS_MARKER_PREFIX
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


def _deduplicate_task_lines(formatted: str) -> str:
    """Remove duplicate task lines from the formatted output.

    Scans '## Tasks' through the next '## ' heading, deduplicates
    checkbox lines by normalized text, and returns the cleaned body.
    """
    lines = formatted.splitlines()
    try:
        header_idx = next(i for i, line in enumerate(lines) if line.strip() == "## Tasks")
    except StopIteration:
        return formatted

    end_idx = next(
        (
            i
            for i in range(header_idx + 1, len(lines))
            if lines[i].startswith("## ") and lines[i].strip() != "## Tasks"
        ),
        len(lines),
    )

    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines[header_idx + 1 : end_idx]:
        stripped = line.strip()
        if not stripped:
            deduped.append(line)
            continue
        norm = _normalize_task_text(_strip_task_marker(stripped))
        if not norm:
            deduped.append(line)
            continue
        if norm in seen:
            continue
        seen.add(norm)
        deduped.append(line)

    result = lines[: header_idx + 1] + deduped + lines[end_idx:]
    return "\n".join(result)


def _section_duplication_ratio(formatted: str) -> float:
    """Return the fraction of section headings that appear more than once.

    A ratio > 0 indicates the formatter doubled one or more sections.
    """
    headings = re.findall(r"^##\s+(.+)$", formatted, re.MULTILINE)
    if not headings:
        return 0.0
    norm_headings = [h.strip().lower() for h in headings]
    unique = set(norm_headings)
    duplicated = sum(1 for h in unique if norm_headings.count(h) > 1)
    return duplicated / len(unique)


def _strip_task_marker(text: str) -> str:
    cleaned = re.sub(r"^\s*([-*+]|\d+[.)]|[A-Za-z][.)])\s*", "", text)
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
        if not value:
            continue
        # Reject short fragments that aren't actionable tasks
        word_count = len(re.findall(r"[A-Za-z0-9']+", value))
        if word_count < 5:
            continue
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
        # Skip normalize_subtasks here; _apply_task_decomposition handles it
        # to avoid double-normalization that can amplify duplication.
        updated_entry = dict(entry)
        if suggestions:
            updated_entry["split_suggestions"] = suggestions
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
    response: Any,
    provider: str,
    use_llm: bool,
    *,
    client: object | None = None,
    trace_id: str | None = None,
    trace_url: str | None = None,
) -> tuple[IssueOptimizationResult | None, str | None]:
    """Process LLM response and return (result, error)."""
    content = getattr(response, "content", None) or str(response)
    parsed = parse_structured_output(
        content,
        IssueOptimizationPayload,
        repair=(
            build_repair_callback(client, template=ISSUE_OPTIMIZER_REPAIR_PROMPT)
            if client is not None
            else None
        ),
        max_repair_attempts=1,
    )
    if parsed.payload is None:
        if parsed.error_stage == "repair_unavailable":
            return None, "LLM output failed validation and could not be repaired."
        if parsed.error_stage == "repair_validation":
            return None, f"LLM repair failed validation: {parsed.error_detail}"
        return None, f"LLM output failed validation: {parsed.error_detail}"

    result = _normalize_result(parsed.payload.model_dump(), provider)
    result.task_splitting = _ensure_task_decomposition(result.task_splitting, use_llm=use_llm)
    result.langsmith_trace_id = trace_id
    result.langsmith_trace_url = trace_url
    return result, None


def analyze_issue(issue_body: str, *, use_llm: bool = True) -> IssueOptimizationResult:
    if not issue_body:
        issue_body = ""

    guard_result = check_prompt_injection(issue_body)
    if guard_result["blocked"]:
        return IssueOptimizationResult(
            task_splitting=[],
            blocked_tasks=[],
            objective_criteria=[],
            missing_sections=[],
            formatting_issues=[],
            overall_notes="",
            provider_used=None,
            guard_blocked=True,
            guard_reason=guard_result["reason"],
        )

    last_error: str | None = None
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
                chain = template | client  # type: ignore[operator]
                try:
                    import os

                    issue_num = None
                    env_issue = os.environ.get("ISSUE_NUMBER", "")
                    if env_issue.isdigit():
                        issue_num = int(env_issue)

                    response, trace_id, trace_url = _invoke_llm_with_trace(
                        chain,
                        {
                            "issue_body": issue_body,
                            "agent_limitations": "\n".join(
                                f"- {item}" for item in AGENT_LIMITATIONS
                            ),
                        },
                        operation="analyze_issue",
                        issue_number=issue_num,
                    )
                    result, error = _process_llm_response(
                        response,
                        provider,
                        use_llm,
                        client=client,
                        trace_id=trace_id,
                        trace_url=trace_url,
                    )
                    if result:
                        return result
                    if error:
                        last_error = error
                        print(error, file=sys.stderr)
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
                            openai_chain = template | openai_client  # type: ignore[operator]
                            try:
                                response, trace_id, trace_url = _invoke_llm_with_trace(
                                    openai_chain,
                                    {
                                        "issue_body": issue_body,
                                        "agent_limitations": "\n".join(
                                            f"- {item}" for item in AGENT_LIMITATIONS
                                        ),
                                    },
                                    operation="analyze_issue",
                                    issue_number=issue_num,
                                )
                                result, error = _process_llm_response(
                                    response,
                                    openai_provider,
                                    use_llm=use_llm,
                                    client=openai_client,
                                    trace_id=trace_id,
                                    trace_url=trace_url,
                                )
                                if result is not None:
                                    print(
                                        "Successfully analyzed with OpenAI API",
                                        file=sys.stderr,
                                    )
                                    return result
                                if error:
                                    last_error = error
                                    print(error, file=sys.stderr)
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
    if last_error:
        note = result.overall_notes or ""
        detail = f"LLM structured output failed: {last_error}"
        result.overall_notes = f"{note} {detail}".strip()
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


def _apply_task_decomposition(formatted_body: str | None, suggestions: dict[str, Any]) -> str:
    # Guard against None input (can happen when issue body is too large)
    if formatted_body is None:
        return ""

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
        # ^\s* always matches (zero or more whitespace)
        indent_match = re.match(r"^\s*", line)
        assert indent_match is not None
        indent = indent_match.group(0)
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

    guard_result = check_prompt_injection(issue_body)
    if guard_result["blocked"]:
        return {
            "formatted_body": issue_body,
            "provider_used": None,
            "used_llm": False,
            "guard_blocked": True,
            "guard_reason": guard_result["reason"],
        }

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
                chain = template | client  # type: ignore[operator]
                try:
                    import os

                    issue_num = None
                    env_issue = os.environ.get("ISSUE_NUMBER", "")
                    if env_issue.isdigit():
                        issue_num = int(env_issue)

                    response, trace_id, trace_url = _invoke_llm_with_trace(
                        chain,
                        {
                            "original_body": issue_body,
                            "suggestions_json": json.dumps(
                                suggestions, ensure_ascii=True, indent=2
                            ),
                        },
                        operation="apply_suggestions",
                        issue_number=issue_num,
                    )
                    content = getattr(response, "content", None) or str(response)
                    formatted = content.strip()
                    if _formatted_output_valid(formatted):
                        formatted = _deduplicate_task_lines(formatted)
                        if _section_duplication_ratio(formatted) > 0:
                            print(
                                "LLM output has duplicated sections, falling back",
                                file=sys.stderr,
                            )
                        else:
                            result = {
                                "formatted_body": formatted,
                                "provider_used": provider,
                                "used_llm": True,
                            }
                            if trace_id:
                                result["langsmith_trace_id"] = trace_id
                            if trace_url:
                                result["langsmith_trace_url"] = trace_url
                            return result
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
                            openai_chain = template | openai_client  # type: ignore[operator]
                            try:
                                response, trace_id, trace_url = _invoke_llm_with_trace(
                                    openai_chain,
                                    {
                                        "original_body": issue_body,
                                        "suggestions_json": json.dumps(
                                            suggestions, ensure_ascii=True, indent=2
                                        ),
                                    },
                                    operation="apply_suggestions",
                                    issue_number=issue_num,
                                )
                                content = getattr(response, "content", None) or str(response)
                                formatted = content.strip()
                                if _formatted_output_valid(formatted):
                                    formatted = _deduplicate_task_lines(formatted)
                                    if _section_duplication_ratio(formatted) > 0:
                                        print(
                                            "OpenAI output has duplicated sections, falling back",
                                            file=sys.stderr,
                                        )
                                    else:
                                        print(
                                            "Successfully applied suggestions with OpenAI API",
                                            file=sys.stderr,
                                        )
                                        result = {
                                            "formatted_body": formatted,
                                            "provider_used": openai_provider,
                                            "used_llm": True,
                                        }
                                        if trace_id:
                                            result["langsmith_trace_id"] = trace_id
                                        if trace_url:
                                            result["langsmith_trace_url"] = trace_url
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
    formatted = _deduplicate_task_lines(formatted)
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
            if result.get("guard_blocked"):
                payload["guard_blocked"] = True
                payload["guard_reason"] = result.get("guard_reason") or ""
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
