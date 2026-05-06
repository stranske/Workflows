from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.runner_lib import (
    assemble_prompt,
    parse_runner_output,
    record_completion,
    should_dispatch,
)
from scripts.runner_lib.core import PrCommentRunnerStorage, materialize_reference_packs


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


def test_parse_runner_output_detects_multiline_error_annotation() -> None:
    result = parse_runner_output("claude", "Starting work\n::error:: auth failed\n")

    assert result.success is False
    assert result.error == "::error:: auth failed"


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


def test_materialize_reference_packs_keeps_token_out_of_git_argv(
    tmp_path: Path, monkeypatch: Any
) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "reference_packs.json").write_text(
        json.dumps(
            {
                "baseline": {
                    "repo": "owner/private",
                    "ref": "main",
                    "paths": ["README.md"],
                }
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_check_call(cmd: list[str], **kwargs: Any) -> int:
        env = kwargs.get("env") or {}
        calls.append((cmd, env))
        assert "secret-token" not in " ".join(cmd)
        if cmd[:2] == ["git", "clone"]:
            clone_dir = Path(cmd[-1])
            clone_dir.mkdir(parents=True)
            (clone_dir / "README.md").write_text("reference\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    summary = materialize_reference_packs(tmp_path, token="secret-token")

    assert summary == tmp_path / ".reference" / "REFERENCE_PACKS.md"
    assert (tmp_path / ".reference" / "baseline" / "README.md").is_file()
    assert calls
    assert all(env.get("GIT_ASKPASS_PASSWORD") == "secret-token" for _cmd, env in calls)


def test_pr_comment_storage_stops_when_marker_found() -> None:
    class FakeApi:
        repo = "owner/repo"

        def __init__(self) -> None:
            self.paths: list[str] = []

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            self.paths.append(path)
            assert method == "GET"
            assert body is None
            return [
                {"body": "ordinary comment", "id": 1},
                {
                    "body": (
                        "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                        '{"provider":"codex","head_sha":"abc"} -->'
                    ),
                    "id": 2,
                },
            ]

    api = FakeApi()
    storage = PrCommentRunnerStorage(api)  # type: ignore[arg-type]

    record = storage.read_record(42, "codex")

    assert record == {"provider": "codex", "head_sha": "abc"}
    assert len(api.paths) == 1
