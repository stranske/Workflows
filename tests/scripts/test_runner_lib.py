from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.runner_lib import (
    assemble_prompt,
    parse_runner_output,
    record_completion,
    should_dispatch,
)


class MemoryRunnerStorage:
    def __init__(self) -> None:
        self.records: dict[tuple[int, str], dict[str, Any]] = {}
        self.writes: list[dict[str, Any]] = []

    def read_record(self, pr_number: int, provider: str) -> dict[str, Any] | None:
        record = self.records.get((pr_number, provider))
        return dict(record) if record else None

    def write_record(self, pr_number: int, provider: str, record: dict[str, Any]) -> None:
        self.records[(pr_number, provider)] = dict(record)
        self.writes.append(dict(record))


def _write_prompt_fixture(root: Path) -> None:
    (root / ".github" / "codex").mkdir(parents=True)
    (root / ".github" / "claude").mkdir(parents=True)
    (root / ".github" / "codex" / "AGENT_INSTRUCTIONS.md").write_text(
        "Codex instructions\n", encoding="utf-8"
    )
    (root / ".github" / "claude" / "AGENT_INSTRUCTIONS.md").write_text(
        "Claude instructions\n", encoding="utf-8"
    )
    (root / ".github" / "codex" / "prompts").mkdir(parents=True)
    (root / ".github" / "codex" / "prompts" / "task.md").write_text(
        "Fix the issue.\n", encoding="utf-8"
    )
    (root / ".reference").mkdir()
    (root / ".reference" / "REFERENCE_PACKS.md").write_text(
        "## baseline\n- `README.md`\n", encoding="utf-8"
    )


def test_assemble_prompt_formats_codex_prompt(tmp_path: Path) -> None:
    _write_prompt_fixture(tmp_path)

    prompt = assemble_prompt(
        "baseline",
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
            "appendix": "PR #123 context",
            "pr_number": "123",
        },
        "codex",
    )

    assert prompt.file == "codex-prompt-123.md"
    assert "Codex instructions" in prompt.text
    assert "## Task Prompt" in prompt.text
    assert "Fix the issue." in prompt.text
    assert "## Run context" in prompt.text
    assert "PR #123 context" in prompt.text
    assert "## Reference Packs" in prompt.text
    assert (tmp_path / "codex-prompt-123.md").read_text(encoding="utf-8") == prompt.text


def test_assemble_prompt_formats_claude_prompt(tmp_path: Path) -> None:
    _write_prompt_fixture(tmp_path)

    prompt = assemble_prompt(
        "baseline",
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
            "appendix": "Claude context",
        },
        "claude",
    )

    assert prompt.file == "claude-prompt.md"
    assert "Claude instructions" in prompt.text
    assert "Codex instructions" not in prompt.text
    assert "Claude context" in prompt.text


def test_parse_codex_jsonl_success() -> None:
    raw = "\n".join(
        [
            json.dumps({"type": "step", "message": "working"}),
            json.dumps({"type": "final", "message": "Done"}),
        ]
    )

    result = parse_runner_output("codex", raw)

    assert result.success is True
    assert result.final_message == "Done"
    assert result.summary == "Done"
    assert result.error is None


def test_parse_runner_output_detects_error() -> None:
    result = parse_runner_output("claude", "Error: auth failed\n")

    assert result.success is False
    assert result.error == "Error: auth failed"
    assert result.summary == "Error: auth failed"


def test_parse_runner_output_marks_truncated_output() -> None:
    result = parse_runner_output("claude", "x" * 65000)

    assert result.truncated is True
    assert len(result.final_message) == 64000


def test_should_dispatch_first_duplicate_and_sha_changed() -> None:
    storage = MemoryRunnerStorage()

    first = should_dispatch(42, "aaa", "codex", storage=storage)
    duplicate = should_dispatch(42, "aaa", "codex", storage=storage)
    changed = should_dispatch(42, "bbb", "codex", storage=storage)

    assert first.should_dispatch is True
    assert first.reason == "first-dispatch"
    assert duplicate.should_dispatch is False
    assert duplicate.reason == "duplicate-pending"
    assert changed.should_dispatch is True
    assert changed.reason == "head-sha-changed"


def test_record_completion_is_idempotent_for_same_key() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "claude", storage=storage)
    result = parse_runner_output("claude", "Done")

    first = record_completion(42, "aaa", "claude", result, storage=storage)
    second = record_completion(42, "aaa", "claude", result, storage=storage)

    assert first["status"] == "completed"
    assert second["status"] == "completed"
    assert second["completed_at"] == first["completed_at"]
    assert storage.records[(42, "claude")]["result"]["summary"] == "Done"
