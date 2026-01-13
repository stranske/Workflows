#!/usr/bin/env python3
"""
Two-pass task validation: heuristic triage + LLM refinement.

This module ensures tasks are actionable and acceptance criteria are verifiable
by flagging questionable items and asking the LLM to refine them.

Run with:
    python scripts/langchain/task_validator.py --tasks "task1" "task2" --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants for heuristic detection
# ---------------------------------------------------------------------------

# Subjective words that need measurable context
SUBJECTIVE_WORDS = (
    "clean",
    "nice",
    "good",
    "better",
    "intuitive",
    "polished",
    "quality",
    "appropriate",
    "adequate",
    "sufficient",
    "proper",
    "properly",
    "correctly",
    "ensure",
)

# Words that indicate measurable verification
MEASURABLE_WORDS = (
    "test",
    "tests",
    "pass",
    "passes",
    "fail",
    "lint",
    "ci",
    "coverage",
    "exists",
    "returns",
    "outputs",
    "contains",
    "count",
    "number",
    "error",
    "errors",
)

# Human-only activity indicators
HUMAN_ACTIVITY_PATTERNS = (
    r"\b(train|training)\s+(staff|team|employees|personnel)\b",
    r"\b(conduct|hold|schedule)\s+(session|meeting|interview|review)\b",
    r"\b(obtain|gather|collect)\s+(feedback|input|approval)\b",
    r"\b(stakeholder|staff\s+member|employee)\b",
    r"\bpeer\s+review\b",
    r"\bmanual\s+review\b",
)

# Recursive expansion prefixes that indicate already-processed tasks
EXPANSION_PREFIXES = (
    "define scope for:",
    "implement focused slice for:",
    "validate focused slice for:",
    "define approach for:",
)

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "refine_tasks.md"

REFINEMENT_PROMPT = """
The following tasks/criteria were flagged as potentially problematic.
For each item, decide:

1. **KEEP** - If it's actually valid and actionable, output it unchanged
2. **IMPROVE** - Rewrite to be specific, actionable, and verifiable
3. **DROP** - If it's not a coding task (header, human activity, fragment)

Issue context:
{context}

Flagged items:
{flagged_items}

For each item, respond with EXACTLY one line in this format:
- KEEP: <original task unchanged>
- IMPROVE: <rewritten task>
- DROP: <brief reason>

A valid task MUST be something a coding agent can complete:
- Creates, modifies, or deletes code/config/docs
- Has a verifiable outcome (tests pass, file exists, lint clean)
- NOT: human activities, meetings, reviews, subjective quality checks

Process each item in order. Do not skip any items.
""".strip()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class TaskOutcome(str, Enum):
    """Possible outcomes for a flagged task."""

    KEPT = "kept"
    IMPROVED = "improved"
    DROPPED = "dropped"
    UNPROCESSED = "unprocessed"  # LLM didn't respond; kept original


@dataclass
class TaskFate:
    """Tracks what happened to a task through validation."""

    original: str
    outcome: TaskOutcome
    result: str | None  # None only for dropped
    reason: str | None = None  # Why dropped/improved/unprocessed
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "outcome": self.outcome.value,
            "result": self.result,
            "reason": self.reason,
            "warnings": self.warnings,
        }


@dataclass
class ValidationResult:
    """Complete result of task validation."""

    tasks: list[str]
    fates: list[TaskFate]
    audit_summary: str
    provider_used: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": self.tasks,
            "fates": [f.to_dict() for f in self.fates],
            "audit_summary": self.audit_summary,
            "provider_used": self.provider_used,
        }


# ---------------------------------------------------------------------------
# Heuristic detection functions
# ---------------------------------------------------------------------------


def _has_subjective_without_measurable(task: str) -> bool:
    """Check if task has subjective language without measurable verification."""
    lowered = task.lower()
    has_subjective = any(word in lowered for word in SUBJECTIVE_WORDS)
    has_measurable = any(word in lowered for word in MEASURABLE_WORDS)
    return has_subjective and not has_measurable


def _looks_like_human_activity(task: str) -> bool:
    """Check if task describes human-only activity."""
    return any(re.search(pattern, task, re.IGNORECASE) for pattern in HUMAN_ACTIVITY_PATTERNS)


def _has_expansion_prefix(task: str) -> bool:
    """Check if task has recursive expansion prefix."""
    lowered = task.lower().strip()
    return any(lowered.startswith(prefix) for prefix in EXPANSION_PREFIXES)


def _is_punctuation_fragment(task: str) -> bool:
    """Check if task is just punctuation or whitespace fragments."""
    cleaned = re.sub(r"[\s,;:.!?()[\]{}\"'`]+", "", task)
    return len(cleaned) < 3


def _is_header_syntax(task: str) -> bool:
    """Check if task is actually a markdown header."""
    return bool(re.match(r"^\s*#{1,6}\s+", task.strip()))


def _is_too_short(task: str) -> bool:
    """Check if task is too short to be meaningful."""
    words = task.split()
    return len(words) < 4


# Warning signal registry
WARNING_SIGNALS: dict[str, Any] = {
    "too_short": _is_too_short,
    "is_header": _is_header_syntax,
    "subjective_language": _has_subjective_without_measurable,
    "human_activity": _looks_like_human_activity,
    "recursive_prefix": _has_expansion_prefix,
    "punctuation_fragment": _is_punctuation_fragment,
}


# ---------------------------------------------------------------------------
# Triage functions
# ---------------------------------------------------------------------------


def triage_tasks(tasks: list[str]) -> dict[str, list[Any]]:
    """
    Separate tasks into clean vs flagged for review.

    Args:
        tasks: List of task strings to triage

    Returns:
        Dictionary with "clean" (list[str]) and "flagged" (list[dict]) keys
    """
    clean: list[str] = []
    flagged: list[dict[str, Any]] = []

    for task in tasks:
        if not task or not task.strip():
            continue

        warnings = [name for name, check in WARNING_SIGNALS.items() if check(task)]

        if warnings:
            flagged.append({"task": task, "warnings": warnings})
        else:
            clean.append(task)

    return {"clean": clean, "flagged": flagged}


# ---------------------------------------------------------------------------
# LLM client utilities
# ---------------------------------------------------------------------------


def _get_llm_client(force_openai: bool = False) -> tuple[object, str] | None:
    """Get LLM client, trying GitHub Models first, then OpenAI."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")

    if not github_token and not openai_token:
        return None

    try:
        from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL
    except ImportError:
        DEFAULT_MODEL = "gpt-4o-mini"
        GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"

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


def _is_github_models_auth_error(exc: Exception) -> bool:
    """Check if exception is a GitHub Models authentication error."""
    exc_str = str(exc).lower()
    return "401" in exc_str and "models" in exc_str


def _load_refinement_prompt() -> str:
    """Load refinement prompt from file or use default."""
    if PROMPT_PATH.is_file():
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    return REFINEMENT_PROMPT


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

# Pattern to match KEEP/IMPROVE/DROP responses
REFINEMENT_PATTERN = re.compile(r"^\s*[-*]?\s*(KEEP|IMPROVE|DROP)\s*:\s*(.+)$", re.IGNORECASE)


def _parse_refinement_response(response: str, flagged: list[dict[str, Any]]) -> list[TaskFate]:
    """
    Parse LLM refinement response into TaskFate objects.

    Falls back to keeping original if parsing fails for any item.
    """
    fates: list[TaskFate] = []
    response_lines = [line.strip() for line in response.splitlines() if line.strip()]

    # Track which flagged items we've processed
    processed_indices: set[int] = set()

    # Try to match response lines to flagged items in order
    line_idx = 0
    for item_idx, item in enumerate(flagged):
        task = item["task"]
        warnings = item.get("warnings", [])

        # Look for a matching response line
        fate: TaskFate | None = None

        while line_idx < len(response_lines):
            line = response_lines[line_idx]
            match = REFINEMENT_PATTERN.match(line)

            if match:
                action = match.group(1).upper()
                content = match.group(2).strip()

                if action == "KEEP":
                    fate = TaskFate(
                        original=task,
                        outcome=TaskOutcome.KEPT,
                        result=task,  # Keep original text
                        reason="LLM confirmed valid",
                        warnings=warnings,
                    )
                elif action == "IMPROVE":
                    fate = TaskFate(
                        original=task,
                        outcome=TaskOutcome.IMPROVED,
                        result=content,
                        reason="LLM improved for actionability",
                        warnings=warnings,
                    )
                elif action == "DROP":
                    fate = TaskFate(
                        original=task,
                        outcome=TaskOutcome.DROPPED,
                        result=None,
                        reason=content,
                        warnings=warnings,
                    )

                line_idx += 1
                processed_indices.add(item_idx)
                break
            else:
                # Skip non-matching lines
                line_idx += 1

        # If no fate assigned, keep original (fallback)
        if fate is None:
            fate = TaskFate(
                original=task,
                outcome=TaskOutcome.UNPROCESSED,
                result=task,
                reason="LLM did not respond; keeping original",
                warnings=warnings,
            )

        fates.append(fate)

    return fates


# ---------------------------------------------------------------------------
# Main refinement function
# ---------------------------------------------------------------------------


def refine_flagged_tasks(
    flagged: list[dict[str, Any]], context: str = ""
) -> tuple[list[str], list[TaskFate], str | None]:
    """
    Send flagged tasks to LLM for refinement decision.

    Args:
        flagged: List of {"task": str, "warnings": list[str]} dicts
        context: Optional issue context for LLM

    Returns:
        Tuple of (refined_tasks, fates, provider_used)
    """
    if not flagged:
        return [], [], None

    # Format flagged items for prompt
    flagged_lines: list[str] = []
    for i, item in enumerate(flagged, 1):
        task = item["task"]
        warnings = item.get("warnings", [])
        warning_text = f" (warnings: {', '.join(warnings)})" if warnings else ""
        flagged_lines.append(f"{i}. {task}{warning_text}")

    flagged_text = "\n".join(flagged_lines)

    # Try to get LLM client
    client_info = _get_llm_client()
    if not client_info:
        # No LLM available - return originals with unprocessed fates
        fates = [
            TaskFate(
                original=item["task"],
                outcome=TaskOutcome.UNPROCESSED,
                result=item["task"],
                reason="No LLM available; keeping original",
                warnings=item.get("warnings", []),
            )
            for item in flagged
        ]
        tasks = [f.result for f in fates if f.result]
        return tasks, fates, None

    client, provider = client_info

    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError:
        # Fallback without LangChain
        fates = [
            TaskFate(
                original=item["task"],
                outcome=TaskOutcome.UNPROCESSED,
                result=item["task"],
                reason="LangChain unavailable; keeping original",
                warnings=item.get("warnings", []),
            )
            for item in flagged
        ]
        tasks = [f.result for f in fates if f.result]
        return tasks, fates, None

    # Build and invoke prompt
    prompt_template = _load_refinement_prompt()
    template = ChatPromptTemplate.from_template(prompt_template)
    chain = template | client

    try:
        response = chain.invoke({"flagged_items": flagged_text, "context": context or "None"})
    except Exception as e:
        # If GitHub Models fails, try OpenAI
        if provider == "github-models" and _is_github_models_auth_error(e):
            fallback_info = _get_llm_client(force_openai=True)
            if fallback_info:
                client, provider = fallback_info
                chain = template | client
                response = chain.invoke(
                    {"flagged_items": flagged_text, "context": context or "None"}
                )
            else:
                raise
        else:
            raise

    # Parse response
    content = getattr(response, "content", None) or str(response)
    fates = _parse_refinement_response(content, flagged)

    # Extract tasks (non-None results)
    tasks = [f.result for f in fates if f.result is not None]

    return tasks, fates, provider


# ---------------------------------------------------------------------------
# Audit and merge functions
# ---------------------------------------------------------------------------


def validate_no_items_lost(
    original_count: int,
    result_count: int,
    dropped_count: int,
) -> None:
    """
    Raise ValueError if items disappeared without explicit DROP.

    Args:
        original_count: Number of input items
        result_count: Number of items in final output
        dropped_count: Number of items explicitly dropped
    """
    accounted = result_count + dropped_count
    if accounted < original_count:
        missing = original_count - accounted
        raise ValueError(
            f"Item loss detected: {original_count} input, {accounted} accounted for "
            f"({result_count} kept/improved, {dropped_count} dropped). "
            f"{missing} items unaccounted for."
        )


def merge_with_audit(
    clean: list[str],
    refined: list[str],
    fates: list[TaskFate],
    original_count: int,
) -> tuple[list[str], str]:
    """
    Merge clean and refined tasks, returning audit summary.

    Args:
        clean: Tasks that passed heuristic checks
        refined: Tasks from LLM refinement
        fates: TaskFate objects from refinement
        original_count: Original number of input tasks

    Returns:
        Tuple of (final_tasks, audit_summary)
    """
    final = clean + refined

    # Count outcomes
    dropped = [f for f in fates if f.outcome == TaskOutcome.DROPPED]
    improved = [f for f in fates if f.outcome == TaskOutcome.IMPROVED]
    kept = [f for f in fates if f.outcome == TaskOutcome.KEPT]
    unprocessed = [f for f in fates if f.outcome == TaskOutcome.UNPROCESSED]

    # Validate no silent loss
    # Clean items + all fates should equal original count
    accounted = len(clean) + len(fates)
    if accounted != original_count:
        raise ValueError(
            f"Audit mismatch: {original_count} input items, "
            f"but {len(clean)} clean + {len(fates)} fates = {accounted}"
        )

    # Validate no result loss
    validate_no_items_lost(
        original_count=original_count,
        result_count=len(final),
        dropped_count=len(dropped),
    )

    audit = (
        f"Task validation: {original_count} input → {len(final)} output. "
        f"Clean: {len(clean)}, Kept: {len(kept)}, Improved: {len(improved)}, "
        f"Dropped: {len(dropped)}, Fallback: {len(unprocessed)}"
    )

    return final, audit


# ---------------------------------------------------------------------------
# Main validation function
# ---------------------------------------------------------------------------


def validate_tasks(
    tasks: list[str],
    context: str = "",
    *,
    use_llm: bool = True,
) -> ValidationResult:
    """
    Validate tasks using two-pass heuristic + LLM approach.

    Args:
        tasks: List of task strings to validate
        context: Optional issue context for LLM refinement
        use_llm: Whether to use LLM for refinement (default True)

    Returns:
        ValidationResult with final tasks and full audit trail
    """
    if not tasks:
        return ValidationResult(
            tasks=[],
            fates=[],
            audit_summary="No tasks to validate",
            provider_used=None,
        )

    original_count = len(tasks)

    # Pass 1: Heuristic triage
    triage_result = triage_tasks(tasks)
    clean = triage_result["clean"]
    flagged = triage_result["flagged"]

    # If nothing flagged, return clean tasks
    if not flagged:
        return ValidationResult(
            tasks=clean,
            fates=[],
            audit_summary=f"Task validation: {original_count} input → {len(clean)} output. All clean.",
            provider_used=None,
        )

    # Pass 2: LLM refinement (if enabled)
    if use_llm:
        refined, fates, provider = refine_flagged_tasks(flagged, context)
    else:
        # No LLM - keep all flagged items as unprocessed
        fates = [
            TaskFate(
                original=item["task"],
                outcome=TaskOutcome.UNPROCESSED,
                result=item["task"],
                reason="LLM disabled; keeping original",
                warnings=item.get("warnings", []),
            )
            for item in flagged
        ]
        refined = [f.result for f in fates if f.result]
        provider = None

    # Merge and audit
    final_tasks, audit = merge_with_audit(clean, refined, fates, original_count)

    return ValidationResult(
        tasks=final_tasks,
        fates=fates,
        audit_summary=audit,
        provider_used=provider,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate tasks for actionability.")
    parser.add_argument("--tasks", nargs="+", help="Tasks to validate.")
    parser.add_argument("--context", default="", help="Issue context for refinement.")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM refinement.")
    args = parser.parse_args()

    tasks = args.tasks or []
    result = validate_tasks(tasks, args.context, use_llm=not args.no_llm)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Audit: {result.audit_summary}")
        print("\nFinal tasks:")
        for task in result.tasks:
            print(f"  - {task}")
        if result.fates:
            print("\nFates:")
            for fate in result.fates:
                print(f"  [{fate.outcome.value}] {fate.original[:50]}...")
                if fate.reason:
                    print(f"    Reason: {fate.reason}")


if __name__ == "__main__":
    main()
