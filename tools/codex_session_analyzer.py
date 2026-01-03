"""
Codex Session Analyzer

Analyzes Codex session output to determine task completion status.
Supports multiple data source options:
- Option A: Final summary only (--output-last-message)
- Option B: Full JSONL stream (--json)
- Option B subset: Filtered to high-value events only

Usage:
    from tools.codex_session_analyzer import analyze_session, AnalysisResult

    # From JSONL
    result = analyze_session(jsonl_content, tasks, data_source="jsonl")

    # From summary
    result = analyze_session(summary_text, tasks, data_source="summary")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from tools.codex_jsonl_parser import CodexSession, parse_codex_jsonl
from tools.llm_provider import CompletionAnalysis, get_llm_provider

logger = logging.getLogger(__name__)

DataSource = Literal["jsonl", "jsonl_filtered", "summary", "auto"]


@dataclass
class AnalysisResult:
    """Complete analysis result with metadata."""

    # Core analysis
    completion: CompletionAnalysis

    # Session metadata (if JSONL was parsed)
    session: CodexSession | None = None

    # Data source used
    data_source: str = "unknown"

    # Statistics
    input_length: int = 0
    analysis_text_length: int = 0

    @property
    def has_completions(self) -> bool:
        """Check if any tasks were marked complete."""
        return len(self.completion.completed_tasks) > 0

    @property
    def has_progress(self) -> bool:
        """Check if any work was done (completed or in progress)."""
        return (
            len(self.completion.completed_tasks) > 0 or len(self.completion.in_progress_tasks) > 0
        )

    @property
    def is_stalled(self) -> bool:
        """Check if session appears stalled (no progress, maybe blocked)."""
        return not self.has_progress and len(self.completion.blocked_tasks) > 0

    def get_checkbox_updates(self) -> dict[str, bool]:
        """
        Get mapping of task -> checked status for PR body update.

        Returns:
            Dict mapping task text to checkbox state (True = checked)
        """
        updates = {}
        for task in self.completion.completed_tasks:
            updates[task] = True
        # Don't uncheck anything - only mark completions
        return updates

    def get_summary(self) -> str:
        """Get human-readable summary of the analysis."""
        lines = [
            f"**Analysis Summary** (confidence: {self.completion.confidence:.0%})",
            f"- Provider: {self.completion.provider_used}",
            f"- Data source: {self.data_source}",
            "",
        ]

        if self.completion.completed_tasks:
            lines.append("**Completed:**")
            for task in self.completion.completed_tasks:
                lines.append(f"- ✓ {task}")
            lines.append("")

        if self.completion.in_progress_tasks:
            lines.append("**In Progress:**")
            for task in self.completion.in_progress_tasks:
                lines.append(f"- → {task}")
            lines.append("")

        if self.completion.blocked_tasks:
            lines.append("**Blocked:**")
            for task in self.completion.blocked_tasks:
                lines.append(f"- ✗ {task}")
            lines.append("")

        if self.completion.reasoning:
            lines.append(f"**Analysis:** {self.completion.reasoning}")

        return "\n".join(lines)


def analyze_session(
    content: str,
    tasks: list[str],
    data_source: DataSource = "auto",
    include_reasoning: bool = True,
    context: str | None = None,
    force_provider: str | None = None,
) -> AnalysisResult:
    """
    Analyze Codex session output to determine task completion.

    Args:
        content: Session output (JSONL or summary text)
        tasks: List of task descriptions from PR checkboxes
        data_source: How to interpret content:
            - "jsonl": Parse as full JSONL stream
            - "jsonl_filtered": Parse JSONL, use only agent_message + reasoning
            - "summary": Treat as plain text summary
            - "auto": Auto-detect based on content
        include_reasoning: Include reasoning summaries in analysis (for JSONL)
        context: Additional context (PR description, etc.)
        force_provider: Force use of a specific provider (for testing).
            Options: "github-models", "openai", "regex-fallback"

    Returns:
        AnalysisResult with completion status and metadata
    """
    # Auto-detect data source
    if data_source == "auto":
        data_source = _detect_data_source(content)
        logger.info(f"Auto-detected data source: {data_source}")

    session = None
    analysis_text = content

    # Parse JSONL if applicable
    if data_source in ("jsonl", "jsonl_filtered"):
        try:
            session = parse_codex_jsonl(content)
            analysis_text = session.get_analysis_text(
                include_reasoning=(data_source == "jsonl" and include_reasoning)
            )
            logger.info(
                f"Parsed JSONL: {session.raw_event_count} events, "
                f"{len(session.agent_messages)} messages, "
                f"{len(session.commands)} commands"
            )
        except Exception as e:
            logger.warning(f"Failed to parse as JSONL, falling back to summary: {e}")
            data_source = "summary"
            analysis_text = content

    # Get LLM provider and analyze
    provider = get_llm_provider(force_provider=force_provider)

    try:
        completion = provider.analyze_completion(
            session_output=analysis_text,
            tasks=tasks,
            context=context,
        )
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        # Return empty result on failure
        completion = CompletionAnalysis(
            completed_tasks=[],
            in_progress_tasks=[],
            blocked_tasks=[],
            confidence=0.0,
            reasoning=f"Analysis failed: {e}",
            provider_used="error",
        )

    return AnalysisResult(
        completion=completion,
        session=session,
        data_source=data_source,
        input_length=len(content),
        analysis_text_length=len(analysis_text),
    )


def _detect_data_source(content: str) -> DataSource:
    """
    Auto-detect whether content is JSONL or plain text.

    Args:
        content: Raw content to analyze

    Returns:
        Detected data source type
    """
    # Check first few lines for JSON structure
    lines = content.strip().split("\n")[:5]
    json_lines = 0

    for line in lines:
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            json_lines += 1

    # If most lines look like JSON, treat as JSONL
    if json_lines >= len(lines) * 0.5:
        return "jsonl"

    return "summary"


def analyze_from_files(
    session_file: str,
    tasks_file: str | None = None,
    tasks: list[str] | None = None,
) -> AnalysisResult:
    """
    Convenience function to analyze from file paths.

    Args:
        session_file: Path to session output file
        tasks_file: Path to file with tasks (one per line)
        tasks: List of tasks (alternative to tasks_file)

    Returns:
        AnalysisResult
    """
    from pathlib import Path

    content = Path(session_file).read_text()

    if tasks is None:
        if tasks_file:
            task_text = Path(tasks_file).read_text()
            tasks = [t.strip() for t in task_text.split("\n") if t.strip()]
        else:
            raise ValueError("Either tasks or tasks_file must be provided")

    return analyze_session(content, tasks)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    # Example usage
    sample_tasks = [
        "Fix test failures in calculator module",
        "Update documentation",
        "Add type hints",
    ]

    sample_jsonl = """
{"type": "thread.started", "thread_id": "abc123"}
{"type": "turn.started", "turn_id": "turn1"}
{"type": "item.completed", "item_type": "agent_message", "content": "I've completed fixing the test failures in the calculator module. The tests now pass. I'm starting work on the documentation updates."}
{"type": "item.completed", "item_type": "command_execution", "command": "pytest tests/", "exit_code": 0}
{"type": "item.completed", "item_type": "file_change", "path": "src/calc.py", "change_type": "modified"}
{"type": "turn.completed", "turn_id": "turn1", "token_usage": {"input_tokens": 1000, "output_tokens": 500}}
"""

    print("Analyzing sample session...")
    result = analyze_session(sample_jsonl, sample_tasks)
    print(result.get_summary())
