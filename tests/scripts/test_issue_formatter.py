from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import sys
import types
from unittest import mock

import pytest
from scripts.langchain import issue_formatter
from scripts.langchain.issue_pr_context import reuse_formatted_body


def _canonical_issue_format():
    return issue_formatter._issue_format_validator()


def test_issue_format_validator_removes_partially_loaded_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed validator import must not poison a later retry."""

    attempts = {"count": 0}

    class ValidationResult:
        ok = True

    class FailingLoader:
        def create_module(self, spec):  # noqa: ANN001
            return None

        def exec_module(self, module):  # noqa: ANN001
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("transient validator load failure")
            module.__dict__["validate"] = lambda body: ValidationResult()

    spec = importlib.machinery.ModuleSpec("_fleet_issue_format", FailingLoader())
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *args: spec)
    issue_formatter._issue_format_validator.cache_clear()

    with pytest.raises(RuntimeError, match="transient validator load failure"):
        issue_formatter._issue_format_validator()

    assert "_fleet_issue_format" not in sys.modules
    issue_formatter._issue_format_validator.cache_clear()

    validator = issue_formatter._issue_format_validator()
    assert attempts["count"] == 2
    assert "_fleet_issue_format" in sys.modules
    assert validator is sys.modules["_fleet_issue_format"]

    sys.modules.pop("_fleet_issue_format", None)
    issue_formatter._issue_format_validator.cache_clear()


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


def test_format_issue_fallback_adds_acceptance_gate_when_only_tasks_have_verify_hint() -> None:
    raw = """## Tasks
- [ ] Update `scripts/langchain/issue_formatter.py` and run `(verify: pytest tests/scripts/test_issue_formatter.py)`.

## Acceptance Criteria
- [ ] Formatter preserves the source acceptance prose.
"""

    formatted = issue_formatter.format_issue_body(raw, use_llm=False)["formatted_body"]
    acceptance = _extract_section(formatted, "Acceptance Criteria")

    assert "python3 -m pytest tests/scripts/test_issue_formatter.py" in acceptance
    assert "Formatter preserves the source acceptance prose." in acceptance
    assert _canonical_issue_format().GATE.search(acceptance)
    assert _canonical_issue_format().validate(formatted).ok is True


def test_format_issue_fallback_replaces_acceptance_placeholder_for_safe_verify_hint() -> None:
    raw = """## Tasks
- [ ] Update `scripts/langchain/issue_formatter.py` and run `(verify: pytest tests/scripts/test_issue_formatter.py)`.

## Acceptance Criteria
- [ ] _Not provided._
"""

    formatted = issue_formatter.format_issue_body(raw, use_llm=False)["formatted_body"]
    acceptance = _extract_section(formatted, "Acceptance Criteria")

    assert "_Not provided._" not in acceptance
    assert "python3 -m pytest tests/scripts/test_issue_formatter.py" in acceptance


def test_format_issue_fallback_does_not_promote_shell_verify_hint() -> None:
    raw = """## Tasks
- [ ] Update `scripts/langchain/issue_formatter.py` `(verify: pytest tests/test_x.py; curl https://example.invalid)`.

## Acceptance Criteria
- [ ] _Not provided._
"""

    formatted = issue_formatter.format_issue_body(raw, use_llm=False)["formatted_body"]

    assert "curl https://example.invalid" not in _extract_section(formatted, "Acceptance Criteria")


def test_format_issue_fallback_preserves_tasks_without_decomposition() -> None:
    """Formatter preserves tasks as-is; decomposition is done by agents:optimize step.

    Task decomposition was moved from formatter to the optimize step (which uses
    LLM for intelligent splitting) to avoid heuristic-based task explosion that
    caused issues #805 and #1143.
    """
    raw = """## Tasks
- update docs and add tests

## Acceptance Criteria
- documentation updated
"""
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    tasks = _extract_section(result["formatted_body"], "Tasks")

    # Task is preserved as-is - decomposition happens in optimize step
    assert "- [ ] update docs and add tests" in tasks


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
    assert acceptance.startswith("- [ ] _Not provided._")
    assert "python3 -m pytest" not in acceptance
    assert _canonical_issue_format().validate(formatted).ok is False
    assert result["needs_refinement"] is True


def test_normalize_checklist_lines_drops_placeholder_checkboxes() -> None:
    lines = [
        "- [ ] ---",
        "- [ ] _Filed from the 2026-05-29 design-vs-implementation + blueprint review (upgraded issue set)._",
        "- [ ] _Not provided._",
        "- [ ] Add focused regression test",
        "- [ ] Filed from intake form preserves source metadata",
    ]

    normalized = issue_formatter._normalize_checklist_lines(lines)

    assert normalized == [
        "- [ ] Add focused regression test",
        "- [ ] Filed from intake form preserves source metadata",
    ]


def test_format_issue_fallback_preserves_raw_issue() -> None:
    raw = "Raw issue text\n\n- bullet"
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    formatted = result["formatted_body"]

    assert "<details>" in formatted
    assert "<summary>Original Issue</summary>" in formatted
    assert raw in formatted


def test_format_issue_skips_append_when_input_has_original_issue() -> None:
    """Prevent nested Original Issue sections when re-formatting already-formatted issues."""
    already_formatted = """## Tasks

- [ ] Task 1

## Acceptance Criteria

- [ ] Done

## Implementation Notes

_Not provided._

<details>
<summary>Original Issue</summary>

```text
Original raw content
```
</details>"""
    result = issue_formatter.format_issue_body(already_formatted, use_llm=False)
    formatted = result["formatted_body"]

    # Should NOT nest another Original Issue section - count should remain 1
    # (the original, not a newly appended one)
    assert formatted.count("<summary>Original Issue</summary>") == 1


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


def test_format_issue_body_guard_blocks_llm(
    monkeypatch: pytest.MonkeyPatch,
    injection_samples: list[dict[str, str]],
) -> None:
    raw = injection_samples[0]["text"]

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("LLM should not be invoked when guard blocks input.")

    monkeypatch.setattr(issue_formatter, "_get_llm_client", _fail)

    result = issue_formatter.format_issue_body(raw, use_llm=True)

    assert result["guard_blocked"] is True
    assert result["guard_reason"]
    assert result["used_llm"] is False
    assert result["provider_used"] is None
    assert result["formatted_body"] == raw


def test_format_issue_body_llm_path_includes_raw_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.content = (
        "## Tasks\n- [ ] Update `scripts/langchain/issue_formatter.py`.\n\n"
        "## Acceptance Criteria\n"
        "- [ ] `pytest tests/scripts/test_issue_formatter.py` passes."
    )
    mock_response.response_metadata = {"run_id": "trace-format"}
    mock_chain.invoke.return_value = mock_response

    _install_fake_langchain(monkeypatch, mock_chain)

    with mock.patch(
        "scripts.langchain.issue_formatter._get_llm_client",
        return_value=(mock_client, "github-models"),
    ):
        result = issue_formatter.format_issue_body("Raw issue text", use_llm=True)

    assert result["used_llm"] is True
    assert result["langsmith_trace_id"] == "trace-format"
    assert "<summary>Original Issue</summary>" in result["formatted_body"]
    assert "Raw issue text" in result["formatted_body"]


def test_formatted_output_valid_uses_canonical_contract() -> None:
    invalid = "## Tasks\n- [ ] Do it\n\n## Acceptance Criteria\n- [ ] Done"
    valid = (
        "## Tasks\n- [ ] Update `scripts/langchain/issue_formatter.py`.\n\n"
        "## Acceptance Criteria\n"
        "- [ ] `pytest tests/scripts/test_issue_formatter.py` passes."
    )

    assert issue_formatter._formatted_output_valid(invalid) is False
    assert issue_formatter._formatted_output_valid(valid) is True


def test_formatter_degrades_to_heading_validation_when_validator_cannot_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A briefly incomplete consumer sync must not make issue formatting crash."""
    monkeypatch.setattr(
        issue_formatter,
        "_issue_format_validator",
        mock.MagicMock(side_effect=OSError("validator unavailable")),
    )
    raw = """## Tasks

- [ ] Run `(verify: pytest tests/scripts/test_issue_formatter.py)`.

## Acceptance Criteria

- [ ] Preserve a heading-only fallback while the validator is unavailable.
"""

    formatted = issue_formatter._format_issue_fallback(raw)

    assert issue_formatter._formatted_output_valid(formatted) is True
    assert "PR validation evidence" not in formatted


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


def test_format_issue_fallback_accepts_alpha_lists() -> None:
    raw = """Tasks:
a) add formatter
B) add tests

Acceptance Criteria:
a) formatter runs
"""
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    formatted = result["formatted_body"]

    tasks = _extract_section(formatted, "Tasks")
    acceptance = _extract_section(formatted, "Acceptance Criteria")

    assert "- [ ] add formatter" in tasks
    assert "- [ ] add tests" in tasks
    assert "- [ ] formatter runs" in acceptance


def test_format_issue_fallback_drops_code_fences_in_tasks() -> None:
    raw = """## Tasks
- add formatter
```
- [ ] should stay literal
```
"""
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    tasks = _extract_section(result["formatted_body"], "Tasks")

    assert "```" not in tasks
    assert "- [ ] add formatter" in tasks
    assert "should stay literal" not in tasks


def test_build_label_transition_matches_expected_labels() -> None:
    assert issue_formatter.build_label_transition() == {
        "add": ["agents:formatted"],
        "remove": ["agents:format"],
    }


def test_main_emits_json_with_labels(monkeypatch, capsys) -> None:
    expected_audit = "Task validation: 1 input → 1 output. All clean."
    real_format_issue_body = issue_formatter.format_issue_body
    monkeypatch.setattr(
        issue_formatter,
        "format_issue_body",
        lambda raw, use_llm=True: {
            "formatted_body": real_format_issue_body(raw, use_llm=False)["formatted_body"],
            "provider_used": None,
            "used_llm": False,
            "validation_audit": expected_audit,
            "needs_refinement": False,
        },
    )
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
    assert payload["validation_audit"] == expected_audit


def test_main_emits_formatter_error_without_refinement(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        issue_formatter,
        "format_issue_body",
        lambda raw, use_llm=True: {
            "error": "Issue body too large",
            "formatted_body": None,
            "provider_used": None,
            "used_llm": False,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["issue_formatter.py", "--input-text", "Raw issue", "--json", "--no-llm"],
    )

    issue_formatter.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["error"] == "Issue body too large"
    assert payload["needs_refinement"] is True


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


def test_format_issue_body_caps_oversized_input() -> None:
    """Issue #862 root cause: 135K char issue body exceeded 30K TPM limit.

    Shared issue/PR context assembly now caps oversized inputs before they hit
    LLM prompt construction.
    """
    # Create oversized input (>50K chars)
    oversized_body = "x" * 60000

    result = issue_formatter.format_issue_body(oversized_body, use_llm=False)

    assert result["used_llm"] is False
    assert result["formatted_body"] is not None
    assert len(result["formatted_body"]) < len(oversized_body)
    assert "context exceeded token budget" in result["formatted_body"]


# ---------------------------------------------------------------------------
# Anti-bloat: idempotency / byte-stability (incident #1127 -> #1135, ~78x)
# ---------------------------------------------------------------------------


def test_format_issue_twice_is_byte_stable() -> None:
    """Formatting an already-formatted body must NOT grow it.

    Re-running the formatter on its own output was the primary re-run
    amplification vector. A reuse marker + already-conformant guard now make the
    second pass a byte-stable no-op.
    """
    raw = (
        "Why: ship portfolio constraint validation\n\n"
        "Tasks:\n"
        "- Define common constraints (weight bounds, leverage, concentration)\n"
        "- Implement ConstraintValidator class\n"
        "- Add validation hooks in portfolio construction\n\n"
        "Acceptance:\n"
        "- tests pass\n"
    )
    first = issue_formatter.format_issue_body(raw, use_llm=False)["formatted_body"]
    second = issue_formatter.format_issue_body(first, use_llm=False)
    third = issue_formatter.format_issue_body(second["formatted_body"], use_llm=False)

    assert second["formatted_body"] == first  # byte-stable on re-format
    assert third["formatted_body"] == first  # and stays stable
    assert second["used_llm"] is False
    assert second.get("skipped") in {"reused_marker", "already_conformant"}


def test_format_issue_reuse_marker_written_and_honored() -> None:
    """A formatter output carries a reuse marker that later stages can detect."""
    raw = "Why: do it\n\nTasks:\n- add a thing\n\nAcceptance:\n- it works"
    formatted = issue_formatter.format_issue_body(raw, use_llm=False)["formatted_body"]

    assert "issue-pr-context:formatted-body" in formatted
    # The marker round-trips for any of the auto-pilot chain workflow tags.
    for workflow in ("agents-auto-pilot", "issue_optimizer"):
        assert (
            reuse_formatted_body({"body": formatted}, workflow) is not None
        ), f"marker should be reusable for {workflow}"


def test_format_issue_already_conformant_body_skipped() -> None:
    """A structurally conformant body (no marker) is detected and not re-formatted."""
    conformant = "\n".join(
        [
            "## Why",
            "",
            "Ship it.",
            "",
            "## Scope",
            "",
            "_Not provided._",
            "",
            "## Non-Goals",
            "",
            "_Not provided._",
            "",
            "## Tasks",
            "",
            "- [ ] do a thing",
            "",
            "## Acceptance Criteria",
            "",
            "- [ ] it works",
            "",
            "## Implementation Notes",
            "",
            "_Not provided._",
            "",
            "<details>",
            "<summary>Original Issue</summary>",
            "",
            "```text",
            "Why: ship it",
            "```",
            "</details>",
        ]
    )
    result = issue_formatter.format_issue_body(conformant, use_llm=False)
    assert result["skipped"] == "already_conformant"
    assert result["used_llm"] is False


def test_append_raw_issue_section_replaces_not_nests() -> None:
    """_append_raw_issue_section keeps exactly one Original-Issue block.

    Previously, when the formatted output already had a block but the raw source
    did not, a second block was nested (the #1135 nesting vector).
    """
    formatted_with_block = "\n".join(
        [
            "## Tasks",
            "",
            "- [ ] Task 1",
            "",
            "## Acceptance Criteria",
            "",
            "- [ ] Done",
            "",
            "<details>",
            "<summary>Original Issue</summary>",
            "",
            "```text",
            "TRUE ORIGINAL",
            "```",
            "</details>",
        ]
    )
    # Re-format case: format_issue_body passes the already-formatted body (block
    # and all) back in as issue_body. The block must be replaced once, not nested,
    # and the verbatim innermost original preserved.
    out = issue_formatter._append_raw_issue_section(formatted_with_block, formatted_with_block)
    assert out.count("<summary>Original Issue</summary>") == 1
    assert "TRUE ORIGINAL" in out

    # Edge: the formatted OUTPUT carries a block but the raw arg is empty. The
    # original is still recovered from the output rather than dropped or nested.
    out_empty_raw = issue_formatter._append_raw_issue_section(formatted_with_block, "")
    assert out_empty_raw.count("<summary>Original Issue</summary>") == 1
    assert "TRUE ORIGINAL" in out_empty_raw


def test_append_raw_issue_section_recovers_attributed_details_wrapper() -> None:
    formatted_with_block = """## Tasks

- [ ] `pytest tests/scripts/test_issue_formatter.py`

## Acceptance Criteria

- [ ] `pytest tests/scripts/test_issue_formatter.py` passes.

<details open>
<summary>Original Issue</summary>

```text
TRUE ORIGINAL
```
</details>
"""

    out = issue_formatter._append_raw_issue_section(formatted_with_block, formatted_with_block)

    assert out.count("<summary>Original Issue</summary>") == 1
    assert "TRUE ORIGINAL" in out


def test_append_raw_issue_section_collapses_nested_blocks() -> None:
    """Pre-existing nested blocks collapse to a single block on the next pass."""
    nested = "\n".join(
        [
            "## Tasks",
            "",
            "- [ ] x",
            "",
            "<details>",
            "<summary>Original Issue</summary>",
            "",
            "````text",
            "## Tasks",
            "- [ ] x",
            "",
            "<details>",
            "<summary>Original Issue</summary>",
            "",
            "```text",
            "TRUE ORIGINAL",
            "```",
            "</details>",
            "````",
            "</details>",
        ]
    )
    out = issue_formatter._append_raw_issue_section("## Tasks\n\n- [ ] x", nested)
    assert out.count("<summary>Original Issue</summary>") == 1
    assert out.count("TRUE ORIGINAL") == 1


def test_strip_original_issue_blocks_removes_balanced_nested_details() -> None:
    nested = """## Why

Keep this text.

<details>
<summary>Original Issue</summary>

````text
outer
<details>
<summary>Original Issue</summary>

```text
inner
```
</details>
````
</details>

## Scope

Keep this too.
"""

    stripped = issue_formatter._strip_original_issue_blocks(nested)

    assert "Keep this text." in stripped
    assert "Keep this too." in stripped
    assert "Original Issue" not in stripped
    assert "</details>" not in stripped


@pytest.mark.parametrize("marker", ["```", "~~~"])
def test_strip_original_issue_ignores_details_when_fence_close_has_trailing_text(
    marker: str,
) -> None:
    """A fence line with trailing junk must not resume HTML details counting."""
    payload = "\n".join(
        [
            "## Why",
            "",
            "Keep this text.",
            "",
            "<details>",
            "<summary>Original Issue</summary>",
            "",
            f"{marker}text",
            "literal <details>",
            f"{marker} still-inside",
            "literal </details>",
            marker,
            "</details>",
            "",
            "## Scope",
            "",
            "Keep this too.",
            "",
        ]
    )

    stripped = issue_formatter._strip_original_issue_blocks(payload)

    assert "Keep this text." in stripped
    assert "Keep this too." in stripped
    assert "Original Issue" not in stripped
    assert "literal <details>" not in stripped
    assert "</details>" not in stripped


@pytest.mark.parametrize("marker", ["```", "~~~"])
def test_strip_original_issue_keeps_same_line_details_inside_fence(marker: str) -> None:
    """Same-line HTML must not turn a closing-fence candidate structural."""
    payload = "\n".join(
        [
            "## Why",
            "",
            "Keep this text.",
            "",
            "<details>",
            "<summary>Original Issue</summary>",
            "",
            f"{marker}text",
            f"{marker}</details>",
            "still inside the fenced payload",
            marker,
            "</details>",
            "",
            "## Scope",
            "",
            "Keep this too.",
            "",
        ]
    )

    stripped = issue_formatter._strip_original_issue_blocks(payload)

    assert "Keep this text." in stripped
    assert "Keep this too." in stripped
    assert "Original Issue" not in stripped
    assert "still inside the fenced payload" not in stripped


def test_reuse_sets_needs_refinement_when_validator_fails() -> None:
    """Structurally conformant but contract-invalid bodies must not claim ready."""
    conformant = "\n".join(
        [
            "## Why",
            "",
            "Ship it.",
            "",
            "## Scope",
            "",
            "_Not provided._",
            "",
            "## Non-Goals",
            "",
            "_Not provided._",
            "",
            "## Tasks",
            "",
            "- [ ] do a thing",
            "",
            "## Acceptance Criteria",
            "",
            "- [ ] it works",
            "",
            "## Implementation Notes",
            "",
            "_Not provided._",
            "",
            "<details>",
            "<summary>Original Issue</summary>",
            "",
            "```text",
            "Why: ship it",
            "```",
            "</details>",
        ]
    )
    result = issue_formatter.format_issue_body(conformant, use_llm=False)
    assert result["skipped"] == "already_conformant"
    assert result["needs_refinement"] is True


def test_curl_requires_a_target_for_safe_verify_command() -> None:
    assert issue_formatter.SAFE_VERIFY_COMMAND_RE.match("curl") is None
    assert issue_formatter.SAFE_VERIFY_COMMAND_RE.match("curl /etc/passwd") is None
    assert issue_formatter.SAFE_VERIFY_COMMAND_RE.match("curl file:///etc/passwd") is None
    assert (
        issue_formatter.SAFE_VERIFY_COMMAND_RE.match(
            "curl https://example.test/health --output /tmp/result"
        )
        is None
    )
    assert (
        issue_formatter.SAFE_VERIFY_COMMAND_RE.match("curl https://example.test/health") is not None
    )
    assert (
        issue_formatter.SAFE_VERIFY_COMMAND_RE.match("curl http://example.test/health") is not None
    )


def test_safe_verify_command_rejects_trailing_unallowlisted_text() -> None:
    assert issue_formatter.SAFE_VERIFY_COMMAND_RE.match("pytest tests/test_x.py; curl bad") is None


def test_safe_verify_command_handles_tab_heavy_invalid_input_without_backtracking() -> None:
    hostile = "gh\trun\t!" + "\t\t" * 2_000 + ";"
    assert issue_formatter.SAFE_VERIFY_COMMAND_RE.match(hostile) is None


def test_append_raw_issue_recovers_tilde_fenced_original_issue() -> None:
    original = "TILDE-FENCED ORIGINAL"
    formatted = "\n".join(
        [
            "## Tasks",
            "",
            "- [ ] Keep the original body.",
            "",
            "<details>",
            "<summary>Original Issue</summary>",
            "",
            "~~~text",
            original,
            "~~~",
            "</details>",
        ]
    )

    output = issue_formatter._append_raw_issue_section(formatted, formatted)

    assert output.count("<summary>Original Issue</summary>") == 1
    assert original in output


def test_safe_verify_command_accepts_unittest_and_requires_gh_args() -> None:
    assert (
        issue_formatter.SAFE_VERIFY_COMMAND_RE.match("python -m unittest tests.test_x") is not None
    )
    assert issue_formatter.SAFE_VERIFY_COMMAND_RE.match("unittest") is not None
    assert issue_formatter.SAFE_VERIFY_COMMAND_RE.match("gh run") is None
    assert issue_formatter.SAFE_VERIFY_COMMAND_RE.match("gh workflow run") is None
    assert issue_formatter.SAFE_VERIFY_COMMAND_RE.match("gh run watch") is not None
    assert (
        issue_formatter.SAFE_VERIFY_COMMAND_RE.match("gh workflow run agents-issue-optimizer.yml")
        is not None
    )
