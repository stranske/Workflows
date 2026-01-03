"""Tests for tools/codex_jsonl_parser.py"""

from tools.codex_jsonl_parser import (
    CodexSession,
    CommandExecution,
    FileChange,
    TodoItem,
    parse_codex_jsonl,
)


class TestCodexJSONLParser:
    """Test JSONL parsing functionality."""

    def test_parse_empty_content(self):
        """Empty content returns empty session."""
        session = parse_codex_jsonl("")
        assert session.raw_event_count == 0
        assert session.thread_id is None
        assert len(session.agent_messages) == 0

    def test_parse_thread_started(self):
        """Thread started event sets thread_id."""
        jsonl = '{"type": "thread.started", "thread_id": "test-123"}'
        session = parse_codex_jsonl(jsonl)
        assert session.thread_id == "test-123"
        assert session.raw_event_count == 1

    def test_parse_turn_lifecycle(self):
        """Turn events are tracked correctly."""
        jsonl = """
{"type": "turn.started", "turn_id": "turn-1"}
{"type": "turn.completed", "turn_id": "turn-1", "token_usage": {"input_tokens": 100, "output_tokens": 50}}
"""
        session = parse_codex_jsonl(jsonl)
        assert len(session.turns) == 1
        assert session.turns[0].turn_id == "turn-1"
        assert session.turns[0].completed is True
        assert session.turns[0].input_tokens == 100
        assert session.turns[0].output_tokens == 50

    def test_parse_turn_failed(self):
        """Failed turns are tracked."""
        jsonl = """
{"type": "turn.started", "turn_id": "turn-1"}
{"type": "turn.failed", "turn_id": "turn-1", "error": "Rate limited"}
"""
        session = parse_codex_jsonl(jsonl)
        assert len(session.turns) == 1
        assert session.turns[0].failed is True
        assert session.turns[0].error == "Rate limited"

    def test_parse_agent_message_streaming(self):
        """Agent messages with streaming updates are captured."""
        jsonl = """
{"type": "item.started", "item_id": "msg-1", "item_type": "agent_message"}
{"type": "item.updated", "item_id": "msg-1", "content": "Hello "}
{"type": "item.updated", "item_id": "msg-1", "content": "world!"}
{"type": "item.completed", "item_id": "msg-1"}
"""
        session = parse_codex_jsonl(jsonl)
        assert len(session.agent_messages) == 1
        assert session.agent_messages[0] == "Hello world!"

    def test_parse_agent_message_old_schema(self):
        """Old schema (assistant_message) is supported."""
        jsonl = '{"type": "item.completed", "item_type": "assistant_message", "content": "Done!"}'
        session = parse_codex_jsonl(jsonl)
        assert len(session.agent_messages) == 1
        assert session.agent_messages[0] == "Done!"

    def test_parse_agent_message_nested_schema(self):
        """New nested schema (item.type, item.text) is supported."""
        jsonl = '{"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "Task completed successfully!"}}'
        session = parse_codex_jsonl(jsonl)
        assert len(session.agent_messages) == 1
        assert session.agent_messages[0] == "Task completed successfully!"

    def test_parse_command_nested_schema(self):
        """New nested schema for command execution is supported."""
        jsonl = '{"type": "item.completed", "item": {"id": "cmd_1", "type": "command_execution", "command": "git status", "aggregated_output": "On branch main", "exit_code": 0}}'
        session = parse_codex_jsonl(jsonl)
        assert len(session.commands) == 1
        assert session.commands[0].command == "git status"
        assert session.commands[0].exit_code == 0
        assert session.commands[0].output == "On branch main"

    def test_parse_file_change_nested_schema(self):
        """New nested schema for file changes is supported."""
        jsonl = '{"type": "item.completed", "item": {"id": "fc_1", "type": "file_change", "changes": [{"path": "/home/user/src/app.py", "kind": "update"}]}}'
        session = parse_codex_jsonl(jsonl)
        assert len(session.file_changes) == 1
        assert session.file_changes[0].path == "/home/user/src/app.py"
        assert session.file_changes[0].change_type == "update"

    def test_parse_reasoning_nested_schema(self):
        """New nested schema for reasoning is supported."""
        jsonl = '{"type": "item.completed", "item": {"id": "r_1", "type": "reasoning", "text": "**Planning the approach**"}}'
        session = parse_codex_jsonl(jsonl)
        assert len(session.reasoning_summaries) == 1
        assert "Planning the approach" in session.reasoning_summaries[0]

    def test_parse_reasoning(self):
        """Reasoning summaries are captured."""
        jsonl = '{"type": "item.completed", "item_type": "reasoning", "content": "I should fix the tests first."}'
        session = parse_codex_jsonl(jsonl)
        assert len(session.reasoning_summaries) == 1
        assert "fix the tests" in session.reasoning_summaries[0]

    def test_parse_command_execution(self):
        """Command executions are tracked."""
        jsonl = '{"type": "item.completed", "item_type": "command_execution", "command": "pytest tests/", "exit_code": 0, "output": "1 passed"}'
        session = parse_codex_jsonl(jsonl)
        assert len(session.commands) == 1
        assert session.commands[0].command == "pytest tests/"
        assert session.commands[0].exit_code == 0
        assert len(session.successful_commands) == 1
        assert len(session.failed_commands) == 0

    def test_parse_failed_command(self):
        """Failed commands are tracked separately."""
        jsonl = '{"type": "item.completed", "item_type": "command_execution", "command": "pytest", "exit_code": 1}'
        session = parse_codex_jsonl(jsonl)
        assert len(session.failed_commands) == 1
        assert session.failed_commands[0].exit_code == 1

    def test_parse_file_change(self):
        """File changes are tracked."""
        jsonl = '{"type": "item.completed", "item_type": "file_change", "path": "src/main.py", "change_type": "modified"}'
        session = parse_codex_jsonl(jsonl)
        assert len(session.file_changes) == 1
        assert session.file_changes[0].path == "src/main.py"
        assert session.file_changes[0].change_type == "modified"

    def test_parse_todo_list(self):
        """Todo list items are extracted."""
        jsonl = '{"type": "item.completed", "item_type": "todo_list", "items": [{"task": "Fix tests", "status": "completed"}, {"task": "Update docs", "status": "in_progress"}]}'
        session = parse_codex_jsonl(jsonl)
        assert len(session.todo_items) == 2
        assert session.todo_items[0].task == "Fix tests"
        assert session.todo_items[0].status == "completed"
        assert len(session.completed_todos) == 1

    def test_parse_handles_invalid_json(self):
        """Invalid JSON lines are logged but don't crash."""
        jsonl = """
{"type": "thread.started", "thread_id": "test"}
not valid json
{"type": "turn.started", "turn_id": "turn-1"}
"""
        session = parse_codex_jsonl(jsonl)
        assert session.thread_id == "test"
        assert len(session.turns) == 1
        assert len(session.parse_errors) == 1

    def test_total_tokens(self):
        """Token totals are calculated across turns."""
        jsonl = """
{"type": "turn.started", "turn_id": "turn-1"}
{"type": "turn.completed", "turn_id": "turn-1", "token_usage": {"input_tokens": 100, "output_tokens": 50}}
{"type": "turn.started", "turn_id": "turn-2"}
{"type": "turn.completed", "turn_id": "turn-2", "token_usage": {"input_tokens": 200, "output_tokens": 100}}
"""
        session = parse_codex_jsonl(jsonl)
        assert session.total_input_tokens == 300
        assert session.total_output_tokens == 150


class TestCodexSessionAnalysisText:
    """Test analysis text generation."""

    def test_get_analysis_text_with_messages(self):
        """Analysis text includes agent messages."""
        session = CodexSession(
            agent_messages=["I completed the task successfully."],
        )
        text = session.get_analysis_text()
        assert "Agent Messages" in text
        assert "completed the task" in text

    def test_get_analysis_text_with_reasoning(self):
        """Reasoning is included when requested."""
        session = CodexSession(
            reasoning_summaries=["I should check the tests."],
        )
        text = session.get_analysis_text(include_reasoning=True)
        assert "Reasoning" in text
        assert "check the tests" in text

    def test_get_analysis_text_without_reasoning(self):
        """Reasoning can be excluded."""
        session = CodexSession(
            reasoning_summaries=["Secret thoughts"],
        )
        text = session.get_analysis_text(include_reasoning=False)
        assert "Secret thoughts" not in text

    def test_get_analysis_text_with_todos(self):
        """Todo items are formatted with status."""
        session = CodexSession(
            todo_items=[
                TodoItem(task="Fix tests", status="completed"),
                TodoItem(task="Update docs", status="in_progress"),
            ],
        )
        text = session.get_analysis_text()
        assert "Todo List" in text
        assert "✓ Fix tests" in text
        assert "→ Update docs" in text

    def test_get_analysis_text_with_files(self):
        """File changes are listed."""
        session = CodexSession(
            file_changes=[
                FileChange(path="src/main.py", change_type="modified"),
                FileChange(path="tests/test_main.py", change_type="added"),
            ],
        )
        text = session.get_analysis_text()
        assert "Files Modified" in text
        assert "modified: src/main.py" in text
        assert "added: tests/test_main.py" in text

    def test_get_analysis_text_with_commands(self):
        """Command summary is included."""
        session = CodexSession(
            commands=[
                CommandExecution(command="pytest", exit_code=0, output=""),
                CommandExecution(command="black .", exit_code=0, output=""),
                CommandExecution(command="mypy", exit_code=1, output="error"),
            ],
        )
        text = session.get_analysis_text()
        assert "Commands Executed" in text
        assert "Total: 3" in text
        assert "Successful: 2" in text
        assert "Failed: 1" in text


class TestCompleteSession:
    """Test parsing a complete realistic session."""

    def test_parse_realistic_session(self):
        """Parse a realistic multi-turn session."""
        jsonl = """
{"type": "thread.started", "thread_id": "session-abc"}
{"type": "turn.started", "turn_id": "turn-1"}
{"type": "item.started", "item_id": "reason-1", "item_type": "reasoning"}
{"type": "item.updated", "item_id": "reason-1", "content": "The user wants me to fix tests. I'll run pytest first."}
{"type": "item.completed", "item_id": "reason-1"}
{"type": "item.completed", "item_type": "command_execution", "command": "pytest tests/", "exit_code": 1, "output": "2 failed"}
{"type": "item.started", "item_id": "msg-1", "item_type": "agent_message"}
{"type": "item.updated", "item_id": "msg-1", "content": "I found 2 failing tests. Let me fix them."}
{"type": "item.completed", "item_id": "msg-1"}
{"type": "item.completed", "item_type": "file_change", "path": "tests/test_calc.py", "change_type": "modified"}
{"type": "item.completed", "item_type": "command_execution", "command": "pytest tests/", "exit_code": 0, "output": "all passed"}
{"type": "item.started", "item_id": "msg-2", "item_type": "agent_message"}
{"type": "item.updated", "item_id": "msg-2", "content": "All tests pass now. The fix was to update the expected value."}
{"type": "item.completed", "item_id": "msg-2"}
{"type": "turn.completed", "turn_id": "turn-1", "token_usage": {"input_tokens": 500, "output_tokens": 200}}
"""
        session = parse_codex_jsonl(jsonl)

        # Check overall structure
        assert session.thread_id == "session-abc"
        assert len(session.turns) == 1
        assert session.turns[0].completed

        # Check content
        assert len(session.reasoning_summaries) == 1
        assert "run pytest" in session.reasoning_summaries[0]

        assert len(session.agent_messages) == 2
        assert "2 failing tests" in session.agent_messages[0]
        assert "All tests pass" in session.agent_messages[1]

        assert len(session.commands) == 2
        assert len(session.successful_commands) == 1
        assert len(session.failed_commands) == 1

        assert len(session.file_changes) == 1
        assert session.file_changes[0].path == "tests/test_calc.py"

        # Check tokens
        assert session.total_input_tokens == 500
        assert session.total_output_tokens == 200

        # Check analysis text
        text = session.get_analysis_text()
        assert "All tests pass" in text
        assert "Files Modified" in text
        assert "Commands Executed" in text
