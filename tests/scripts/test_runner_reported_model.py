"""Detect the model reported by a hosted runner CLI."""

from __future__ import annotations

import json

import pytest
from scripts.runner_lib import core

CODEX_ROLLOUT = "\n".join(
    json.dumps(event)
    for event in [
        {"type": "session_meta", "payload": {"id": "s1", "model_provider": "openai"}},
        {"type": "turn_context", "payload": {"turn_id": "t1", "model": "gpt-6.1-sol"}},
        {"type": "event_msg", "payload": {"type": "task_complete"}},
        # A runtime fallback attempt writes a later turn on another model.
        {"type": "turn_context", "payload": {"turn_id": "t2", "model": "gpt-5.6-terra"}},
    ]
)

CLAUDE_TRANSCRIPT = "\n".join(
    json.dumps(event)
    for event in [
        {"type": "user", "message": {"role": "user", "content": "go"}},
        {"type": "assistant", "message": {"model": "claude-opus-5-5", "content": []}},
        # Sub-agent turns and synthetic placeholders are not the run's model.
        {
            "type": "assistant",
            "isSidechain": True,
            "message": {"model": "claude-haiku-5-0", "content": []},
        },
        {"type": "assistant", "message": {"model": "<synthetic>", "content": []}},
        # --fallback-model switched mid-run: the last main-thread turn names the fallback.
        {"type": "assistant", "message": {"model": "claude-sonnet-5-0", "content": []}},
    ]
)


def test_codex_reported_model_comes_from_its_rollout() -> None:
    assert core.extract_reported_model("codex", CODEX_ROLLOUT) == "gpt-5.6-terra"


def test_codex_reported_model_reads_the_session_header() -> None:
    header = "--------\nworkdir: /w\nmodel: gpt-6.1-sol\nprovider: openai\n--------\n"
    assert core.extract_reported_model("codex", header) == "gpt-6.1-sol"


def test_codex_exec_json_stream_alone_reports_no_model() -> None:
    stream = "\n".join(
        json.dumps(event)
        for event in [
            {"type": "thread.started", "thread_id": "x"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
            {"type": "turn.completed", "usage": {}},
        ]
    )
    assert core.extract_reported_model("codex", stream) == ""


def test_claude_reported_model_is_last_main_thread_turn() -> None:
    assert core.extract_reported_model("claude", CLAUDE_TRANSCRIPT) == "claude-sonnet-5-0"


@pytest.mark.parametrize(
    "trailing",
    [
        {
            "type": "assistant",
            "isSidechain": True,
            "message": {"model": "claude-haiku-5-0", "content": []},
        },
        {"type": "assistant", "message": {"model": "<synthetic>", "content": []}},
    ],
    ids=["trailing-sidechain", "trailing-synthetic"],
)
def test_claude_trailing_non_main_turn_does_not_replace_the_model(trailing: dict) -> None:
    transcript = CLAUDE_TRANSCRIPT + "\n" + json.dumps(trailing)
    assert core.extract_reported_model("claude", transcript) == "claude-sonnet-5-0"


def test_claude_stream_json_init_model_when_no_assistant_turn() -> None:
    init = json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-5-5"})
    assert core.extract_reported_model("claude", init) == "claude-opus-5-5"


@pytest.mark.parametrize("provider", ["codex", "claude", "cursor", "gemini", "muse"])
@pytest.mark.parametrize(
    "raw",
    ["", "All tasks done. I used the model you asked for.", "{not json", '{"type": "result"}'],
)
def test_unparseable_output_reports_empty_model(provider: str, raw: str) -> None:
    assert core.extract_reported_model(provider, raw) == ""


@pytest.mark.parametrize("provider", ["cursor", "gemini", "muse"])
def test_text_only_providers_never_borrow_a_model(provider: str) -> None:
    # These CLIs print plain text; even JSON-looking model lines are not their own report.
    assert core.extract_reported_model(provider, CODEX_ROLLOUT + "\n" + CLAUDE_TRANSCRIPT) == ""


def test_detect_model_cli_reads_files_and_skips_missing(tmp_path, monkeypatch, capsys) -> None:
    rollout = tmp_path / "rollout-1.jsonl"
    rollout.write_text(CODEX_ROLLOUT, encoding="utf-8")
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert (
        core.main(
            [
                "detect-model",
                "--provider",
                "codex",
                "--source-file",
                "",
                "--source-file",
                str(tmp_path / "missing.jsonl"),
                "--source-file",
                str(rollout),
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {"reported-model": "gpt-5.6-terra"}
    assert output.read_text(encoding="utf-8") == "reported-model=gpt-5.6-terra\n"
