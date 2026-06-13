from __future__ import annotations

import json
import subprocess
import types
from pathlib import Path
from typing import Any

import pytest
import scripts.runner_lib.core as runner_core
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


def test_assemble_prompt_formats_cursor_prompt(tmp_path: Path) -> None:
    _write_prompt_fixture(tmp_path)

    prompt = assemble_prompt(
        "baseline",
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
            "appendix": "Cursor context",
        },
        "cursor",
    )

    assert prompt.file == "cursor-prompt.md"
    assert prompt.provider == "cursor"
    assert "Cursor context" in prompt.text


def test_parse_cursor_text_output_success() -> None:
    result = parse_runner_output("cursor", "Implemented the change and ran tests.\n")

    assert result.success is True
    assert "Implemented the change" in result.final_message
    assert result.error is None


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


def test_should_dispatch_allows_stale_pending_record() -> None:
    storage = MemoryRunnerStorage()
    storage.records[(42, "codex")] = {
        "provider": "codex",
        "pr_number": 42,
        "head_sha": "aaa",
        "status": "pending",
        "started_at": "2026-05-06T00:00:00Z",
    }

    decision = should_dispatch(42, "aaa", "codex", storage=storage)

    assert decision.should_dispatch is True
    assert decision.reason == "stale-pending"


def test_should_dispatch_uses_specific_retry_reason_for_error_status() -> None:
    storage = MemoryRunnerStorage()
    storage.records[(42, "codex")] = {
        "provider": "codex",
        "pr_number": 42,
        "head_sha": "aaa",
        "status": "error",
    }

    decision = should_dispatch(42, "aaa", "codex", storage=storage)

    assert decision.should_dispatch is True
    assert decision.reason == "retry-error"


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


def test_record_completion_stores_compact_result_payload() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    result = parse_runner_output("codex", "x" * 10000)

    record = record_completion(42, "aaa", "codex", result, storage=storage)

    assert record["result"]["summary"] == "x" * 500
    assert "final_message" not in record["result"]
    assert len(record["result"]["final_message_sha256"]) == 64
    assert record["result"]["final_message_chars"] == 10000


def test_record_completion_stores_compact_marker_safe_result() -> None:
    storage = MemoryRunnerStorage()
    result = {
        "provider": "claude",
        "success": True,
        "final_message": "full output --> with marker closer",
        "summary": "summary --> closer",
        "error": None,
        "truncated": False,
    }

    record = record_completion(42, "aaa", "claude", result, storage=storage)

    stored_result = storage.records[(42, "claude")]["result"]
    assert record["result"] == stored_result
    assert stored_result["schema"] == "runner-result-summary/v1"
    assert stored_result["summary"] == "summary --\\u003e closer"
    assert "final_message" not in stored_result
    assert stored_result["final_message_chars"] == len(result["final_message"])
    assert len(stored_result["final_message_sha256"]) == 64
    assert "-->" not in json.dumps(stored_result)


def test_record_completion_preserves_falsy_result_text() -> None:
    storage = MemoryRunnerStorage()
    result = {
        "provider": "claude",
        "success": False,
        "final_message": False,
        "summary": 0,
        "error": False,
        "truncated": False,
    }

    record = record_completion(42, "aaa", "claude", result, storage=storage)

    assert record["result"]["summary"] == "0"
    assert record["result"]["error"] == "False"
    assert record["result"]["final_message_chars"] == len("False")
    assert len(record["result"]["final_message_sha256"]) == 64


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


def test_pr_comment_marker_round_trips_nested_result_payload() -> None:
    result = parse_runner_output("claude", "Done")
    record = {
        "provider": "claude",
        "pr_number": 42,
        "head_sha": "aaa",
        "status": "completed",
        "result": {
            "summary": result.summary,
            "nested": {"value": "inner"},
            "final_message": "contains --> comment closer",
        },
    }

    marker = runner_core._build_marker(42, "claude", record)
    parsed = runner_core._extract_record(marker, 42, "claude")

    assert parsed == record


def test_pr_comment_marker_rejects_invalid_base64_payload() -> None:
    marker = "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 base64:!!!not-base64!!! -->"

    assert runner_core._extract_record(marker, 42, "codex") is None


def test_pr_comment_marker_rejects_invalid_utf8_payload() -> None:
    marker = "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 base64://8= -->"

    assert runner_core._extract_record(marker, 42, "codex") is None


def test_prompt_cli_rejects_non_prompt_provider() -> None:
    parser = runner_core.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "assemble-prompt",
                "--provider",
                "autofix",
                "--base-prompt",
                ".github/codex/prompts/task.md",
            ]
        )


def test_parse_output_cli_accepts_autofix_provider() -> None:
    parser = runner_core.build_parser()

    args = parser.parse_args(["parse-output", "--provider", "autofix"])

    assert args.provider == "autofix"


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


def test_pr_comment_storage_normalizes_direction_case() -> None:
    class FakeApi:
        repo = "owner/repo"

        def __init__(self) -> None:
            self.paths: list[str] = []

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            self.paths.append(path)
            assert method == "GET"
            assert body is None
            return []

    api = FakeApi()
    storage = PrCommentRunnerStorage(api)  # type: ignore[arg-type]

    assert list(storage._iter_comments(42, direction="DESC")) == []
    assert "direction=desc" in api.paths[0]


def test_pr_comment_storage_selects_newest_marker_from_newest_page() -> None:
    class FakeApi:
        repo = "owner/repo"

        def __init__(self) -> None:
            self.paths: list[str] = []

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            assert method == "GET"
            assert body is None
            self.paths.append(path)
            if path.endswith("page=1"):
                assert "sort=created&direction=desc" in path
                return [
                    {
                        "body": (
                            "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                            '{"provider":"codex","head_sha":"new"} -->'
                        ),
                        "id": 101,
                    },
                ]
            return [
                {
                    "body": (
                        "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                        '{"provider":"codex","head_sha":"old"} -->'
                    ),
                    "id": 1,
                }
            ]

    api = FakeApi()
    storage = PrCommentRunnerStorage(api)  # type: ignore[arg-type]

    assert storage.read_record(42, "codex") == {"provider": "codex", "head_sha": "new"}
    assert len(api.paths) == 1


def test_pr_comment_storage_ignores_untrusted_marker_comments() -> None:
    class FakeApi:
        repo = "owner/repo"

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            assert method == "GET"
            assert body is None
            return [
                {
                    "body": (
                        "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                        '{"provider":"codex","head_sha":"spoofed"} -->'
                    ),
                    "id": 1,
                    "user": {"login": "drive-by-commenter"},
                    "author_association": "NONE",
                },
                {
                    "body": (
                        "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                        '{"provider":"codex","head_sha":"trusted"} -->'
                    ),
                    "id": 2,
                    "user": {"login": "github-actions[bot]"},
                    "author_association": "NONE",
                },
            ]

    storage = PrCommentRunnerStorage(FakeApi())  # type: ignore[arg-type]

    assert storage.read_record(42, "codex") == {"provider": "codex", "head_sha": "trusted"}


def test_materialize_reference_packs_import_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_import(name: str) -> Any:
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr(runner_core.importlib, "import_module", fail_import)

    with pytest.raises(RuntimeError, match="reference packs are not supported"):
        runner_core.materialize_reference_packs(".")


def test_materialize_reference_packs_does_not_put_token_in_git_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = "ghp_secret_token"
    plan = types.SimpleNamespace(
        name="baseline",
        repo="stranske/private-reference",
        ref="main",
        paths=["README.md"],
        checkout_path=".reference/baseline",
    )
    fake_reference_packs = types.SimpleNamespace(
        load_reference_packs=lambda _workspace: types.SimpleNamespace(exists=True, packs=[plan]),
        build_checkout_plan=lambda _packs: [plan],
    )
    calls: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_import(name: str) -> Any:
        assert name == "scripts.reference_packs"
        return fake_reference_packs

    def fail_check_call(
        args: list[str],
        stdout: Any = None,
        stderr: Any = None,
        env: dict[str, str] | None = None,
    ) -> None:
        calls.append((args, env))
        raise subprocess.CalledProcessError(128, args)

    monkeypatch.setattr(runner_core.importlib, "import_module", fake_import)
    monkeypatch.setattr(runner_core.subprocess, "check_call", fail_check_call)

    with pytest.raises(RuntimeError) as exc_info:
        runner_core.materialize_reference_packs(tmp_path, token=token)

    assert token not in str(exc_info.value)
    assert calls
    clone_cmd, clone_env = calls[0]
    assert all(token not in part for part in clone_cmd)
    assert clone_env is not None
    assert clone_env["GIT_ASKPASS_PASSWORD"] == token
    assert Path(clone_env["GIT_ASKPASS"]).exists() is False
