"""Contract tests for the LLM-backed topic splitter's deterministic boundary."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path
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


@pytest.mark.parametrize("string_response", [False, True])
def test_splitter_turns_fenced_response_into_stable_topic_records(
    monkeypatch, capsys, string_response: bool
) -> None:
    client = object()
    input_text = "## Issue {one}\nKeep **all** details and `scripts/example.py`."
    monkeypatch.setattr(topic_splitter, "_get_llm_client", lambda: (client, "fixture-provider"))
    calls = []

    def invoke(llm, prompt, *, operation):
        calls.append((llm, prompt, operation))
        response, trace = _response(
            "```json\n"
            '{"issues": [{"title": "  First issue ", "body": "Keep **all** details."}, '
            '{"title": "", "body": "Second body"}]}\n'
            "```"
        )
        return (response.content if string_response else response), trace

    monkeypatch.setattr(topic_splitter, "invoke_with_trace", invoke)

    topics = topic_splitter.split_topics_with_llm(input_text)

    assert len(calls) == 1
    assert calls[0][0] is client
    assert calls[0][1].endswith(input_text)
    assert calls[0][2] == "topic_splitter"
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


def test_main_rejects_missing_input_and_writes_topics(tmp_path, monkeypatch, capsys) -> None:
    missing = tmp_path / "missing.txt"
    monkeypatch.setattr(sys, "argv", ["topic_splitter.py", "--input-file", str(missing)])
    with pytest.raises(SystemExit) as excinfo:
        topic_splitter.main()
    assert excinfo.value.code == 1
    assert "Input file not found" in capsys.readouterr().err

    input_path = tmp_path / "input.txt"
    output_path = tmp_path / "topics.json"
    input_path.write_text("one", encoding="utf-8")
    monkeypatch.setattr(topic_splitter, "split_topics_with_llm", lambda _: [{"title": "One"}])
    monkeypatch.setattr(
        sys,
        "argv",
        ["topic_splitter.py", "--input-file", str(input_path), "--output-file", str(output_path)],
    )
    topic_splitter.main()
    assert output_path.read_text(encoding="utf-8") == '[\n  {\n    "title": "One"\n  }\n]'
    assert "Split into 1 topic(s). First: One" in capsys.readouterr().out


def test_direct_script_execution_uses_local_import_fallback(tmp_path) -> None:
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, str(topic_splitter.__file__), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert result.returncode == 0
    assert "Split raw text into topics using LLM" in result.stdout


def _exec_topic_splitter_with_scripts_stub() -> types.ModuleType:
    """Load topic_splitter.py while ``scripts`` is an incomplete package stub.

    Forces the ModuleNotFoundError import-fallback (lines 26–28). Subprocess
    execution exercises the same path behaviorally, but in-process reload is
    required for pytest-cov to attribute those lines.
    """
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "scripts" / "langchain" / "topic_splitter.py"
    probe_name = "scripts.langchain.topic_splitter_import_fallback_probe"
    langchain_dir = str(module_path.parent)

    saved = {
        name: module
        for name, module in sys.modules.items()
        if name == "scripts" or name.startswith("scripts.")
    }
    saved_path = list(sys.path)
    try:
        for name in list(sys.modules):
            if name == "scripts" or name.startswith("scripts."):
                del sys.modules[name]

        stub_scripts = types.ModuleType("scripts")
        stub_scripts.__path__ = []
        sys.modules["scripts"] = stub_scripts
        sys.path.insert(0, langchain_dir)

        spec = importlib.util.spec_from_file_location(probe_name, module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[probe_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = saved_path
        sys.modules.pop(probe_name, None)
        for name in list(sys.modules):
            if name == "scripts" or name.startswith("scripts."):
                del sys.modules[name]
        sys.modules.update(saved)


def test_import_fallback_recovers_when_scripts_package_is_incomplete() -> None:
    module = _exec_topic_splitter_with_scripts_stub()
    assert callable(module.split_topics_with_llm)
    assert topic_splitter.split_topics_with_llm is not None
