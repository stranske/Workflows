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

    def get_analysis_text(self, include_reasoning: bool = True) -> str:
        """
        Get consolidated text suitable for LLM analysis.

        Args:
            include_reasoning: Whether to include reasoning summaries

        Returns:
            Formatted text with key session information
        """
        sections = []

        # Agent messages (highest signal)
        if self.agent_messages:
            sections.append("## Agent Messages")
            for msg in self.agent_messages:
                sections.append(msg[:2000])  # Truncate long messages
                sections.append("")

        # Reasoning (if requested)
        if include_reasoning and self.reasoning_summaries:
            sections.append("## Reasoning Summaries")
            for reason in self.reasoning_summaries:
                sections.append(reason[:1000])
                sections.append("")

        # Todo list (direct task mapping)
        if self.todo_items:
            sections.append("## Todo List")
            for item in self.todo_items:
                status_emoji = {
                    "completed": "✓",
                    "in_progress": "→",
                    "blocked": "✗",
                    "not_started": "○",
                }.get(item.status, "?")
                sections.append(f"{status_emoji} {item.task}")
            sections.append("")

        # File changes (concrete evidence)
        if self.file_changes:
            sections.append("## Files Modified")
            for fc in self.file_changes:
                sections.append(f"- {fc.change_type}: {fc.path}")
            sections.append("")

        # Command summary
        if self.commands:
            sections.append("## Commands Executed")
            sections.append(f"- Total: {len(self.commands)}")
            sections.append(f"- Successful: {len(self.successful_commands)}")
            sections.append(f"- Failed: {len(self.failed_commands)}")
            if self.failed_commands:
                sections.append("- Failed commands:")
                for cmd in self.failed_commands[:3]:  # Limit to first 3
                    sections.append(f"  - {cmd.command[:100]} (exit {cmd.exit_code})")
            sections.append("")

        return "\n".join(sections)


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
        elif event_type == "item.started":
            item_id = event.get("item_id")
            # Handle both old (item_type) and new (type in nested object) schemas
            item_type = event.get("item_type") or event.get("item", {}).get("type")
            if item_id:
                self._current_items[item_id] = {
                    "type": item_type,
                    "content": "",
                }

        elif event_type == "item.updated":
            item_id = event.get("item_id")
            if item_id in self._current_items:
                # Append content updates
                content = event.get("content", "")
                self._current_items[item_id]["content"] += content

        elif event_type == "item.completed":
            item_id = event.get("item_id")
            item_data = self._current_items.pop(item_id, None)

            if not item_data:
                # Try to get item type from event itself
                item_type = event.get("item_type") or event.get("item", {}).get("type")
                item_data = {"type": item_type, "content": ""}

            item_type = item_data.get("type")
            content = item_data.get("content", "") or event.get("content", "")

            self._handle_completed_item(item_type, content, event)

    def _handle_completed_item(
        self, item_type: str | None, content: str, event: dict[str, Any]
    ) -> None:
        """Handle a completed item based on its type."""

        # Handle schema variations (old: assistant_message, new: agent_message)
        if item_type in ("agent_message", "assistant_message"):
            if content:
                self._session.agent_messages.append(content)

        elif item_type == "reasoning":
            if content:
                self._session.reasoning_summaries.append(content)

        elif item_type == "command_execution":
            cmd = CommandExecution(
                command=event.get("command", content),
                exit_code=event.get("exit_code", 0),
                output=event.get("output", ""),
                duration_seconds=event.get("duration"),
            )
            self._session.commands.append(cmd)

        elif item_type == "file_change":
            fc = FileChange(
                path=event.get("path", ""),
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
