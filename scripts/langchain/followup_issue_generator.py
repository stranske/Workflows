#!/usr/bin/env python3
"""
Generate properly structured follow-up issues from verification feedback.

This script takes verification data (from verify:evaluate or verify:compare)
along with the original issue and agent execution history, then produces
a well-structured follow-up issue ready for a new keepalive cycle.

The output follows AGENT_ISSUE_TEMPLATE format with:
- Clear Why section explaining the follow-up context
- Specific, actionable tasks derived from verification concerns
- Testable acceptance criteria (subset of original unmet criteria)
- Background context in collapsible sections

Run with:
    python scripts/langchain/followup_issue_generator.py \
        --original-issue issue.md \
        --verification-data verify.json \
        --agent-log codex.jsonl \
        --output followup.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Section alias handling aligned with issue_formatter/issue_optimizer.
SECTION_ALIASES = {
    "why": ["why", "motivation", "summary", "goals"],
    "scope": ["scope", "context", "background", "overview"],
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

LIST_ITEM_REGEX = re.compile(r"^\s*([-*+]|\d+[.)]|[A-Za-z][.)])\s+(.*)$")
CHECKBOX_REGEX = re.compile(r"^\[([ xX])\]\s*(.*)$")


def _normalize_heading(text: str) -> str:
    """Normalize heading text for comparison (lowercase, stripped of markdown)."""
    cleaned = re.sub(r"[#*_:]+", " ", text).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


# Pre-computed normalized aliases for efficient section resolution.
# Maps normalized alias string -> section key
_NORMALIZED_ALIAS_MAP: dict[str, str] = {
    _normalize_heading(alias): key for key, aliases in SECTION_ALIASES.items() for alias in aliases
}

# Prompts for multi-round LLM interaction
# NOTE: We use a reasoning model (o1/o3-mini) for ANALYZE_VERIFICATION_PROMPT
# because this step requires deep analysis to produce useful follow-up tasks.

ANALYZE_VERIFICATION_PROMPT = """
You are a senior engineer analyzing why a coding agent's work didn't fully meet acceptance criteria.
Your analysis will be used to create a follow-up issue for another agent attempt.

## Critical Distinction
Your analysis should separate:
1. **Actionable tasks** - concrete code changes an agent can make
2. **Planning artifacts** - insights useful for you to reason but NOT included in the final issue

## Verification Feedback
{provider_verdicts}

## Specific Concerns Raised by Verifiers
{concerns}

## Low Scores (areas needing improvement)
{low_scores}

## Original Acceptance Criteria (from the issue the agent worked on)
{original_acceptance_criteria}

## Agent Execution History
- Iterations run: {iteration_count}
- Tasks attempted: {tasks_attempted}
- Tasks completed: {tasks_completed}
- Items the agent couldn't make progress on: {non_actionable_items}

## Previous Iteration Details (if useful)
{iteration_details}

## Your Task
Analyze what went wrong and what SPECIFICALLY needs to change. Focus on:

1. **Which original acceptance criteria are actually still unmet?**
   - Don't assume all criteria need rework. Only include criteria that the
     verification shows are genuinely incomplete.
   - Rewrite criteria that were unclear or unmeasurable as clear, testable statements.

2. **What concrete code changes are needed?**
   - Convert verification concerns into specific tasks (add test X, fix function Y, update config Z)
   - Verification concerns are NOT tasks themselves - they describe problems, not solutions
   - Each task must be something a coding agent can complete in code

3. **Did previous iterations reveal blockers the next agent should avoid?**
   - Only include if there's specific, detailed information about what didn't work and why
   - "Iteration 3 failed" is NOT useful. "Iteration 3 attempted X approach but
     failed because Y, so try Z instead" IS useful

Output JSON:
{{
  "rewritten_acceptance_criteria": [
    {{"original": "...", "rewritten": "...", "why_changed": "..."}}
  ],
  "concrete_tasks": [
    {{"task": "...", "why_needed": "...", "estimated_complexity": "small|medium|large"}}
  ],
  "blockers_to_avoid": [
    {{"what_failed": "...", "why_it_failed": "...", "what_to_try_instead": "..."}}
  ],
  "items_requiring_human_action": [
    {{"item": "...", "why_human_needed": "..."}}
  ]
}}
""".strip()

GENERATE_TASKS_PROMPT = """
Convert the analysis into a final task list for the follow-up issue.

## Analysis Results
{analysis_json}

## Original Tasks (for context only - do NOT copy these directly)
{original_tasks}

## Critical Guidelines

**Tasks MUST be:**
- Concrete code changes: "Add test for X", "Implement Y in file Z", "Fix bug where A happens"
- Completable by an automated coding agent (no manual steps, no external services, no UI testing)
- Sized appropriately: not too big ("fix everything") or too small ("add a comma")

**Tasks MUST NOT be:**
- Verification concerns restated as tasks (e.g., "The safety rules section
  is incomplete" is NOT a task)
- Original acceptance criteria restated as tasks
- Vague actions like "improve", "ensure", "address concerns about"

**Deferred items:** Anything requiring credentials, external APIs, manual
testing, or human decisions

Output JSON:
{{
  "tasks": [
    {{"task": "...", "why": "...", "files_affected": ["..."]}}
  ],
  "deferred": [
    {{"item": "...", "reason_deferred": "..."}}
  ]
}}
""".strip()

GENERATE_ACCEPTANCE_CRITERIA_PROMPT = """
Generate SPECIFIC, TESTABLE acceptance criteria for the follow-up issue.

## Tasks That Will Be Completed
{tasks_json}

## Original Acceptance Criteria (rewritten/refined)
{unmet_criteria}

## Critical Requirements

**Each criterion MUST be:**
- Objectively verifiable by an automated system or code review
- Specific enough to pass/fail without subjective judgment
- Tied to a concrete task or original requirement

**GOOD acceptance criteria examples:**
- "The `calculateTax()` function returns correct values for all test cases in `test_tax.py`"
- "All Python files pass `ruff check` with no errors"
- "The README.md contains installation instructions with at least 3 steps"
- "API endpoint `/users/{{id}}` returns 404 status code when user doesn't exist"

**BAD acceptance criteria (NEVER write these):**
- "All verification concerns are addressed" (not specific)
- "Code quality is improved" (subjective)
- "Tests pass" (too vague - which tests?)
- "Documentation is updated" (not testable - updated how?)

Output JSON:
{{
  "acceptance_criteria": [
    {{
      "criterion": "[Specific testable condition]",
      "verification_method": "[How to verify: run command X, check file Y, etc.]",
      "related_task": "[Which task this validates]"
    }}
  ]
}}
""".strip()

FORMAT_FOLLOWUP_ISSUE_PROMPT = """
Format the final follow-up issue for a coding agent to work on.

## Context
Original PR: #{pr_number}
Original Issue: #{original_issue_number}
Verification Verdict: {verdict}

## Content to Include
Why Section: {why_section}
Tasks: {tasks_json}
Acceptance Criteria: {acceptance_criteria_json}
Deferred Items: {deferred_tasks_json}
Background (failures to avoid): {background_analysis}

## Issue Structure

Use this exact structure:

```markdown
## Why
[Brief explanation of what needs to happen and why]

## Tasks
- [ ] Task 1
- [ ] Task 2
...

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
...

## Implementation Notes
[Specific guidance about files, approaches, or patterns to use]

<details>
<summary>Background (previous attempt context)</summary>

[Only include if there are specific failures to avoid. Do NOT include generic iteration summaries.]

</details>
```

## Critical Rules
1. Do NOT include "Remaining Unchecked Items" or "Iteration Details" sections
   unless they contain specific, useful failure context
2. Tasks should be concrete actions, not verification concerns restated
3. Acceptance criteria must be testable (not "all concerns addressed")
4. Keep the main body focused - hide background/history in the collapsible section
5. Do NOT include the entire analysis object - only include specific failure
   contexts from `blockers_to_avoid`

Output the complete markdown issue body.
""".strip()


@dataclass
class VerificationData:
    """Data extracted from verification comments."""

    provider_verdicts: dict[str, dict[str, Any]] = field(default_factory=dict)
    concerns: list[str] = field(default_factory=list)
    low_scores: dict[str, int] = field(default_factory=dict)
    iteration_count: int = 0
    tasks_attempted: int = 0
    tasks_completed: int = 0
    non_actionable_items: list[str] = field(default_factory=list)
    structural_issues: list[str] = field(default_factory=list)


@dataclass
class OriginalIssueData:
    """Data extracted from the original issue."""

    title: str = ""
    number: int = 0
    why: str = ""
    scope: str = ""
    tasks: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    implementation_notes: str = ""


@dataclass
class FollowupIssue:
    """The generated follow-up issue."""

    title: str
    body: str
    labels: list[str] = field(default_factory=list)


def extract_verification_data(comment_body: str) -> VerificationData:
    """Extract structured data from verification comment(s)."""
    data = VerificationData()

    # Extract provider verdicts (from comparison reports)
    lines = comment_body.splitlines()
    in_provider_table = False
    for line in lines:
        if re.search(
            r"\|\s*Provider\s*\|\s*Model\s*\|\s*Verdict\s*\|\s*Confidence",
            line,
            re.IGNORECASE,
        ):
            in_provider_table = True
            continue
        if not in_provider_table:
            continue
        if not line.strip().startswith("|"):
            in_provider_table = False
            continue
        if re.match(r"^\|\s*-", line):
            continue
        cols = [col.strip() for col in line.strip().strip("|").split("|")]
        if len(cols) < 4:
            continue
        provider = cols[0]
        if provider.lower() == "provider":
            continue
        model = cols[1]
        verdict = cols[2]
        confidence_text = cols[3]
        confidence_match = re.search(r"\d+", confidence_text)
        confidence = int(confidence_match.group(0)) if confidence_match else 0
        data.provider_verdicts[provider] = {
            "model": model,
            "verdict": verdict.strip(),
            "confidence": confidence,
        }

    # Extract verdicts from provider detail sections as a fallback.
    current_provider = None
    for line in lines:
        header_match = re.match(r"^####\s+(.+)$", line.strip())
        if header_match:
            current_provider = header_match.group(1).strip()
            continue
        if not current_provider:
            continue
        verdict_match = re.search(r"-\s*\*\*Verdict:\*\*\s*([^\n]+)", line)
        if verdict_match:
            verdict = verdict_match.group(1).strip()
            entry = data.provider_verdicts.setdefault(
                current_provider, {"model": "", "verdict": verdict, "confidence": 0}
            )
            entry["verdict"] = verdict
            continue
        confidence_match = re.search(r"-\s*\*\*Confidence:\*\*\s*([^\n]+)", line)
        if confidence_match:
            confidence_text = confidence_match.group(1)
            conf_digits = re.search(r"\d+", confidence_text)
            confidence = int(conf_digits.group(0)) if conf_digits else 0
            entry = data.provider_verdicts.setdefault(
                current_provider, {"model": "", "verdict": "", "confidence": 0}
            )
            entry["confidence"] = confidence

    # Also try single-provider format
    single_verdict = re.search(
        r"Verdict:\s*(?:\*\*(.+?)\*\*|([^\n@]+?))(?:\s*@|\s*$)",
        comment_body,
        re.IGNORECASE,
    )
    if single_verdict and not data.provider_verdicts:
        verdict = (single_verdict.group(1) or single_verdict.group(2) or "").strip()
        confidence_match = re.search(r"Verdict:.*?@?\s*(\d+)%", comment_body, re.IGNORECASE)
        confidence = int(confidence_match.group(1)) if confidence_match else 0
        data.provider_verdicts["default"] = {
            "verdict": verdict,
            "confidence": confidence,
        }

    # Extract concerns - handle multiple formats
    # Format 1: ### Concerns heading (old format)
    # Format 2: - **Concerns:** bullet list (Provider Comparison Report format)
    all_concerns: list[str] = []

    # Try heading format first
    concerns_heading_match = re.search(
        r"### Concerns\s*\n([\s\S]*?)(?=###|##|$)", comment_body, re.IGNORECASE
    )
    if concerns_heading_match:
        concerns_text = concerns_heading_match.group(1).strip()
        all_concerns.extend(
            c.strip().lstrip("- ").lstrip("* ")
            for c in concerns_text.split("\n")
            if c.strip() and not c.strip().startswith("#")
        )

    # Try Provider Comparison Report format: "- **Concerns:**\n  - concern1\n  - concern2"
    concerns_bullet_matches = re.findall(
        r"- \*\*Concerns:\*\*\s*\n((?:\s+-\s+[^\n]+\n?)+)", comment_body
    )
    for match in concerns_bullet_matches:
        # Extract individual concerns from the indented list
        for line in match.split("\n"):
            line = line.strip()
            if line.startswith("-"):
                concern = line.lstrip("- ").strip()
                if concern and len(concern) > 10:  # Skip tiny fragments
                    all_concerns.append(concern)

    # Also extract from "Unique Insights" section which often has good concerns
    unique_insights_match = re.search(
        r"### Unique Insights\s*\n([\s\S]*?)(?=\n##|\n---|\Z)", comment_body
    )
    if unique_insights_match:
        insights_text = unique_insights_match.group(1)
        # Format: "- provider: concern1; concern2; concern3"
        for line in insights_text.split("\n"):
            if line.strip().startswith("-"):
                # Remove provider prefix like "- github-models: "
                content = re.sub(r"^-\s*\w+(?:-\w+)?:\s*", "", line.strip())
                # Split on semicolons
                for concern in content.split(";"):
                    concern = concern.strip()
                    if concern and len(concern) > 15:
                        all_concerns.append(concern)

    # Deduplicate while preserving order, and filter out spurious entries
    seen: set[str] = set()
    data.concerns = []
    spurious_patterns = [
        r"^\d+\s+verification concern",  # "10 verification concerns"
        r"^\d+\s+unchecked task",  # "5 unchecked tasks"
        r"^-\s*\d+\s",  # "- 10 ..."
    ]
    for c in all_concerns:
        c_lower = c.lower()
        # Skip spurious entries
        if any(re.match(p, c_lower) for p in spurious_patterns):
            continue
        if c_lower not in seen:
            seen.add(c_lower)
            data.concerns.append(c)

    # Extract low scores (handle decimal scores like 6.0/10)
    score_pattern = re.compile(r"(\w+):\s*(\d+(?:\.\d+)?)/10", re.IGNORECASE)
    for match in score_pattern.finditer(comment_body):
        category, score = match.groups()
        score_float = float(score)
        if score_float < 7:
            data.low_scores[category] = int(score_float)

    # Extract iteration/task data from structural analysis
    iter_match = re.search(r"Agent ran (\d+) iterations?", comment_body)
    if iter_match:
        data.iteration_count = int(iter_match.group(1))

    remaining_match = re.search(r"Remaining unchecked items?:\s*(\d+)\s*of\s*(\d+)", comment_body)
    if remaining_match:
        unchecked, total = int(remaining_match.group(1)), int(remaining_match.group(2))
        data.tasks_attempted = total
        data.tasks_completed = total - unchecked

    # Extract non-actionable items
    non_actionable_match = re.search(
        r"Non-actionable items.*?:\s*\n([\s\S]*?)(?=\n\n|\n###|\n##|$)", comment_body, re.IGNORECASE
    )
    if non_actionable_match:
        items_text = non_actionable_match.group(1)
        data.non_actionable_items = [
            item.strip().lstrip("- `").rstrip("`")
            for item in items_text.split("\n")
            if item.strip() and item.strip().startswith("-")
        ]

    # Extract structural issues
    structural_match = re.search(
        r"### ⚠️ Issues Detected.*?\n([\s\S]*?)(?=\n##|\n---|\Z)", comment_body, re.IGNORECASE
    )
    if structural_match:
        issues_text = structural_match.group(1)
        problem_pattern = re.compile(r"\*\*Problem:\*\*\s*(.+?)(?=\n\*\*|\n-|\Z)", re.DOTALL)
        for match in problem_pattern.finditer(issues_text):
            data.structural_issues.append(match.group(1).strip())

    return data


def extract_original_issue_data(
    issue_body: str, issue_number: int = 0, title: str = ""
) -> OriginalIssueData:
    """Extract structured data from the original issue."""
    data = OriginalIssueData(number=issue_number, title=title)

    sections = _parse_sections(issue_body)

    data.why = "\n".join(sections["why"]).strip()
    data.scope = "\n".join(sections["scope"]).strip()
    data.implementation_notes = "\n".join(sections["implementation"]).strip()

    # Extract tasks and acceptance criteria from checklist/bulleted items.
    data.tasks = _parse_checklist(sections["tasks"])
    data.acceptance_criteria = _parse_checklist(sections["acceptance"])

    return data


def _resolve_section(label: str) -> str | None:
    """Map a heading label to a known section key, or None if unrecognized.

    Uses pre-computed _NORMALIZED_ALIAS_MAP for efficient O(1) lookup.
    """
    normalized = _normalize_heading(label)
    return _NORMALIZED_ALIAS_MAP.get(normalized)


def _parse_sections(body: str) -> dict[str, list[str]]:
    """Parse issue body into recognized sections.

    Splits the body by headings (#, ##, ###) and maps content to known section keys.
    Unrecognized headings terminate the current section.
    Deeper subheadings (####, #####, etc.) within a section are preserved as content.
    """
    sections: dict[str, list[str]] = {key: [] for key in SECTION_TITLES}
    current: str | None = None
    for line in body.splitlines():
        # Match section headings (#, ##, ###) - GitHub issue forms use ### for fields
        # Deeper headings (####, #####) are kept as content within the current section
        heading_match = re.match(r"^\s*#{1,3}\s+(.*)$", line)
        if heading_match:
            section_key = _resolve_section(heading_match.group(1))
            # Update current - set to None for unrecognized headings
            # This prevents content under "## Random Notes" etc. from being
            # appended to the previous recognized section
            current = section_key
            continue
        if current:
            sections[current].append(line)
    return sections


def _strip_checkbox(line: str, list_match: re.Match[str] | None = None) -> str:
    """Extract text content from a list item, stripping bullet and checkbox markers.

    Args:
        line: The line to process.
        list_match: Optional pre-computed LIST_ITEM_REGEX match to avoid re-matching.
    """
    stripped = line.strip()
    match = list_match or LIST_ITEM_REGEX.match(stripped)
    if not match:
        return stripped
    content = match.group(2).strip()
    checkbox = CHECKBOX_REGEX.match(content)
    if checkbox:
        return checkbox.group(2).strip()
    return content


def _parse_checklist(lines: list[str]) -> list[str]:
    """Extract checklist items from lines, handling both checkbox and plain list formats."""
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # First try direct checkbox at start of line (rare but possible)
        checkbox_match = CHECKBOX_REGEX.match(stripped)
        if checkbox_match:
            value = checkbox_match.group(2).strip()
            if value and len(value) > 3:
                items.append(value)
            continue
        # Then try list item (with optional checkbox inside)
        list_match = LIST_ITEM_REGEX.match(stripped)
        if list_match:
            # Pass the match to avoid re-matching in _strip_checkbox
            value = _strip_checkbox(line, list_match)
            if value and len(value) > 3:
                items.append(value)
    return items


def _get_llm_client(reasoning: bool = False) -> tuple[Any, str] | None:
    """Get LLM client with fallback.

    Args:
        reasoning: If True, use a reasoning model (o3-mini) for complex analysis.
                   If False, use standard model (gpt-4o) for formatting tasks.
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        print(f"Warning: langchain_openai not available: {e}", file=sys.stderr)
        return None

    # GitHub Models constants (inline to avoid import dependency)
    github_models_base_url = "https://models.inference.ai.azure.com"
    github_default_model = "gpt-4o"

    # Select model based on task type
    # Reasoning models (o3-mini) are better for deep analysis and understanding
    # Standard models (gpt-4o) are better for formatting and generation
    if reasoning:
        default_model = "o3-mini"
        env_var = "FOLLOWUP_REASONING_MODEL"
    else:
        default_model = "gpt-4o"
        env_var = "FOLLOWUP_MODEL"

    # Prefer OpenAI for complex multi-turn generation
    if os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get(env_var, default_model)
        print(f"Using OpenAI with model: {model}", file=sys.stderr)
        # Reasoning models don't support temperature parameter
        if model.startswith(("o1", "o3")):
            return ChatOpenAI(model=model, timeout=60), model
        return ChatOpenAI(model=model, temperature=0.3, timeout=30), model

    # Fall back to GitHub Models
    if os.environ.get("GITHUB_TOKEN"):
        print(f"Using GitHub Models with model: {github_default_model}", file=sys.stderr)
        return (
            ChatOpenAI(
                model=github_default_model,
                base_url=github_models_base_url,
                api_key=os.environ["GITHUB_TOKEN"],
                temperature=0.3,
                timeout=30,
            ),
            github_default_model,
        )

    print("Warning: No LLM API keys found (OPENAI_API_KEY or GITHUB_TOKEN)", file=sys.stderr)
    return None


def _prepare_iteration_details(codex_log: str) -> str:
    """Filter iteration details to only include useful failure information.

    We only want to include information that helps the next agent avoid mistakes.
    Information about successful iterations is not useful - we don't need to know
    what worked, only what failed and why.

    Returns filtered iteration details or a message indicating no useful details.
    """
    if not codex_log:
        return "No previous iteration details available."

    # Look for failure patterns in the log
    useful_patterns = [
        "error",
        "failed",
        "exception",
        "timeout",
        "could not",
        "unable to",
        "blocked by",
        "missing",
        "not found",
        "rejected",
        "invalid",
    ]

    lines = codex_log.split("\n")
    useful_lines = []

    for i, line in enumerate(lines):
        line_lower = line.lower()
        # Include lines with failure indicators and some context
        if any(pattern in line_lower for pattern in useful_patterns):
            # Include 2 lines before and after for context
            start = max(0, i - 2)
            end = min(len(lines), i + 3)
            context_block = "\n".join(lines[start:end])
            if context_block not in useful_lines:
                useful_lines.append(context_block)

    if not useful_lines:
        return (
            "Previous iterations completed without recorded failures. "
            "No specific blockers to avoid."
        )

    # Deduplicate and limit length
    unique_blocks = list(dict.fromkeys(useful_lines))[:5]  # Max 5 failure contexts

    result = "**Relevant failure contexts from previous iterations:**\n\n"
    for block in unique_blocks:
        result += f"```\n{block.strip()}\n```\n\n"

    return result.strip()


def _invoke_llm(prompt: str, client: Any) -> str:
    """Invoke LLM and return response text."""
    from langchain_core.messages import HumanMessage

    response = client.invoke([HumanMessage(content=prompt)])
    return response.content


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to find JSON in code block
    json_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if json_match:
        text = json_match.group(1)

    # Clean up common issues
    text = text.strip()
    if not text.startswith("{"):
        # Find the start of JSON
        start = text.find("{")
        if start >= 0:
            text = text[start:]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def generate_followup_issue(
    verification_data: VerificationData,
    original_issue: OriginalIssueData,
    pr_number: int,
    codex_log: str | None = None,
    use_llm: bool = True,
) -> FollowupIssue:
    """
    Generate a properly structured follow-up issue.

    This uses multiple LLM rounds:
    1. Analyze verification feedback + original issue to understand gaps (reasoning model)
    2. Generate specific, actionable tasks
    3. Generate testable acceptance criteria
    4. Format the final issue
    """
    if not use_llm:
        return _generate_without_llm(verification_data, original_issue, pr_number)

    # Get reasoning model for analysis (o3-mini)
    reasoning_client_info = _get_llm_client(reasoning=True)
    # Get standard model for formatting (gpt-4o)
    standard_client_info = _get_llm_client(reasoning=False)

    # Handle partial availability: use whatever client(s) we have
    if reasoning_client_info and standard_client_info:
        # Best case: both clients available
        return _generate_with_llm(
            verification_data,
            original_issue,
            pr_number,
            codex_log,
            reasoning_client=reasoning_client_info[0],
            reasoning_model=reasoning_client_info[1],
            standard_client=standard_client_info[0],
            standard_model=standard_client_info[1],
        )
    elif reasoning_client_info:
        # Only reasoning client available - use it for all steps
        return _generate_with_llm(
            verification_data,
            original_issue,
            pr_number,
            codex_log,
            reasoning_client=reasoning_client_info[0],
            reasoning_model=reasoning_client_info[1],
            standard_client=reasoning_client_info[0],
            standard_model=reasoning_client_info[1],
        )
    elif standard_client_info:
        # Only standard client available - use it for all steps
        return _generate_with_llm(
            verification_data,
            original_issue,
            pr_number,
            codex_log,
            reasoning_client=standard_client_info[0],
            reasoning_model=standard_client_info[1],
            standard_client=standard_client_info[0],
            standard_model=standard_client_info[1],
        )
    else:
        # No LLM clients available
        return _generate_without_llm(verification_data, original_issue, pr_number)


def _generate_with_llm(
    verification_data: VerificationData,
    original_issue: OriginalIssueData,
    pr_number: int,
    codex_log: str | None,
    reasoning_client: Any,
    reasoning_model: str,  # noqa: ARG001 - kept for API compatibility
    standard_client: Any,
    standard_model: str,  # noqa: ARG001 - kept for API compatibility
) -> FollowupIssue:
    """Generate follow-up issue using multi-round LLM interaction.

    Uses reasoning model (o3-mini) for analysis, standard model (gpt-4o) for formatting.
    """

    # Prepare iteration details - only include if there's useful failure information
    iteration_details = (
        _prepare_iteration_details(codex_log)
        if codex_log
        else "No previous iteration details available."
    )

    # Round 1: Analyze verification feedback (use REASONING model for deep analysis)
    analyze_prompt = ANALYZE_VERIFICATION_PROMPT.format(
        provider_verdicts=json.dumps(verification_data.provider_verdicts, indent=2),
        concerns="\n".join(f"- {c}" for c in verification_data.concerns),
        low_scores=json.dumps(verification_data.low_scores),
        original_acceptance_criteria="\n".join(
            f"- [ ] {ac}" for ac in original_issue.acceptance_criteria
        ),
        iteration_count=verification_data.iteration_count,
        tasks_attempted=verification_data.tasks_attempted,
        tasks_completed=verification_data.tasks_completed,
        non_actionable_items="\n".join(
            f"- {item}" for item in verification_data.non_actionable_items
        ),
        iteration_details=iteration_details,
    )

    analysis_response = _invoke_llm(analyze_prompt, reasoning_client)
    analysis = _extract_json(analysis_response)

    # Round 2: Generate tasks (use standard model - straightforward task)
    tasks_prompt = GENERATE_TASKS_PROMPT.format(
        analysis_json=json.dumps(analysis, indent=2),
        original_tasks="\n".join(
            f"- [ ] {t}" for t in original_issue.tasks[:20]
        ),  # Limit for token budget
    )

    tasks_response = _invoke_llm(tasks_prompt, standard_client)
    tasks_data = _extract_json(tasks_response)

    # Round 3: Generate acceptance criteria (use standard model)
    ac_prompt = GENERATE_ACCEPTANCE_CRITERIA_PROMPT.format(
        tasks_json=json.dumps(tasks_data.get("tasks", []), indent=2),
        unmet_criteria=json.dumps(analysis.get("rewritten_acceptance_criteria", []), indent=2),
    )

    ac_response = _invoke_llm(ac_prompt, standard_client)
    ac_data = _extract_json(ac_response)

    # Round 4: Format final issue (use standard model)
    why_section = _build_why_section(verification_data, original_issue, pr_number)

    format_prompt = FORMAT_FOLLOWUP_ISSUE_PROMPT.format(
        pr_number=pr_number,
        original_issue_number=original_issue.number,
        verdict=_get_primary_verdict(verification_data),
        why_section=why_section,
        tasks_json=json.dumps(tasks_data.get("tasks", []), indent=2),
        acceptance_criteria_json=json.dumps(ac_data.get("acceptance_criteria", []), indent=2),
        deferred_tasks_json=json.dumps(tasks_data.get("deferred", []), indent=2),
        background_analysis=json.dumps(
            {
                "structural_issues": verification_data.structural_issues,
                "blockers_to_avoid": analysis.get("blockers_to_avoid", []),
            },
            indent=2,
        ),
    )

    issue_body = _invoke_llm(format_prompt, standard_client)

    # Generate title from concrete tasks
    concrete_tasks = analysis.get("concrete_tasks", [])
    if concrete_tasks:
        title_focus = concrete_tasks[0].get("task", "verification concerns")[:50]
    else:
        title_focus = "verification concerns"
    title = f"[Follow-up] {title_focus} (PR #{pr_number})"

    return FollowupIssue(
        title=title,
        body=issue_body,
        labels=["follow-up", "agents:optimize"],
    )


def _generate_without_llm(
    verification_data: VerificationData,
    original_issue: OriginalIssueData,
    pr_number: int,
) -> FollowupIssue:
    """Generate follow-up issue without LLM (structured extraction only)."""

    why_section = _build_why_section(verification_data, original_issue, pr_number)

    # Convert concerns to tasks
    tasks = []
    for concern in verification_data.concerns[:10]:  # Limit
        # Clean up concern to be task-like
        task = concern
        if not task.lower().startswith(("add", "fix", "implement", "update", "ensure")):
            task = f"Address: {task}"
        tasks.append(task)

    # Use original unmet acceptance criteria
    acceptance_criteria = original_issue.acceptance_criteria[:10]

    # Build body
    body_parts = [
        "## Why",
        "",
        why_section,
        "",
        "## Scope",
        "",
        f"Address verification concerns from PR #{pr_number} related to {original_issue.title}.",
        "",
        "## Tasks",
        "",
    ]

    for task in tasks:
        body_parts.append(f"- [ ] {task}")

    body_parts.extend(
        [
            "",
            "## Acceptance Criteria",
            "",
        ]
    )

    for ac in acceptance_criteria:
        body_parts.append(f"- [ ] {ac}")

    # Add background context in collapsible section
    body_parts.extend(
        [
            "",
            "## Background Context",
            "",
            "<details>",
            "<summary>Verification analysis details</summary>",
            "",
            "### Provider Verdicts",
            "",
        ]
    )

    for provider, data in verification_data.provider_verdicts.items():
        body_parts.append(
            f"- **{provider}**: {data.get('verdict', 'Unknown')} @ {data.get('confidence', 0)}%"
        )

    if verification_data.structural_issues:
        body_parts.extend(
            [
                "",
                "### Structural Issues Detected",
                "",
            ]
        )
        for issue in verification_data.structural_issues:
            body_parts.append(f"- {issue}")

    if verification_data.non_actionable_items:
        body_parts.extend(
            [
                "",
                "### Non-actionable Items Encountered",
                "",
            ]
        )
        for item in verification_data.non_actionable_items[:5]:
            body_parts.append(f"- `{item}`")

    body_parts.extend(
        [
            "",
            "</details>",
            "",
            "---",
            "*Auto-generated by followup-issue-generator*",
        ]
    )

    title = f"[Follow-up] Address verification concerns from PR #{pr_number}"

    return FollowupIssue(
        title=title,
        body="\n".join(body_parts),
        labels=["follow-up", "agents:optimize"],
    )


def _build_why_section(
    verification_data: VerificationData,
    original_issue: OriginalIssueData,
    pr_number: int,
) -> str:
    """Build the Why section explaining the follow-up context."""
    verdict = _get_primary_verdict(verification_data)

    parts = [
        f"PR #{pr_number} addressed issue #{original_issue.number} but verification "
        f"identified concerns (verdict: **{verdict}**).",
    ]

    if verification_data.tasks_completed > 0:
        completion_rate = (
            verification_data.tasks_completed / verification_data.tasks_attempted * 100
            if verification_data.tasks_attempted > 0
            else 0
        )
        parts.append(
            f"The agent completed {verification_data.tasks_completed} of "
            f"{verification_data.tasks_attempted} tasks ({completion_rate:.0f}%) "
            f"over {verification_data.iteration_count} iterations."
        )

    if verification_data.structural_issues:
        parts.append("The original issue had structural problems that may have hindered progress.")

    parts.append("This follow-up addresses the remaining gaps with improved task structure.")

    return " ".join(parts)


def _get_primary_verdict(verification_data: VerificationData) -> str:
    """Get the primary verdict from verification data."""
    if not verification_data.provider_verdicts:
        return "Unknown"

    # Prefer openai verdict, then any other
    if "openai" in verification_data.provider_verdicts:
        return verification_data.provider_verdicts["openai"].get("verdict", "Unknown")

    first_provider = next(iter(verification_data.provider_verdicts.values()))
    return first_provider.get("verdict", "Unknown")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate follow-up issue from verification feedback."
    )
    parser.add_argument(
        "--verification-comment",
        type=str,
        help="Raw verification comment text (or path to file)",
    )
    parser.add_argument(
        "--original-issue",
        type=str,
        help="Original issue body (or path to file)",
    )
    parser.add_argument(
        "--original-issue-number",
        type=int,
        default=0,
        help="Original issue number",
    )
    parser.add_argument(
        "--original-issue-title",
        type=str,
        default="",
        help="Original issue title",
    )
    parser.add_argument(
        "--pr-number",
        type=int,
        required=True,
        help="PR number for the follow-up",
    )
    parser.add_argument(
        "--codex-log",
        type=str,
        help="Path to Codex JSONL log file",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Generate without LLM (structured extraction only)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path",
    )

    args = parser.parse_args()

    # Load verification comment
    if args.verification_comment:
        if Path(args.verification_comment).is_file():
            verification_text = Path(args.verification_comment).read_text()
        else:
            verification_text = args.verification_comment
    else:
        verification_text = sys.stdin.read()

    # Load original issue
    original_text = ""
    if args.original_issue:
        if Path(args.original_issue).is_file():
            original_text = Path(args.original_issue).read_text()
        else:
            original_text = args.original_issue

    # Load codex log
    codex_log = None
    if args.codex_log and Path(args.codex_log).is_file():
        codex_log = Path(args.codex_log).read_text()

    # Parse data
    verification_data = extract_verification_data(verification_text)
    original_issue = extract_original_issue_data(
        original_text,
        issue_number=args.original_issue_number,
        title=args.original_issue_title,
    )

    # Debug: show extracted data
    print(f"Extracted {len(verification_data.concerns)} concerns", file=sys.stderr)
    print(
        f"Extracted {len(verification_data.provider_verdicts)} provider verdicts", file=sys.stderr
    )
    print(
        f"Extracted {len(original_issue.acceptance_criteria)} acceptance criteria", file=sys.stderr
    )
    print(f"Extracted {len(original_issue.tasks)} tasks", file=sys.stderr)
    if verification_data.concerns:
        print("Sample concerns:", file=sys.stderr)
        for c in verification_data.concerns[:3]:
            print(f"  - {c[:80]}...", file=sys.stderr)

    # Generate follow-up
    followup = generate_followup_issue(
        verification_data=verification_data,
        original_issue=original_issue,
        pr_number=args.pr_number,
        codex_log=codex_log,
        use_llm=not args.no_llm,
    )

    # Output
    if args.json:
        output = json.dumps(
            {
                "title": followup.title,
                "body": followup.body,
                "labels": followup.labels,
            },
            indent=2,
        )
    else:
        output = f"# {followup.title}\n\n{followup.body}"

    if args.output:
        Path(args.output).write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
