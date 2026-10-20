"""Contract tests for the LLM-backed topic splitter's deterministic boundary."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from scripts.langchain import topic_splitter


def _response(content: str) -> tuple[SimpleNamespace, SimpleNamespace]:
    return SimpleNamespace(content=content), SimpleNamespace(trace_url=None)


def test_generate_guid_normalizes_whitespace_and_case() -> None:
    assert topic_splitter._generate_guid(
        "  Preserve  This\nTitle "
    ) == topic_splitter._generate_guid("preserve this title")


def test_splitter_refuses_to_run_without_a_configured_client(monkeypatch) -> None:
    monkeypatch.setattr(topic_splitter, "_get_llm_client", lambda: None)

    with pytest.raises(RuntimeError, match="No LLM client available"):
        topic_splitter.split_topics_with_llm("one issue")


def test_splitter_turns_fenced_response_into_stable_topic_records(monkeypatch, capsys) -> None:
    monkeypatch.setattr(topic_splitter, "_get_llm_client", lambda: (object(), "fixture-provider"))
    monkeypatch.setattr(
        topic_splitter,
        "invoke_with_trace",
        lambda *_args, **_kwargs: _response(
            "```json\n"
            '{"issues": [{"title": "  First issue ", "body": "Keep **all** details."}, '
            '{"title": "", "body": "Second body"}]}\n'
            "```"
        ),
    )

    topics = topic_splitter.split_topics_with_llm("raw multi-issue text")

    assert [topic["title"] for topic in topics] == ["First issue", "Untitled Issue 2"]
    assert [topic["extras"] for topic in topics] == ["Keep **all** details.", "Second body"]
    assert [topic["enumerator"] for topic in topics] == ["1", "2"]
    assert topics[0]["guid"] == topic_splitter._generate_guid("First issue")
    assert topics[1]["guid"] == topic_splitter._generate_guid("Untitled Issue 2")
    assert all(topic["sections"]["acceptance_criteria"] == "" for topic in topics)
    assert "Using LLM provider: fixture-provider" in capsys.readouterr().err


def test_splitter_rejects_invalid_json_and_empty_issue_lists(monkeypatch) -> None:
    monkeypatch.setattr(topic_splitter, "_get_llm_client", lambda: (object(), "fixture-provider"))
    monkeypatch.setattr(
        topic_splitter,
        "invoke_with_trace",
        lambda *_args, **_kwargs: _response("not json"),
    )

    with pytest.raises(RuntimeError, match="did not return valid JSON"):
        topic_splitter.split_topics_with_llm("raw")

    monkeypatch.setattr(
        topic_splitter,
        "invoke_with_trace",
        lambda *_args, **_kwargs: _response('{"issues": []}'),
    )
    with pytest.raises(RuntimeError, match="returned no issues"):
        topic_splitter.split_topics_with_llm("raw")


def test_splitter_preserves_trace_url_and_wraps_provider_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(topic_splitter, "_get_llm_client", lambda: (object(), "fixture-provider"))
    monkeypatch.setattr(
        topic_splitter,
        "invoke_with_trace",
        lambda *_args, **_kwargs: (
            SimpleNamespace(content='{"issues": [{"title": "One", "body": "Body"}]}'),
            SimpleNamespace(trace_url="https://trace.example/run"),
        ),
    )

    assert topic_splitter.split_topics_with_llm("raw")[0]["title"] == "One"
    assert "LangSmith trace: https://trace.example/run" in capsys.readouterr().err

    monkeypatch.setattr(
        topic_splitter,
        "invoke_with_trace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("down")),
    )
    with pytest.raises(RuntimeError, match="LLM call failed: down"):
        topic_splitter.split_topics_with_llm("raw")


@pytest.mark.parametrize(
    ("input_text", "expected_code"),
    [("", 2), ("content", 1)],
)
def test_main_rejects_empty_input_and_splitter_errors(
    tmp_path, monkeypatch, input_text: str, expected_code: int
) -> None:
    input_path = tmp_path / "input.txt"
    input_path.write_text(input_text, encoding="utf-8")
    output_path = tmp_path / "topics.json"
    if input_text:
        monkeypatch.setattr(
            topic_splitter,
            "split_topics_with_llm",
            lambda _: (_ for _ in ()).throw(RuntimeError("bad")),
        )
    monkeypatch.setattr(
        sys,
        "argv",
        ["topic_splitter.py", "--input-file", str(input_path), "--output-file", str(output_path)],
    )

    with pytest.raises(SystemExit) as excinfo:
        topic_splitter.main()

    assert excinfo.value.code == expected_code
