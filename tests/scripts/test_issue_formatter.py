from __future__ import annotations

import io
import json
import sys
import types
from unittest import mock

import pytest

from scripts.langchain import issue_formatter


def _install_fake_langchain(monkeypatch: pytest.MonkeyPatch, mock_chain: mock.MagicMock) -> None:
    mock_template = mock.MagicMock()
    mock_template.__or__ = mock.MagicMock(return_value=mock_chain)

    class FakeChatPromptTemplate:
        @staticmethod
        def from_template(_: str):
            return mock_template

    fake_prompts = types.SimpleNamespace(ChatPromptTemplate=FakeChatPromptTemplate)
    fake_core = types.SimpleNamespace(prompts=fake_prompts)
    monkeypatch.setitem(sys.modules, "langchain_core", fake_core)
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)


def _extract_section(body: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in body:
        return ""
    parts = body.split(marker, 1)[1].split("\n")
    # Skip the blank line after the heading
    content_lines = []
    for line in parts[1:]:
        if line.startswith("## "):
            break
        content_lines.append(line)
    return "\n".join(content_lines).strip()


def test_format_issue_fallback_adds_sections_and_checkboxes() -> None:
    raw = """Why:
We need to improve the issue intake.

Tasks:
- add formatter
- add tests

Acceptance Criteria:
- formatted issue body
- label transition works
"""
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    formatted = result["formatted_body"]

    assert "## Why" in formatted
    assert "## Tasks" in formatted
    assert "## Acceptance Criteria" in formatted
    assert "- [ ] add formatter" in formatted
    assert "- [ ] add tests" in formatted
    assert "- [ ] formatted issue body" in formatted
    assert "- [ ] label transition works" in formatted


def test_format_issue_fallback_decomposes_large_tasks() -> None:
    raw = """## Tasks
- update docs and add tests

## Acceptance Criteria
- documentation updated
"""
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    tasks = _extract_section(result["formatted_body"], "Tasks")

    assert "- [ ] update docs and add tests" in tasks
    assert "update docs (verify: docs updated)" in tasks
    assert "add tests (verify: tests pass)" in tasks


def test_format_issue_fallback_strips_bullets_from_scope() -> None:
    raw = """## Scope
- keep API stable
- avoid workflow changes

## Tasks
- add formatter
"""
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    formatted = result["formatted_body"]

    scope = _extract_section(formatted, "Scope")
    assert scope
    assert "- " not in scope
    assert "* " not in scope
    assert "keep API stable" in scope
    assert "avoid workflow changes" in scope


def test_format_issue_fallback_uses_placeholders() -> None:
    raw = "Just a note without sections."
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    formatted = result["formatted_body"]

    tasks = _extract_section(formatted, "Tasks")
    acceptance = _extract_section(formatted, "Acceptance Criteria")

    assert tasks == "- [ ] _Not provided._"
    assert acceptance == "- [ ] _Not provided._"


def test_format_issue_fallback_preserves_raw_issue() -> None:
    raw = "Raw issue text\n\n- bullet"
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    formatted = result["formatted_body"]

    assert "<details>" in formatted
    assert "<summary>Original Issue</summary>" in formatted
    assert raw in formatted


def test_load_prompt_appends_feedback(tmp_path, monkeypatch) -> None:
    prompt_path = tmp_path / "format_issue.md"
    feedback_path = tmp_path / "format_issue_feedback.md"
    prompt_path.write_text("Base prompt.", encoding="utf-8")
    feedback_path.write_text("Feedback notes.", encoding="utf-8")

    monkeypatch.setattr(issue_formatter, "PROMPT_PATH", prompt_path)
    monkeypatch.setattr(issue_formatter, "FEEDBACK_PROMPT_PATH", feedback_path)

    prompt = issue_formatter._load_prompt()

    assert "Base prompt." in prompt
    assert "Feedback notes." in prompt


def test_format_issue_body_falls_back_without_llm_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    # Clear LLM tokens to force fallback behavior
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    raw = "Just a note without tokens."
    result = issue_formatter.format_issue_body(raw, use_llm=True)

    assert result["used_llm"] is False
    assert result["provider_used"] is None
    assert "## Tasks" in result["formatted_body"]


def test_format_issue_body_llm_path_includes_raw_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.content = "## Tasks\n- [ ] Do it\n\n## Acceptance Criteria\n- [ ] Done"
    mock_chain.invoke.return_value = mock_response

    _install_fake_langchain(monkeypatch, mock_chain)

    with mock.patch(
        "scripts.langchain.issue_formatter._get_llm_client",
        return_value=(mock_client, "github-models"),
    ):
        result = issue_formatter.format_issue_body("Raw issue text", use_llm=True)

    assert result["used_llm"] is True
    assert "<summary>Original Issue</summary>" in result["formatted_body"]
    assert "Raw issue text" in result["formatted_body"]


def test_format_issue_body_llm_invalid_output_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.content = "No required sections."
    mock_chain.invoke.return_value = mock_response

    _install_fake_langchain(monkeypatch, mock_chain)

    with mock.patch(
        "scripts.langchain.issue_formatter._get_llm_client",
        return_value=(mock_client, "openai"),
    ):
        result = issue_formatter.format_issue_body("Why: Because", use_llm=True)

    assert result["used_llm"] is False
    assert result["provider_used"] is None
    assert "## Acceptance Criteria" in result["formatted_body"]


def test_format_issue_fallback_parses_aliases_and_preamble() -> None:
    raw = """Quick summary without heading.

**Motivation**
Improve formatting.

Task List:
1. add formatter

Definition of Done:
* formatted body
"""
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    formatted = result["formatted_body"]

    why = _extract_section(formatted, "Why")
    scope = _extract_section(formatted, "Scope")
    tasks = _extract_section(formatted, "Tasks")
    acceptance = _extract_section(formatted, "Acceptance Criteria")

    assert "Improve formatting." in why
    assert "Quick summary without heading." in scope
    assert "Quick summary without heading." in scope
    assert "- [ ] add formatter" in tasks
    assert "- [ ] formatted body" in acceptance


def test_format_issue_fallback_preserves_code_fences_in_tasks() -> None:
    raw = """## Tasks
- add formatter
```
- [ ] should stay literal
```
"""
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    tasks = _extract_section(result["formatted_body"], "Tasks")

    assert "```" in tasks
    assert "- [ ] add formatter" in tasks
    assert "- [ ] should stay literal" in tasks


def test_build_label_transition_matches_expected_labels() -> None:
    assert issue_formatter.build_label_transition() == {
        "add": ["agents:formatted"],
        "remove": ["agents:format"],
    }


def test_main_emits_json_with_labels(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["issue_formatter.py", "--input-text", "Raw issue", "--json", "--no-llm"],
    )

    issue_formatter.main()
    captured = capsys.readouterr().out.strip()

    payload = json.loads(captured)
    assert payload["labels"] == {
        "add": ["agents:formatted"],
        "remove": ["agents:format"],
    }
    assert payload["used_llm"] is False
    assert "## Acceptance Criteria" in payload["formatted_body"]


def test_main_writes_output_file(monkeypatch, tmp_path, capsys) -> None:
    output_path = tmp_path / "formatted.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "issue_formatter.py",
            "--input-text",
            "Why: Because",
            "--output-file",
            str(output_path),
            "--no-llm",
        ],
    )

    issue_formatter.main()
    stdout = capsys.readouterr().out

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") in stdout


def test_main_reads_stdin_when_no_input_options(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["issue_formatter.py", "--no-llm"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("Why: stdin"))

    issue_formatter.main()

    stdout = capsys.readouterr().out
    assert "## Why" in stdout


def test_format_issue_body_rejects_oversized_input() -> None:
    """Issue #862 root cause: 135K char issue body exceeded 30K TPM limit.

    The formatter should reject oversized inputs early with a clear error
    instead of letting them hit OpenAI rate limits.
    """
    # Create oversized input (>50K chars)
    oversized_body = "x" * 60000

    result = issue_formatter.format_issue_body(oversized_body, use_llm=False)

    assert result["formatted_body"] is None
    assert result["used_llm"] is False
    assert "error" in result
    assert "too large" in result["error"]
    assert "60,000" in result["error"]  # Should show actual size
    assert "50,000" in result["error"]  # Should show limit
