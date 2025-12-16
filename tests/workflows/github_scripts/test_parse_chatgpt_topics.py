from __future__ import annotations

import contextlib
import io
import json
import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".github" / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "parse_chatgpt_topics.py"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import parse_chatgpt_topics as parser  # noqa: E402

DECODE_SCRIPT_PATH = SCRIPT_DIR / "decode_raw_input.py"


def run_decode_script(
    workdir: Path,
    *,
    argv: tuple[str, ...] = (),
    raw_payload: str | None = None,
) -> SimpleNamespace:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    original_cwd = os.getcwd()
    original_argv = sys.argv[:]
    try:
        os.chdir(workdir)
        if raw_payload is not None:
            (workdir / "raw_input.json").write_text(raw_payload, encoding="utf-8")
        sys.argv = [str(DECODE_SCRIPT_PATH), *argv]
        with (
            contextlib.redirect_stdout(stdout_buffer),
            contextlib.redirect_stderr(stderr_buffer),
        ):
            try:
                runpy.run_path(str(DECODE_SCRIPT_PATH), run_name="__main__")
                code = 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
    finally:
        os.chdir(original_cwd)
        sys.argv = original_argv

    return SimpleNamespace(
        returncode=code,
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
        input_path=workdir / "input.txt",
    )


def run_parse_script(workdir: Path, *, env: dict[str, str] | None = None) -> SimpleNamespace:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    original_cwd = os.getcwd()
    original_env = os.environ.copy()
    original_argv = sys.argv[:]
    try:
        os.chdir(workdir)
        if env:
            os.environ.update(env)
        sys.argv = [str(SCRIPT_PATH)]
        with (
            contextlib.redirect_stdout(stdout_buffer),
            contextlib.redirect_stderr(stderr_buffer),
        ):
            try:
                runpy.run_path(str(SCRIPT_PATH), run_name="__main__")
                code = 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
    finally:
        os.chdir(original_cwd)
        os.environ.clear()
        os.environ.update(original_env)
        sys.argv = original_argv

    return SimpleNamespace(
        returncode=code,
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
        output_path=workdir / "topics.json",
    )


def test_parse_text_extracts_sections_and_labels() -> None:
    raw_text = (
        "1) First title\n"
        "Labels: agent:codex, agents:codex-invite, enhancement\n"
        "Intro paragraph before sections\n\n"
        "Why\nReason line\n\n"
        "Tasks\n- item one\n- item two\n\n"
        "Acceptance criteria\nOutcome defined\n\n"
        "Implementation notes\nKeep tests updated\n"
        "3) Second title\n"
        "Additional notes for later\n"
    )

    topics = parser.parse_text(raw_text)
    assert len(topics) == 2

    first = topics[0]
    assert first["title"] == "First title"
    assert first["labels"] == [
        "agent:codex",
        "agents:codex-invite",
        "enhancement",
    ]
    assert "Reason line" in first["sections"]["why"]
    assert "item one" in first["sections"]["tasks"]
    assert "Outcome defined" in first["sections"]["acceptance_criteria"]
    assert "Keep tests updated" in first["sections"]["implementation_notes"]
    assert "Intro paragraph" in first["extras"]
    assert first["guid"]

    second = topics[1]
    assert second["title"] == "Second title"
    assert second["continuity_break"] is True


def test_split_numbered_items_handles_alpha_and_alphanum() -> None:
    alpha_text = "A) Alpha topic\nB) Beta topic\nD) Delta topic"
    alpha_items = parser._split_numbered_items(alpha_text)
    assert [item["enumerator"] for item in alpha_items] == ["A", "B", "D"]
    assert alpha_items[1]["continuity_break"] is False
    assert alpha_items[2]["continuity_break"] is True

    alphanum_text = "A1) Combined topic\nA2) Follow up"
    alphanum_items = parser._split_numbered_items(alphanum_text)
    assert [item["enumerator"] for item in alphanum_items] == ["A1", "A2"]
    assert alphanum_items[1]["continuity_break"] is False


def test_parse_text_single_topic_fallback() -> None:
    text = "Standalone topic without numbering\nFollow up details line"

    topics = parser.parse_text(text, allow_single_fallback=True)
    assert len(topics) == 1
    only = topics[0]
    assert only["title"].startswith("Standalone topic without numbering")
    assert "Follow up details line" in only["extras"]
    assert only["labels"] == []
    assert only["sections"]["why"] == ""


def test_parse_text_handles_non_list_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    sample_items = [
        {"title": "Numeric", "lines": ["Line"], "continuity_break": False},
        {"title": "StringLines", "lines": "single", "continuity_break": False},
        {"title": "NoneLines", "lines": None, "continuity_break": False},
    ]

    monkeypatch.setattr(parser, "_split_numbered_items", lambda text: sample_items)

    topics = parser.parse_text("ignored")
    assert len(topics) == 3
    assert topics[1]["sections"]["why"] == ""
    assert topics[2]["extras"] == ""


def test_main_generates_topics_file(tmp_path: Path) -> None:
    (tmp_path / "input.txt").write_text(
        "1) Alpha topic\nWhy\nAlpha\n\nTasks\n- a\n\nAcceptance criteria\nDone\n",
        encoding="utf-8",
    )

    result = run_parse_script(tmp_path)
    assert result.returncode == 0

    data = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["title"] == "Alpha topic"


def test_pipeline_processes_issues_style_input(tmp_path: Path) -> None:
    workdir = tmp_path / "pipeline"
    workdir.mkdir()

    issues_text = (
        "1. Agents Workflow Guard\n"
        "Labels: agent:codex, agents, guardrail\n\n"
        "Why\nEnsure workflows stay healthy.\n\n"
        "Tasks\n- review pipeline\n- update documentation\n\n"
        "Acceptance criteria\nAll checks green.\n\n"
        "Implementation notes\nCoordinate with maintainers.\n\n"
        "2. Agents Intake Labels\n"
        "Labels: agent:codex, documentation\n\n"
        "Why\nClarify unlabeled behaviour.\n\n"
        "Tasks\n- update triggers\n\n"
        "Acceptance criteria\nPolicy documented.\n\n"
        "Implementation notes\nKeep concurrency group stable.\n"
    )

    source_path = workdir / "Issues.txt"
    source_path.write_text(issues_text, encoding="utf-8")

    decode_result = run_decode_script(
        workdir,
        argv=("--passthrough", "--in", str(source_path), "--source", "repo_file"),
    )
    assert decode_result.returncode == 0
    assert decode_result.input_path.exists()

    parse_result = run_parse_script(workdir)
    assert parse_result.returncode == 0

    topics = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))
    assert len(topics) == 2
    first, second = topics
    assert "agent:codex" in first["labels"]
    assert first["sections"]["why"].startswith("Ensure workflows")
    assert first["sections"]["acceptance_criteria"].startswith("All checks")
    assert first["guid"]

    assert "agent:codex" in second["labels"]
    assert second["sections"]["tasks"].startswith("- update")
    assert second["continuity_break"] is False


def test_main_exit_codes_for_empty_or_unstructured_input(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    (empty_dir / "input.txt").write_text("\n", encoding="utf-8")

    empty_result = run_parse_script(empty_dir)
    assert empty_result.returncode == 2
    assert empty_result.stderr.strip() == "2"

    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    (plain_dir / "input.txt").write_text("No enumerators present", encoding="utf-8")

    plain_result = run_parse_script(plain_dir)
    assert plain_result.returncode == 3
    assert plain_result.stderr.strip() == "3"


def test_main_missing_input_propagates(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing"
    missing_dir.mkdir()
    result = run_parse_script(missing_dir)
    assert result.returncode == 1
    assert "No input.txt" in result.stderr


def test_main_unknown_system_exit_re_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> list[dict[str, object]]:
        raise SystemExit("Unhandled parsing error")

    monkeypatch.setattr(parser, "parse_topics", boom)

    with pytest.raises(SystemExit) as excinfo:
        parser.main()
    assert str(excinfo.value) == "Unhandled parsing error"


def test_main_raises_when_no_topics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parser, "parse_topics", lambda: [])

    with pytest.raises(SystemExit) as excinfo:
        parser.main()
    assert excinfo.value.code == 4


def test_parse_text_fallback_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_text("   ", allow_single_fallback=True)
    assert excinfo.value.code == 2
