"""`pr_verifier`'s LangSmith config fallback and its comparison report.

Ranked here by `escaped_defect_priority` — this module carries the third-most fix commits in the
repository — and `pr_verifier` had no test file naming it beyond a chain-depth check and an import
smoke test.

Two clusters, chosen because both are silent when wrong.

`_build_llm_config`'s ENTIRE fallback path was unexercised. It runs whenever `tools.llm_provider`
cannot be imported, which is the ordinary shape in a consumer repo that does not vendor it — so a
defect there mislabels every trace the fleet emits from those repos, and nothing fails.

`format_comparison_report`'s empty-results branch was unexercised too. Without it an empty run
renders a report with headings and no rows, which reads as "the providers agreed on nothing to
say" rather than "no provider answered".
"""

from __future__ import annotations

import pytest
from scripts.langchain.pr_verifier import (
    EvaluationResult,
    _build_llm_config,
    _extract_pr_metadata,
    format_comparison_report,
)


@pytest.fixture()
def no_llm_provider(monkeypatch):
    """Force the fallback by making `tools.llm_provider` unimportable.

    Patching the import machinery rather than deleting a module: the function imports INSIDE its
    body, so a `sys.modules` deletion alone would let a real import succeed on the next call.
    """
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def fake_import(name, *args, **kwargs):
        if name == "tools.llm_provider" or name.startswith("tools.llm_provider."):
            raise ImportError("simulated: consumer repo does not vendor tools/llm_provider")
        return real_import(name, *args, **kwargs)

    monkeypatch.setitem(
        __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__,
        "__import__",
        fake_import,
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "RUN_ID", "PR_NUMBER", "ISSUE_NUMBER"):
        monkeypatch.delenv(var, raising=False)


# -------------------------------------------------------------------------------------------
# The fallback config. Every assertion here is about a value that reaches LangSmith as a tag.
# -------------------------------------------------------------------------------------------


def test_the_fallback_names_the_repo_and_run_from_the_environment(no_llm_provider, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    config = _build_llm_config(operation="verify", pr_number=7)
    assert config["metadata"]["repo"] == "stranske/Workflows"
    assert config["metadata"]["run_id"] == "12345"
    assert "repo:stranske/Workflows" in config["tags"]
    assert "run_id:12345" in config["tags"]


def test_unknown_is_used_when_the_environment_says_nothing(no_llm_provider):
    """`unknown` is a stated absence. An empty string would render as a tag with no value."""
    config = _build_llm_config(operation="verify")
    assert config["metadata"]["repo"] == "unknown"
    assert config["metadata"]["run_id"] == "unknown"
    assert config["metadata"]["issue_or_pr_number"] == "unknown"


def test_run_id_falls_back_to_the_unprefixed_variable(no_llm_provider, monkeypatch):
    """`RUN_ID` is what several consumer workflows set; only reading `GITHUB_RUN_ID` loses them."""
    monkeypatch.setenv("RUN_ID", "999")
    assert _build_llm_config(operation="verify")["metadata"]["run_id"] == "999"


def test_github_run_id_wins_over_the_unprefixed_one(no_llm_provider, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "111")
    monkeypatch.setenv("RUN_ID", "222")
    assert _build_llm_config(operation="verify")["metadata"]["run_id"] == "111"


def test_an_explicit_pr_number_wins_over_an_issue_number(no_llm_provider):
    """Both can be present; tagging the trace with the wrong one misfiles it."""
    config = _build_llm_config(operation="verify", pr_number=7, issue_number=9)
    assert config["metadata"]["issue_or_pr_number"] == "7"
    assert config["metadata"]["pr_number"] == "7"
    assert config["metadata"]["issue_number"] == "9"


def test_an_issue_number_is_used_when_no_pr_number_is_given(no_llm_provider):
    config = _build_llm_config(operation="verify", issue_number=9)
    assert config["metadata"]["issue_or_pr_number"] == "9"
    assert config["metadata"]["pr_number"] is None


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"PR_NUMBER": "12"}, "12"),
        ({"ISSUE_NUMBER": "34"}, "34"),
        ({"PR_NUMBER": "12", "ISSUE_NUMBER": "34"}, "12"),
        # NON-NUMERIC IS REJECTED, not passed through. A tag reading `issue_or_pr:refs/heads/main`
        # would look like a real identifier and group unrelated traces together.
        ({"PR_NUMBER": "refs/heads/main"}, "unknown"),
        ({"PR_NUMBER": "", "ISSUE_NUMBER": ""}, "unknown"),
        ({"PR_NUMBER": "not-a-number", "ISSUE_NUMBER": "34"}, "34"),
    ],
)
def test_the_environment_numbers_are_validated_before_use(
    no_llm_provider, monkeypatch, env, expected
):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config = _build_llm_config(operation="verify")
    assert config["metadata"]["issue_or_pr_number"] == expected


def test_a_pr_number_is_recovered_from_the_context_when_not_passed(no_llm_provider):
    """The context is what the workflow has; requiring the caller to parse it duplicates this."""
    context = "Pull request: [#42](https://github.com/o/r/pull/42)\n"
    config = _build_llm_config(operation="verify", context=context)
    assert config["metadata"]["issue_or_pr_number"] == "42"


def test_the_operation_is_always_tagged(no_llm_provider):
    """Traces are grouped by operation; an untagged one is invisible in every per-op view."""
    config = _build_llm_config(operation="compare")
    assert config["metadata"]["operation"] == "compare"
    assert "operation:compare" in config["tags"]
    assert "workflows-agents" in config["tags"]


# -------------------------------------------------------------------------------------------
# Context parsing, which feeds the above.
# -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "context, number, url",
    [
        ("Pull request: [#42](https://x/pull/42)", 42, "https://x/pull/42"),
        ("Pull request: #42", 42, None),
        ("Pull request: none here", None, None),
        ("", None, None),
        ("Issue: #42", None, None),
    ],
)
def test_pr_metadata_is_read_only_from_a_pull_request_line(context, number, url):
    assert _extract_pr_metadata(context) == (number, url)


# -------------------------------------------------------------------------------------------
# The report. An empty run must not render as a comparison.
# -------------------------------------------------------------------------------------------


def test_no_results_says_so_rather_than_rendering_an_empty_comparison():
    report = format_comparison_report([])
    assert "No evaluation results available." in report
    assert "| Provider | Model |" not in report, (
        "an empty run must not render a comparison table; a report with headings and no rows "
        "reads as agreement rather than as absence"
    )


def test_a_single_provider_is_reported_as_not_compared():
    """One provider is not a comparison, and presenting it as one overstates the evidence."""
    report = format_comparison_report([EvaluationResult(verdict="PASS", summary="fine")])
    assert "Only one provider was available; comparison skipped." in report


def test_an_errored_provider_shows_its_error():
    """An error rendered as a blank cell is indistinguishable from a provider that had nothing
    to say."""
    results = [
        EvaluationResult(verdict="PASS", model="m1", summary="ok"),
        EvaluationResult(verdict="FAIL", model="m2", error="rate limited"),
    ]
    report = format_comparison_report(results)
    assert "- **Error:** rate limited" in report


def test_the_model_is_named_in_the_details_when_known():
    report = format_comparison_report(
        [
            EvaluationResult(verdict="PASS", model="claude-x", summary="a"),
            EvaluationResult(verdict="PASS", model="gemini-y", summary="b"),
        ]
    )
    assert "- **Model:** claude-x" in report
    assert "- **Model:** gemini-y" in report
