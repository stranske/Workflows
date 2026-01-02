#!/usr/bin/env python3
"""
Analyze Codex Session CLI

Command-line interface for analyzing Codex session output to determine
task completion status. Designed to be called from GitHub Actions workflows.

Usage:
    python scripts/analyze_codex_session.py \
        --session-file codex-session-123.jsonl \
        --tasks "Fix bug" "Add tests" "Update docs" \
        --output json

    # Or with PR body file containing checkboxes
    python scripts/analyze_codex_session.py \
        --session-file codex-session-123.jsonl \
        --pr-body-file pr_body.md \
        --output github-actions

Exit codes:
    0 - Analysis completed successfully
    1 - Error during analysis
    2 - No session file found
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.codex_session_analyzer import AnalysisResult, analyze_session

logger = logging.getLogger(__name__)


def extract_tasks_from_pr_body(pr_body: str) -> list[str]:
    """
    Extract task descriptions from PR body checkboxes.

    Looks for patterns like:
    - [ ] Task description
    - [x] Completed task

    Returns only unchecked tasks (the ones we're tracking).
    """
    tasks = []

    # Match both checked and unchecked boxes to get all tasks
    # Pattern: - [ ] or - [x] followed by task text
    checkbox_pattern = re.compile(r"^[\s]*-\s*\[([ xX])\]\s*(.+)$", re.MULTILINE)

    for match in checkbox_pattern.finditer(pr_body):
        checked = match.group(1).lower() == "x"
        task_text = match.group(2).strip()

        # Only track unchecked tasks
        if not checked and task_text:
            tasks.append(task_text)

    return tasks


def extract_all_tasks_from_pr_body(pr_body: str) -> dict[str, bool]:
    """
    Extract all tasks with their current status.

    Returns:
        Dict mapping task text to checked status
    """
    tasks = {}
    checkbox_pattern = re.compile(r"^[\s]*-\s*\[([ xX])\]\s*(.+)$", re.MULTILINE)

    for match in checkbox_pattern.finditer(pr_body):
        checked = match.group(1).lower() == "x"
        task_text = match.group(2).strip()
        if task_text:
            tasks[task_text] = checked

    return tasks


def update_pr_body_checkboxes(pr_body: str, completed_tasks: list[str]) -> str:
    """
    Update PR body to check off completed tasks.

    Args:
        pr_body: Original PR body text
        completed_tasks: List of task descriptions to mark complete

    Returns:
        Updated PR body with checkboxes updated
    """
    updated_body = pr_body

    for task in completed_tasks:
        # Escape special regex characters in task
        escaped_task = re.escape(task)

        # Pattern to match unchecked checkbox with this task
        pattern = re.compile(
            rf"^([\s]*-\s*)\[ \](\s*){escaped_task}",
            re.MULTILINE,
        )

        # Replace with checked version
        updated_body = pattern.sub(rf"\1[x]\2{task}", updated_body)

    return updated_body


def output_github_actions(result: AnalysisResult) -> None:
    """Output results in GitHub Actions format."""
    github_output = os.environ.get("GITHUB_OUTPUT", "")

    # Print notices for visibility in logs
    print(f"::notice::Analysis completed with {result.completion.provider_used}")
    print(f"::notice::Confidence: {result.completion.confidence:.0%}")

    if result.completion.completed_tasks:
        print(f"::notice::Completed tasks: {len(result.completion.completed_tasks)}")
        for task in result.completion.completed_tasks:
            print(f"::notice::  ✓ {task[:80]}")

    if result.completion.in_progress_tasks:
        print(f"::notice::In progress: {len(result.completion.in_progress_tasks)}")

    if result.completion.blocked_tasks:
        print(f"::warning::Blocked tasks: {len(result.completion.blocked_tasks)}")
        for task in result.completion.blocked_tasks:
            print(f"::warning::  ✗ {task[:80]}")

    # Write to GITHUB_OUTPUT if available
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"provider={result.completion.provider_used}\n")
            f.write(f"confidence={result.completion.confidence}\n")
            f.write(f"completed-count={len(result.completion.completed_tasks)}\n")
            f.write(f"in-progress-count={len(result.completion.in_progress_tasks)}\n")
            f.write(f"blocked-count={len(result.completion.blocked_tasks)}\n")
            f.write(f"has-completions={str(result.has_completions).lower()}\n")
            f.write(f"has-progress={str(result.has_progress).lower()}\n")
            f.write(f"is-stalled={str(result.is_stalled).lower()}\n")

            # Encode completed tasks as JSON for downstream use
            completed_json = json.dumps(result.completion.completed_tasks)
            f.write(f"completed-tasks={completed_json}\n")


def output_json(result: AnalysisResult, pretty: bool = False) -> None:
    """Output results as JSON."""
    data = {
        "provider": result.completion.provider_used,
        "confidence": result.completion.confidence,
        "completed_tasks": result.completion.completed_tasks,
        "in_progress_tasks": result.completion.in_progress_tasks,
        "blocked_tasks": result.completion.blocked_tasks,
        "reasoning": result.completion.reasoning,
        "data_source": result.data_source,
        "input_length": result.input_length,
        "analysis_text_length": result.analysis_text_length,
    }

    if result.session:
        data["session"] = {
            "event_count": result.session.raw_event_count,
            "message_count": len(result.session.agent_messages),
            "command_count": len(result.session.commands),
            "file_change_count": len(result.session.file_changes),
            "todo_count": len(result.session.todo_items),
        }

    if pretty:
        print(json.dumps(data, indent=2))
    else:
        print(json.dumps(data))


def output_markdown(result: AnalysisResult) -> None:
    """Output results as markdown summary."""
    print(result.get_summary())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze Codex session output for task completion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--session-file",
        required=True,
        help="Path to Codex session JSONL or summary file",
    )

    parser.add_argument(
        "--tasks",
        nargs="*",
        help="Task descriptions to track (alternative to --pr-body-file)",
    )

    parser.add_argument(
        "--pr-body-file",
        help="Path to file containing PR body with checkboxes",
    )

    parser.add_argument(
        "--pr-body",
        help="PR body text directly (alternative to --pr-body-file)",
    )

    parser.add_argument(
        "--context",
        help="Additional context for analysis",
    )

    parser.add_argument(
        "--output",
        choices=["json", "json-pretty", "markdown", "github-actions"],
        default="json",
        help="Output format (default: json)",
    )

    parser.add_argument(
        "--update-pr-body",
        action="store_true",
        help="Output updated PR body with completed checkboxes",
    )

    parser.add_argument(
        "--updated-body-file",
        help="Write updated PR body to this file",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Check session file exists
    session_path = Path(args.session_file)
    if not session_path.exists():
        logger.error(f"Session file not found: {args.session_file}")
        return 2

    # Get session content
    session_content = session_path.read_text()

    # Get tasks
    tasks = []
    pr_body = None

    if args.tasks:
        tasks = args.tasks
    elif args.pr_body_file:
        pr_body = Path(args.pr_body_file).read_text()
        tasks = extract_tasks_from_pr_body(pr_body)
    elif args.pr_body:
        pr_body = args.pr_body
        tasks = extract_tasks_from_pr_body(pr_body)
    else:
        logger.error("Must provide --tasks, --pr-body-file, or --pr-body")
        return 1

    if not tasks:
        logger.warning("No tasks found to track")
        # Still run analysis but with empty task list

    logger.info(f"Analyzing session ({len(session_content)} bytes) with {len(tasks)} tasks")

    # Run analysis
    try:
        result = analyze_session(
            content=session_content,
            tasks=tasks,
            context=args.context,
        )
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return 1

    # Output results
    if args.output == "github-actions":
        output_github_actions(result)
    elif args.output == "json":
        output_json(result)
    elif args.output == "json-pretty":
        output_json(result, pretty=True)
    elif args.output == "markdown":
        output_markdown(result)

    # Update PR body if requested
    if args.update_pr_body and pr_body and result.completion.completed_tasks:
        updated_body = update_pr_body_checkboxes(pr_body, result.completion.completed_tasks)

        if args.updated_body_file:
            Path(args.updated_body_file).write_text(updated_body)
            logger.info(f"Updated PR body written to {args.updated_body_file}")
        else:
            print("\n--- UPDATED PR BODY ---")
            print(updated_body)

    return 0


if __name__ == "__main__":
    sys.exit(main())
