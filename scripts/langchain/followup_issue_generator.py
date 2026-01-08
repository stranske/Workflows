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

# Prompts for multi-round LLM interaction
ANALYZE_VERIFICATION_PROMPT = """
You are analyzing verification feedback from a code review to understand what went wrong.

## Verification Data
Provider verdicts: {provider_verdicts}
Concerns raised: {concerns}
Low scores: {low_scores}

## Original Issue Acceptance Criteria
{original_acceptance_criteria}

## Agent Execution Summary
Iterations: {iteration_count}
Tasks attempted: {tasks_attempted}
Tasks completed: {tasks_completed}
Non-actionable items encountered: {non_actionable_items}

Analyze and output JSON:
{{
  "unmet_criteria": [
    {{"criterion": "...", "status": "achievable|impossible|problematic", "reason": "...", "fix_suggestion": "..."}}
  ],
  "key_concerns": [
    {{"concern": "...", "root_cause": "...", "actionable_fix": "..."}}
  ],
  "structural_issues": [
    {{"issue": "...", "impact": "...", "prevention": "..."}}
  ],
  "recommended_focus": ["Top 3-5 items to address first"],
  "should_defer": ["Items to defer to separate issue"]
}}
""".strip()

GENERATE_TASKS_PROMPT = """
Based on this analysis, generate specific, actionable tasks for a follow-up issue.

## Analysis Results
{analysis_json}

## Original Tasks (for reference)
{original_tasks}

## Guidelines
- Each task must be completable by an automated coding agent
- Size tasks for agent work: specific enough to complete in one iteration (not "fix everything")
- Use action verbs: "Add", "Implement", "Fix", "Update"
- Include file paths when known
- Do NOT include tasks that require external credentials, manual UI testing, or infrastructure changes

Output JSON:
{{
  "tasks": [
    {{"task": "...", "priority": "high|medium|low", "estimated_minutes": 15, "files_likely_affected": ["..."]}}
  ],
  "deferred_tasks": [
    {{"task": "...", "reason": "...", "suggested_approach": "..."}}
  ]
}}
""".strip()

GENERATE_ACCEPTANCE_CRITERIA_PROMPT = """
Generate testable acceptance criteria for the follow-up issue.

## Tasks to Complete
{tasks_json}

## Original Unmet Acceptance Criteria
{unmet_criteria}

## Guidelines
- Each criterion must be objectively verifiable
- Include specific values, file paths, or behaviors where possible
- Avoid subjective terms like "clean", "fast", "intuitive"
- Format: "- [ ] [Specific testable condition]"

Output JSON:
{{
  "acceptance_criteria": [
    {{"criterion": "...", "verification_method": "..."}}
  ]
}}
""".strip()

FORMAT_FOLLOWUP_ISSUE_PROMPT = """
Format the final follow-up issue in AGENT_ISSUE_TEMPLATE format.

## Context
Original PR: #{pr_number}
Original Issue: #{original_issue_number}
Verification Verdict: {verdict}

## Generated Content
Why: {why_section}
Tasks: {tasks_json}
Acceptance Criteria: {acceptance_criteria_json}
Deferred Tasks: {deferred_tasks_json}
Background Analysis: {background_analysis}

## Guidelines
- Put background/historical context in a collapsible <details> section at the end
- Lead with the actionable content (Why, Tasks, Acceptance Criteria)
- Keep the main body focused on what the agent needs to do
- Include Implementation Notes if specific files/approaches are known

Output the complete markdown issue body (not JSON).
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
    # Pattern: | provider | model | verdict | confidence |
    # Handle various table formats with optional leading/trailing pipes
    verdict_pattern = re.compile(
        r"^\|\s*(\w+[-\w]*)\s*\|\s*([\w.-]+)\s*\|\s*(\w+(?:\s+\w+)?)\s*\|\s*(\d+)%\s*\|?\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in verdict_pattern.finditer(comment_body):
        provider, model, verdict, confidence = match.groups()
        # Skip header separator rows
        if provider.startswith("-"):
            continue
        data.provider_verdicts[provider] = {
            "model": model,
            "verdict": verdict.strip(),
            "confidence": int(confidence),
        }

    # Also try single-provider format
    single_verdict = re.search(r"Verdict:\s*\*?\*?(\w+)\*?\*?\s*@?\s*(\d+)?%?", comment_body)
    if single_verdict and not data.provider_verdicts:
        data.provider_verdicts["default"] = {
            "verdict": single_verdict.group(1),
            "confidence": int(single_verdict.group(2)) if single_verdict.group(2) else 0,
        }

    # Extract concerns
    concerns_match = re.search(
        r"### Concerns\s*\n([\s\S]*?)(?=###|##|$)", comment_body, re.IGNORECASE
    )
    if concerns_match:
        concerns_text = concerns_match.group(1).strip()
        # Split into individual concerns
        data.concerns = [
            c.strip().lstrip("- ").lstrip("* ")
            for c in concerns_text.split("\n")
            if c.strip() and not c.strip().startswith("#")
        ]

    # Extract low scores
    score_pattern = re.compile(r"(\w+):\s*(\d+)/10", re.IGNORECASE)
    for match in score_pattern.finditer(comment_body):
        category, score = match.groups()
        score_int = int(score)
        if score_int < 7:
            data.low_scores[category] = score_int

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

    # Extract sections
    section_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    sections: dict[str, str] = {}

    matches = list(section_pattern.finditer(issue_body))
    for i, match in enumerate(matches):
        section_name = match.group(1).strip().lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(issue_body)
        sections[section_name] = issue_body[start:end].strip()

    # Map to structured fields
    for key in ("why", "motivation", "summary"):
        if key in sections:
            data.why = sections[key]
            break

    for key in ("scope", "context", "background"):
        if key in sections:
            data.scope = sections[key]
            break

    for key in ("implementation notes", "notes", "implementation"):
        if key in sections:
            data.implementation_notes = sections[key]
            break

    # Extract tasks (checkboxes)
    task_section = sections.get("tasks", "")
    checkbox_pattern = re.compile(r"^\s*[-*+]\s*\[([ xX])\]\s*(.+)$", re.MULTILINE)
    for match in checkbox_pattern.finditer(task_section):
        task_text = match.group(2).strip()
        if task_text and len(task_text) > 3:  # Skip tiny fragments
            data.tasks.append(task_text)

    # Extract acceptance criteria
    ac_section = sections.get("acceptance criteria", sections.get("acceptance", ""))
    for match in checkbox_pattern.finditer(ac_section):
        criterion = match.group(2).strip()
        if criterion and len(criterion) > 3:
            data.acceptance_criteria.append(criterion)

    return data


def _get_llm_client() -> tuple[Any, str] | None:
    """Get LLM client with fallback."""
    try:
        from langchain_openai import ChatOpenAI

        from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL
    except ImportError:
        return None

    # Prefer OpenAI for complex multi-turn generation
    if os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("FOLLOWUP_MODEL", "gpt-4o")
        return ChatOpenAI(model=model, temperature=0.3, timeout=30), model

    # Fall back to GitHub Models
    if os.environ.get("GITHUB_TOKEN"):
        return (
            ChatOpenAI(
                model=DEFAULT_MODEL,
                base_url=GITHUB_MODELS_BASE_URL,
                api_key=os.environ["GITHUB_TOKEN"],
                temperature=0.3,
                timeout=30,
            ),
            DEFAULT_MODEL,
        )

    return None


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
    1. Analyze verification feedback + original issue to understand gaps
    2. Generate specific, actionable tasks
    3. Generate testable acceptance criteria
    4. Format the final issue
    """
    client_info = _get_llm_client() if use_llm else None

    if client_info and use_llm:
        client, model = client_info
        return _generate_with_llm(
            verification_data, original_issue, pr_number, codex_log, client, model
        )
    else:
        return _generate_without_llm(verification_data, original_issue, pr_number)


def _generate_with_llm(
    verification_data: VerificationData,
    original_issue: OriginalIssueData,
    pr_number: int,
    codex_log: str | None,
    client: Any,
    model: str,
) -> FollowupIssue:
    """Generate follow-up issue using multi-round LLM interaction."""

    # Round 1: Analyze verification feedback
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
    )

    analysis_response = _invoke_llm(analyze_prompt, client)
    analysis = _extract_json(analysis_response)

    # Round 2: Generate tasks
    tasks_prompt = GENERATE_TASKS_PROMPT.format(
        analysis_json=json.dumps(analysis, indent=2),
        original_tasks="\n".join(
            f"- [ ] {t}" for t in original_issue.tasks[:20]
        ),  # Limit for token budget
    )

    tasks_response = _invoke_llm(tasks_prompt, client)
    tasks_data = _extract_json(tasks_response)

    # Round 3: Generate acceptance criteria
    ac_prompt = GENERATE_ACCEPTANCE_CRITERIA_PROMPT.format(
        tasks_json=json.dumps(tasks_data.get("tasks", []), indent=2),
        unmet_criteria=json.dumps(analysis.get("unmet_criteria", []), indent=2),
    )

    ac_response = _invoke_llm(ac_prompt, client)
    ac_data = _extract_json(ac_response)

    # Round 4: Format final issue
    why_section = _build_why_section(verification_data, original_issue, pr_number)

    format_prompt = FORMAT_FOLLOWUP_ISSUE_PROMPT.format(
        pr_number=pr_number,
        original_issue_number=original_issue.number,
        verdict=_get_primary_verdict(verification_data),
        why_section=why_section,
        tasks_json=json.dumps(tasks_data.get("tasks", []), indent=2),
        acceptance_criteria_json=json.dumps(ac_data.get("acceptance_criteria", []), indent=2),
        deferred_tasks_json=json.dumps(tasks_data.get("deferred_tasks", []), indent=2),
        background_analysis=json.dumps(
            {
                "structural_issues": verification_data.structural_issues,
                "analysis": analysis,
            },
            indent=2,
        ),
    )

    issue_body = _invoke_llm(format_prompt, client)

    # Generate title
    focus_items = analysis.get("recommended_focus", [])
    title_focus = focus_items[0] if focus_items else "verification concerns"
    title = f"[Follow-up] {title_focus[:60]} (PR #{pr_number})"

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
