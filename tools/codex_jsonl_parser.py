"""
Codex JSONL Event Parser

Parses the JSONL event stream from `codex exec --json` for task completion analysis.

Event types supported:
- thread.started / turn.started / turn.completed / turn.failed
- item.started / item.updated / item.completed
- Item types: agent_message, reasoning, command_execution, file_change, todo_list

Usage:
    from tools.codex_jsonl_parser import parse_codex_jsonl, CodexSession

    session = parse_codex_jsonl(jsonl_content)
    print(session.agent_messages)
    print(session.file_changes)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CommandExecution:
    """Represents a shell command executed by Codex."""

    command: str
    exit_code: int
    output: str
    duration_seconds: float | None = None


@dataclass
class FileChange:
    """Represents a file modification by Codex."""

    path: str
    change_type: str  # added, modified, deleted
    content_preview: str | None = None


@dataclass
class TodoItem:
    """Represents a task in Codex's todo list."""

    task: str
    status: str  # completed, in_progress, not_started, blocked


@dataclass
class TurnInfo:
    """Information about a conversation turn."""

    turn_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    completed: bool = False
    failed: bool = False
    error: str | None = None


@dataclass
class CodexSession:
    """Parsed Codex session data from JSONL events."""

    # Thread info
    thread_id: str | None = None

    # Turns
    turns: list[TurnInfo] = field(default_factory=list)

    # High-value content for analysis
    agent_messages: list[str] = field(default_factory=list)
    reasoning_summaries: list[str] = field(default_factory=list)

    # Concrete work evidence
    commands: list[CommandExecution] = field(default_factory=list)
    file_changes: list[FileChange] = field(default_factory=list)

    # Direct task mapping (if available)
    todo_items: list[TodoItem] = field(default_factory=list)

    # Raw events (for debugging)
    raw_event_count: int = 0
    parse_errors: list[str] = field(default_factory=list)

    @property
    def total_input_tokens(self) -> int:
        return sum(t.input_tokens for t in self.turns)

    @property
    def total_output_tokens(self) -> int:
        return sum(t.output_tokens for t in self.turns)

    @property
    def successful_commands(self) -> list[CommandExecution]:
        return [c for c in self.commands if c.exit_code == 0]

    @property
    def failed_commands(self) -> list[CommandExecution]:
        return [c for c in self.commands if c.exit_code != 0]

    @property
    def completed_todos(self) -> list[TodoItem]:
        return [t for t in self.todo_items if t.status == "completed"]

    def get_analysis_text(self, include_reasoning: bool = True, max_length: int = 7000) -> str:
        """
        Get consolidated text suitable for LLM analysis.

        This method builds a comprehensive view of the session by including:
        1. Agent messages (highest signal)
        2. Reasoning summaries (understanding intent)
        3. Todo list (direct task mapping)
        4. File changes with content previews (concrete evidence)
        5. Command outputs (evidence of work done)

        If no agent messages are present (common in some Codex modes),
        it falls back to extracting evidence from commands and file changes.

        Args:
            include_reasoning: Whether to include reasoning summaries
            max_length: Target max length for the analysis text (to fit LLM context)

        Returns:
            Formatted text with key session information
        """
        sections = []
        remaining_budget = max_length

        def add_section(title: str, content: list[str], budget_per_item: int = 500) -> int:
            """Add a section and return characters used."""
            if not content:
                return 0
            section_text = f"## {title}\n" + "\n".join(c[:budget_per_item] for c in content) + "\n"
            sections.append(section_text)
            return len(section_text)

        # Agent messages (highest signal)
        if self.agent_messages:
            used = add_section("Agent Messages", self.agent_messages, budget_per_item=2000)
            remaining_budget -= used

        # Reasoning (if requested) - important context
        if include_reasoning and self.reasoning_summaries:
            used = add_section("Reasoning Summaries", self.reasoning_summaries, budget_per_item=800)
            remaining_budget -= used

        # Todo list (direct task mapping)
        if self.todo_items:
            todo_lines = []
            for item in self.todo_items:
                status_emoji = {
                    "completed": "✓",
                    "in_progress": "→",
                    "blocked": "✗",
                    "not_started": "○",
                }.get(item.status, "?")
                todo_lines.append(f"{status_emoji} {item.task}")
            used = add_section("Todo List", todo_lines, budget_per_item=200)
            remaining_budget -= used

        # File changes with content previews (concrete evidence)
        if self.file_changes:
            file_lines = []
            for fc in self.file_changes:
                line = f"- {fc.change_type}: {fc.path}"
                if fc.content_preview:
                    # Include truncated content preview for context
                    preview = fc.content_preview[:300].replace("\n", " ")
                    line += f"\n  Preview: {preview}..."
                file_lines.append(line)
            used = add_section("Files Modified", file_lines, budget_per_item=500)
            remaining_budget -= used

        # Command outputs (evidence of work done) - CRITICAL for sessions without agent_messages
        if self.commands:
            cmd_section = []
            cmd_section.append(
                f"Total: {len(self.commands)} | Successful: {len(self.successful_commands)} | Failed: {len(self.failed_commands)}"
            )

            # Include outputs from recent successful commands (shows actual work)
            meaningful_commands = [
                c
                for c in self.successful_commands
                if c.output
                and len(c.output) > 20
                and not c.command.startswith(("cd ", "ls ", "pwd", "echo "))
            ]

            if meaningful_commands:
                cmd_section.append("\n### Recent Command Outputs (evidence of work):")
                # Take last 5 meaningful commands
                for cmd in meaningful_commands[-5:]:
                    cmd_section.append(f"\n$ {cmd.command[:100]}")
                    # Truncate output but include enough to show what was done
                    output_preview = cmd.output[:600].strip()
                    if output_preview:
                        cmd_section.append(output_preview)

            if self.failed_commands:
                cmd_section.append("\n### Failed Commands:")
                for cmd in self.failed_commands[:3]:
                    cmd_section.append(f"- {cmd.command[:100]} (exit {cmd.exit_code})")
                    if cmd.output:
                        cmd_section.append(f"  Error: {cmd.output[:200]}")

            used = add_section("Commands Executed", cmd_section, budget_per_item=800)
            remaining_budget -= used

        # FALLBACK: If we have very little text but evidence of work, synthesize a summary
        result = "\n".join(sections)
        if len(result) < 200 and (self.file_changes or self.commands):
            fallback = self._synthesize_work_evidence_summary()
            if fallback:
                result = fallback + "\n\n" + result

        return result

    def _synthesize_work_evidence_summary(self) -> str:
        """
        Synthesize a work summary when agent messages are missing.

        This is a fallback that extracts evidence from file changes and
        command patterns to give the LLM something to analyze.
        """
        summary_parts = ["## Work Evidence Summary (synthesized from session data)"]

        if self.file_changes:
            summary_parts.append(f"\n**{len(self.file_changes)} files were modified:**")
            for fc in self.file_changes:
                path_parts = Path(fc.path).parts
                # Extract meaningful file name context
                context = "/".join(path_parts[-3:]) if len(path_parts) > 2 else fc.path
                summary_parts.append(f"- {fc.change_type}: {context}")

        if self.commands:
            # Categorize commands to understand what was done
            test_cmds = [
                c for c in self.commands if "pytest" in c.command or "test" in c.command.lower()
            ]
            edit_cmds = [
                c
                for c in self.commands
                if any(x in c.command for x in ["sed", "cat", "echo >", "vim", "nano"])
            ]
            grep_cmds = [c for c in self.commands if "grep" in c.command or "rg" in c.command]

            if test_cmds:
                passed = sum(1 for c in test_cmds if c.exit_code == 0)
                summary_parts.append(
                    f"\n**Testing:** {len(test_cmds)} test commands run, {passed} successful"
                )

            if edit_cmds:
                summary_parts.append(f"\n**File editing:** {len(edit_cmds)} edit commands executed")

            if grep_cmds:
                summary_parts.append(
                    f"\n**Code exploration:** {len(grep_cmds)} search commands used"
                )

            # Include actual test output if available
            for cmd in test_cmds:
                if cmd.exit_code == 0 and cmd.output:
                    # Extract test summary lines
                    for line in cmd.output.split("\n"):
                        if any(
                            x in line.lower()
                            for x in ["passed", "failed", "error", "warning", "collected"]
                        ):
                            summary_parts.append(f"  {line.strip()}")
                            break

        return "\n".join(summary_parts) if len(summary_parts) > 1 else ""

    def get_quality_metrics(self) -> dict:
        """
        Get metrics about session quality for analysis validation.

        Returns metrics that can be used to detect suspicious analysis results:
        - has_agent_messages: Whether the session has any agent messages
        - has_work_evidence: Whether there's concrete evidence of work
        - command_success_rate: Ratio of successful commands
        - estimated_effort_score: Rough score of work done (0-100)
        """
        total_cmds = len(self.commands)
        successful_cmds = len(self.successful_commands)

        # Calculate effort score based on multiple signals
        effort_signals = []

        # File changes are strong evidence
        if self.file_changes:
            effort_signals.append(min(40, len(self.file_changes) * 10))

        # Successful commands indicate progress
        if successful_cmds > 0:
            effort_signals.append(min(30, successful_cmds * 2))

        # Agent messages indicate active work
        if self.agent_messages:
            effort_signals.append(min(20, len(self.agent_messages) * 5))

        # Todo completions are direct evidence
        completed = len(self.completed_todos)
        if completed > 0:
            effort_signals.append(min(30, completed * 10))

        effort_score = min(100, sum(effort_signals))

        return {
            "has_agent_messages": len(self.agent_messages) > 0,
            "has_work_evidence": len(self.file_changes) > 0 or successful_cmds > 0,
            "command_success_rate": successful_cmds / total_cmds if total_cmds > 0 else 0.0,
            "file_change_count": len(self.file_changes),
            "successful_command_count": successful_cmds,
            "estimated_effort_score": effort_score,
            "data_quality": self._assess_data_quality(),
        }

    def _assess_data_quality(self) -> str:
        """Assess the quality of data available for analysis."""
        if self.agent_messages and self.file_changes:
            return "high"  # Full data available
        elif self.file_changes or len(self.successful_commands) > 5:
            return "medium"  # Concrete evidence but no messages
        elif self.commands:
            return "low"  # Only commands, limited insight
        else:
            return "minimal"  # Very little data


class CodexJSONLParser:
    """Parser for Codex JSONL event streams."""

    def __init__(self):
        self._session = CodexSession()
        self._current_items: dict[str, dict] = {}  # item_id -> item data

    def parse(self, jsonl_content: str) -> CodexSession:
        """
        Parse JSONL content into a CodexSession.

        Args:
            jsonl_content: Raw JSONL string (one JSON object per line)

        Returns:
            Parsed CodexSession
        """
        for line_num, line in enumerate(jsonl_content.strip().split("\n"), 1):
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
                self._process_event(event)
                self._session.raw_event_count += 1
            except json.JSONDecodeError as e:
                error_msg = f"Line {line_num}: JSON parse error: {e}"
                logger.warning(error_msg)
                self._session.parse_errors.append(error_msg)
            except Exception as e:
                error_msg = f"Line {line_num}: Processing error: {e}"
                logger.warning(error_msg)
                self._session.parse_errors.append(error_msg)

        return self._session

    def _process_event(self, event: dict[str, Any]) -> None:
        """Process a single event."""
        event_type = event.get("type", "")

        # Thread events
        if event_type == "thread.started":
            self._session.thread_id = event.get("thread_id")

        # Turn events
        elif event_type == "turn.started":
            turn = TurnInfo(turn_id=event.get("turn_id", ""))
            self._session.turns.append(turn)

        elif event_type == "turn.completed":
            turn_id = event.get("turn_id")
            usage = event.get("token_usage", {})
            for turn in self._session.turns:
                if turn.turn_id == turn_id:
                    turn.completed = True
                    turn.input_tokens = usage.get("input_tokens", 0)
                    turn.output_tokens = usage.get("output_tokens", 0)
                    turn.reasoning_tokens = usage.get("reasoning_tokens", 0)
                    break

        elif event_type == "turn.failed":
            turn_id = event.get("turn_id")
            for turn in self._session.turns:
                if turn.turn_id == turn_id:
                    turn.failed = True
                    turn.error = event.get("error")
                    break

        # Item events
        # Handle both old schema (item_id, item_type at top level) and
        # new schema (item.id, item.type in nested object)
        elif event_type == "item.started":
            item_obj = event.get("item", {})
            item_id = event.get("item_id") or item_obj.get("id")
            item_type = event.get("item_type") or item_obj.get("type")
            if item_id:
                self._current_items[item_id] = {
                    "type": item_type,
                    "content": "",
                }

        elif event_type == "item.updated":
            item_obj = event.get("item", {})
            item_id = event.get("item_id") or item_obj.get("id")
            if item_id in self._current_items:
                # Append content updates - check multiple possible locations
                content = event.get("content", "") or item_obj.get("text", "")
                self._current_items[item_id]["content"] += content

        elif event_type == "item.completed":
            item_obj = event.get("item", {})
            item_id = event.get("item_id") or item_obj.get("id")
            item_data = self._current_items.pop(item_id, None)

            if not item_data:
                # Item wasn't tracked via item.started - extract from completed event
                item_type = event.get("item_type") or item_obj.get("type")
                item_data = {"type": item_type, "content": ""}

            item_type = item_data.get("type")
            # Content can be in multiple places: tracked content, event.content, or item.text
            content = (
                item_data.get("content", "") or event.get("content", "") or item_obj.get("text", "")
            )

            self._handle_completed_item(item_type, content, event)

    def _handle_completed_item(
        self, item_type: str | None, content: str, event: dict[str, Any]
    ) -> None:
        """Handle a completed item based on its type."""
        # Get nested item object for new schema
        item_obj = event.get("item", {})

        # Handle schema variations (old: assistant_message, new: agent_message)
        if item_type in ("agent_message", "assistant_message"):
            if content:
                self._session.agent_messages.append(content)

        elif item_type == "reasoning":
            if content:
                self._session.reasoning_summaries.append(content)

        elif item_type == "command_execution":
            # Command data can be at event level (old) or in item object (new)
            cmd = CommandExecution(
                command=event.get("command") or item_obj.get("command") or content,
                exit_code=(
                    event.get("exit_code")
                    if event.get("exit_code") is not None
                    else item_obj.get("exit_code", 0)
                ),
                output=event.get("output") or item_obj.get("aggregated_output", ""),
                duration_seconds=event.get("duration") or item_obj.get("duration"),
            )
            self._session.commands.append(cmd)

        elif item_type == "file_change":
            # File change data can be at event level (old) or in item.changes (new)
            changes = item_obj.get("changes", [])
            if changes:
                # New schema: changes is a list of {path, kind}
                for change in changes:
                    fc = FileChange(
                        path=change.get("path", ""),
                        change_type=change.get("kind", "modified"),
                        content_preview=content[:500] if content else None,
                    )
                    self._session.file_changes.append(fc)
            else:
                # Old schema: path/change_type at event level
                fc = FileChange(
                    path=event.get("path", "") or item_obj.get("path", ""),
                    change_type=event.get("change_type", "modified"),
                    content_preview=content[:500] if content else None,
                )
                self._session.file_changes.append(fc)

        elif item_type == "todo_list":
            # Parse todo items from content or event
            items = event.get("items", [])
            if not items and content:
                # Try to parse from content
                import contextlib

                with contextlib.suppress(json.JSONDecodeError):
                    items = json.loads(content)

            for item in items:
                if isinstance(item, dict):
                    todo = TodoItem(
                        task=item.get("task", ""),
                        status=item.get("status", "not_started"),
                    )
                    self._session.todo_items.append(todo)


def parse_codex_jsonl(jsonl_content: str) -> CodexSession:
    """
    Parse Codex JSONL event stream.

    Args:
        jsonl_content: Raw JSONL string from `codex exec --json`

    Returns:
        Parsed CodexSession with all extracted information
    """
    parser = CodexJSONLParser()
    return parser.parse(jsonl_content)


def parse_codex_jsonl_file(file_path: str | Path) -> CodexSession:
    """
    Parse Codex JSONL from a file.

    Args:
        file_path: Path to JSONL file

    Returns:
        Parsed CodexSession
    """
    path = Path(file_path)
    content = path.read_text()
    return parse_codex_jsonl(content)


if __name__ == "__main__":
    # Example usage
    sample_jsonl = """
{"type": "thread.started", "thread_id": "abc123"}
{"type": "turn.started", "turn_id": "turn1"}
{"type": "item.started", "item_id": "msg1", "item_type": "agent_message"}
{"type": "item.updated", "item_id": "msg1", "content": "I'll fix the test failures "}
{"type": "item.updated", "item_id": "msg1", "content": "in the calculator module."}
{"type": "item.completed", "item_id": "msg1"}
{"type": "item.completed", "item_type": "command_execution", "command": "pytest tests/", "exit_code": 0}
{"type": "item.completed", "item_type": "file_change", "path": "src/calc.py", "change_type": "modified"}
{"type": "turn.completed", "turn_id": "turn1", "token_usage": {"input_tokens": 1000, "output_tokens": 500}}
"""

    session = parse_codex_jsonl(sample_jsonl)
    print(f"Thread ID: {session.thread_id}")
    print(f"Events parsed: {session.raw_event_count}")
    print(f"Agent messages: {len(session.agent_messages)}")
    print(f"Commands: {len(session.commands)}")
    print(f"File changes: {len(session.file_changes)}")
    print(f"\nAnalysis text:\n{session.get_analysis_text()}")
