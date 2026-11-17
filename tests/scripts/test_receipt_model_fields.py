"""Completion receipts name the model a hosted run asked for and the model the CLI ran on."""

from __future__ import annotations

import json

import pytest
from scripts.runner_lib import core

from tests.scripts.test_runner_completion_receipts import CommentApi, reservation

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


def test_compact_summary_carries_requested_and_reported_model() -> None:
    compact = core._compact_runner_result_payload(
        {
            "provider": "claude",
            "success": True,
            "summary": "done",
            "requested_model": "claude-opus-5-5",
            "reported_model": "claude-sonnet-5-0",
        }
    )

    assert compact["schema"] == "runner-result-summary/v1"
    assert compact["requested_model"] == "claude-opus-5-5"
    assert compact["reported_model"] == "claude-sonnet-5-0"


def test_compact_summary_rejects_non_model_text() -> None:
    compact = core._compact_runner_result_payload(
        {"requested_model": "gpt-6.1-sol\ninjected=1", "reported_model": "some prose -->"}
    )

    assert compact["requested_model"] == ""
    assert compact["reported_model"] == ""


def test_payload_without_models_yields_empty_strings_and_round_trips(monkeypatch) -> None:
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "old")
    api = CommentApi(reservation())
    storage = core.PrCommentRunnerStorage(api)

    written = core.record_completion(
        42, "aaa", "codex", {"provider": "codex", "success": True}, storage=storage
    )

    assert written["result"]["requested_model"] == ""
    assert written["result"]["reported_model"] == ""
    stored = storage.read_record(42, "codex")
    assert stored["status"] == "completed"
    assert stored["result"] == written["result"]


def test_models_round_trip_through_the_receipt_reader(monkeypatch) -> None:
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "old")
    api = CommentApi(reservation())
    storage = core.PrCommentRunnerStorage(api)

    core.record_completion(
        42,
        "aaa",
        "codex",
        {
            "provider": "codex",
            "success": True,
            "requested_model": "gpt-6.1-sol",
            "reported_model": "gpt-5.6-terra",
        },
        storage=storage,
    )

    result = storage.read_record(42, "codex")["result"]
    assert result["requested_model"] == "gpt-6.1-sol"
    assert result["reported_model"] == "gpt-5.6-terra"


def test_receipt_written_before_model_fields_still_parses(monkeypatch) -> None:
    monkeypatch.setattr(core, "_workflow_attempt_id", lambda: "old")
    reserved = reservation()
    api = CommentApi(reserved)
    old_record = {
        **reserved,
        "status": "completed",
        "completed_at": "2026-09-20T00:05:00Z",
        "result": {
            "schema": "runner-result-summary/v1",
            "provider": "codex",
            "success": True,
            "summary": "done",
            "error": "",
            "truncated": False,
        },
        "completion": {"reason": "no_progress"},
    }
    api.receipts.append(
        {
            "id": 2,
            "body": core._build_marker(
                42,
                "codex",
                {
                    "schema": "runner-completion-receipt/v1",
                    "provider": "codex",
                    "reservation_id": reserved["reservation_id"],
                    "record": old_record,
                },
                marker_prefix=core.COMPLETION_MARKER_PREFIX,
            ),
        }
    )

    stored = core.PrCommentRunnerStorage(api).read_record(42, "codex")

    assert stored["result"] == old_record["result"]
    assert stored["result"].get("requested_model", "") == ""


def test_record_completion_cli_passes_models_into_the_receipt(monkeypatch, capsys) -> None:
    records: dict[tuple[int, str], dict] = {}

    class Storage:
        def read_record(self, pr_number, provider):
            return records.get((pr_number, provider))

        def write_record(self, pr_number, provider, record):
            records[(pr_number, provider)] = dict(record)

    monkeypatch.setattr(core, "_storage_from_name", lambda _name: Storage())
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "200")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    common = ["--provider", "claude", "--pr-number", "42", "--head-sha", "aaa"]
    assert core.main(["should-dispatch", *common]) == 0
    assert (
        core.main(
            [
                "record-completion",
                *common,
                "--summary",
                "Done",
                "--requested-model",
                "claude-opus-5-5",
                "--reported-model",
                "claude-sonnet-5-0",
            ]
        )
        == 0
    )
    capsys.readouterr()

    result = records[(42, "claude")]["result"]
    assert result["requested_model"] == "claude-opus-5-5"
    assert result["reported_model"] == "claude-sonnet-5-0"


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


def test_codex_requested_model_falls_back_to_the_configured_model() -> None:
    """2026-11-16: 13 hosted codex rounds stopped at "Setup Codex auth" (expired CODEX_AUTH_JSON) before the
    CLI step, so run_codex never set requested-model and every receipt read requested_model="" (half of the
    Workflows#4693 pass-number sample). The configured model is known before the run starts."""
    from pathlib import Path

    import yaml

    workflow = yaml.safe_load(
        (
            Path(__file__).resolve().parents[2] / ".github/workflows/reusable-codex-run.yml"
        ).read_text()
    )
    output = workflow["jobs"]["codex"]["outputs"]["requested-model"]
    # The CLI-level request wins; then the resolved profile model; then the configured input.
    assert output == (
        "${{ steps.run_codex.outputs.requested-model || steps.codex_model.outputs.model"
        " || inputs.codex_model }}"
    )
