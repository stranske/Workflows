"""Behavioral coverage for pr_verifier diff path parsing helpers."""

from __future__ import annotations

import textwrap

import pytest
from scripts.langchain.pr_verifier import FileCoverage, PromptCoverage, _split_diff_files


def test_split_diff_files_parses_quoted_git_paths() -> None:
    diff = textwrap.dedent("""\
        diff --git "a/path with spaces.txt" "b/path with spaces.txt"
        --- "a/path with spaces.txt"
        +++ "b/path with spaces.txt"
        @@ -1 +1 @@
        -old
        +new
        """)
    files = _split_diff_files(diff)
    assert files == [("path with spaces.txt", diff)]


def test_split_diff_files_handles_rename_to_metadata() -> None:
    diff = textwrap.dedent("""\
        diff --git a/old_name.py b/old_name.py
        rename to src/new_name.py
        --- a/old_name.py
        +++ b/new_name.py
        @@ -1 +1 @@
        -x
        +y
        """)
    files = _split_diff_files(diff)
    assert files[0][0] == "new_name.py"


def test_split_diff_files_rejects_malformed_quoted_header() -> None:
    diff = textwrap.dedent("""\
        diff --git a/broken.txt b/broken.txt
        --- "unterminated
        +++ b/broken.txt
        @@ -1 +1 @@
        -a
        +b
        """)
    assert _split_diff_files(diff)[0][0] is None


def test_split_diff_files_handles_copy_to_metadata() -> None:
    diff = textwrap.dedent("""\
        diff --git a/old.py b/old.py
        copy to src/copied.py
        --- a/old.py
        +++ b/copied.py
        @@ -1 +1 @@
        -1
        +2
        """)
    assert _split_diff_files(diff)[0][0] == "copied.py"


def test_split_diff_files_treats_dev_null_as_empty_path() -> None:
    diff = textwrap.dedent("""\
        diff --git a/removed.txt b/removed.txt
        --- a/removed.txt
        +++ /dev/null
        @@ -1 +0,0 @@
        -gone
        """)
    assert _split_diff_files(diff)[0][0] == "removed.txt"


def test_prompt_coverage_render_lists_optional_omissions_and_many_partials() -> None:
    partial_files = tuple(
        FileCoverage(
            path=f"src/file_{index}.py", status="truncated", included_chars=1, total_chars=9
        )
        for index in range(41)
    )
    coverage = PromptCoverage(
        acceptance="complete",
        acceptance_evidence="complete",
        code="truncated",
        files=partial_files,
        code_included_chars=41,
        code_total_chars=369,
        context_truncated=False,
        reasons=("changed code incomplete",),
        omitted_optional_evidence_sections=("screenshots",),
        included_required_evidence_channels=("overall",),
    )
    rendered = coverage.render()
    assert "Optional evidence sections omitted" in rendered
    assert "screenshots" in rendered
    assert "... 1 more partial file(s)" in rendered
    assert "INCOMPLETE" in rendered


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ("", 4000),
        ("not-a-number", 4000),
        ("0", 4000),
        ("9000", 9000),
    ],
)
def test_budget_from_env_uses_positive_override(monkeypatch, env: str, expected: int) -> None:
    from scripts.langchain import pr_verifier

    monkeypatch.setenv("VERIFIER_CONTEXT_BUDGET_TOKENS", env)
    assert pr_verifier._budget_from_env("VERIFIER_CONTEXT_BUDGET_TOKENS", 4000) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("```python", ("```", False, 0)),
        ("    ```python", ("```", False, 4)),
        ("```python info", ("```", False, 0)),
        ("~~~", ("~~~", True, 0)),
        ("```", ("```", True, 0)),
    ],
)
def test_code_fence_marker_distinguishes_info_strings(line: str, expected) -> None:
    from scripts.langchain import pr_verifier

    assert pr_verifier._code_fence_marker(line) == expected


def test_summary_destination_paths_parses_encoded_and_plain_entries() -> None:
    from scripts.langchain import pr_verifier

    summary = "\n".join(
        [
            "### File changes",
            '- src/app.py (added) <!-- verifier-file-path:v1 "src/app.py" -->',
            "- docs/readme.md (+3/-1)",
        ]
    )
    assert pr_verifier._summary_destination_paths(summary) == ["src/app.py", "docs/readme.md"]


def test_summary_destination_paths_rejects_malformed_encoded_marker() -> None:
    from scripts.langchain import pr_verifier

    summary = "### File changes\n- broken <!-- verifier-file-path:v1 not-json -->"
    with pytest.raises(ValueError, match="Malformed encoded summary destination"):
        pr_verifier._summary_destination_paths(summary)


def test_summary_destination_paths_rejects_empty_encoded_destination() -> None:
    from scripts.langchain import pr_verifier

    summary = '### File changes\n- row <!-- verifier-file-path:v1 "" -->'
    with pytest.raises(ValueError, match="Empty or non-string encoded summary destination"):
        pr_verifier._summary_destination_paths(summary)
