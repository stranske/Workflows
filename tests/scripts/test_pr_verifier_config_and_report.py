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
from scripts.langchain import pr_verifier
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


# ---------------------------------------------------------------------------------------------
# `main` — 43 unexercised statements, and the CLI every verifier run enters through.
#
# It reads `sys.argv` directly, so the tests set it. Everything that would reach an LLM or the
# GitHub API is stubbed; what is under test is the wiring around those calls, which is where the
# silent failures live.
# ---------------------------------------------------------------------------------------------


@pytest.fixture()
def clean_run_env(monkeypatch):
    for var in ("GITHUB_RUN_ID", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(var, raising=False)


def _stub_evaluation(monkeypatch, **kwargs):
    result = EvaluationResult(
        verdict=kwargs.pop("verdict", "CONCERNS"),
        summary=kwargs.pop("summary", "a summary"),
        raw_content=kwargs.pop("raw_content", "the raw content"),
        **kwargs,
    )
    monkeypatch.setattr(pr_verifier, "evaluate_pr", lambda *a, **k: result)
    return result


def _argv(monkeypatch, tmp_path, *args):
    """Always supply a context file.

    `_load_text(None)` reads STDIN, so a test that omits it hangs on the terminal rather than
    exercising anything — which is how the first draft of these failed with "reading from stdin
    while output is captured" instead of a real assertion.
    """
    context = tmp_path / "context.md"
    if not context.exists():
        context.write_text("Pull request: [#7](https://x/pull/7)\n", encoding="utf-8")
    monkeypatch.setattr(
        pr_verifier.sys, "argv", ["pr_verifier.py", "--context-file", str(context), *args]
    )


def test_a_failed_follow_up_issue_does_not_lose_the_evaluation(
    tmp_path, monkeypatch, capsys, clean_run_env
):
    """The contract that matters most here.

    Issue creation touches the GitHub API and can fail for reasons that have nothing to do with
    the verdict — rate limits, a missing token, a label that does not exist. If that took the run
    down, a transient API problem would discard a completed evaluation and the PR would show no
    result at all.
    """
    _stub_evaluation(monkeypatch)
    monkeypatch.setattr(
        pr_verifier,
        "_create_followup_issue",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rate limited")),
    )
    _argv(monkeypatch, tmp_path, "--create-issue")
    pr_verifier.main()
    captured = capsys.readouterr()
    assert "Failed to create follow-up issue: rate limited" in captured.err
    assert "the raw content" in captured.out, "the evaluation must still be reported"


def test_a_created_issue_is_announced_on_stderr_not_stdout(
    tmp_path, monkeypatch, capsys, clean_run_env
):
    """stdout is the evaluation payload; a caller piping it must not receive chatter."""
    _stub_evaluation(monkeypatch)
    monkeypatch.setattr(pr_verifier, "_create_followup_issue", lambda *a, **k: 4242)
    _argv(monkeypatch, tmp_path, "--create-issue")
    pr_verifier.main()
    captured = capsys.readouterr()
    assert "Created follow-up issue #4242." in captured.err
    assert "4242" not in captured.out


def test_the_default_issue_label_routes_to_an_agent(tmp_path, monkeypatch, clean_run_env):
    """A wrong default sends every follow-up to an agent that is not working the PR."""
    _stub_evaluation(monkeypatch)
    seen: dict = {}

    def capture(result, context, *, labels, run_url):
        seen["labels"] = labels
        return 1

    monkeypatch.setattr(pr_verifier, "_create_followup_issue", capture)
    _argv(monkeypatch, tmp_path, "--create-issue")
    pr_verifier.main()
    assert seen["labels"] == ["agent:codex"]


def test_explicit_labels_replace_the_default(tmp_path, monkeypatch, clean_run_env):
    _stub_evaluation(monkeypatch)
    seen: dict = {}
    monkeypatch.setattr(
        pr_verifier,
        "_create_followup_issue",
        lambda result, context, *, labels, run_url: seen.setdefault("labels", labels) and 1,
    )
    _argv(
        monkeypatch,
        tmp_path,
        "--create-issue",
        "--issue-label",
        "agent:claude",
        "--issue-label",
        "bug",
    )
    pr_verifier.main()
    assert seen["labels"] == ["agent:claude", "bug"]


def test_the_run_url_needs_every_part_or_none_of_it(tmp_path, monkeypatch, clean_run_env):
    """A half-built run URL is a dead link in an issue that outlives the run.

    Each variable is absent in a real context — locally none are set, and a workflow can carry
    some without the others — so a partial URL must be no URL rather than a broken one.
    """
    _stub_evaluation(monkeypatch)
    seen: dict = {}
    monkeypatch.setattr(
        pr_verifier,
        "_create_followup_issue",
        lambda result, context, *, labels, run_url: seen.setdefault("url", run_url) or 1,
    )
    monkeypatch.setenv("GITHUB_RUN_ID", "77")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    # GITHUB_REPOSITORY deliberately absent
    _argv(monkeypatch, tmp_path, "--create-issue")
    pr_verifier.main()
    assert seen["url"] is None


def test_a_complete_environment_builds_the_run_url(tmp_path, monkeypatch, clean_run_env):
    _stub_evaluation(monkeypatch)
    seen: dict = {}
    monkeypatch.setattr(
        pr_verifier,
        "_create_followup_issue",
        lambda result, context, *, labels, run_url: seen.setdefault("url", run_url) or 1,
    )
    monkeypatch.setenv("GITHUB_RUN_ID", "77")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    _argv(monkeypatch, tmp_path, "--create-issue")
    pr_verifier.main()
    assert seen["url"] == "https://github.com/stranske/Workflows/actions/runs/77"


def test_no_issue_is_created_without_the_flag(tmp_path, monkeypatch, clean_run_env):
    """Creating an issue is a side effect on a real repository; it must be opt-in."""
    _stub_evaluation(monkeypatch)

    def must_not_run(*a, **k):
        raise AssertionError("an issue was created without --create-issue")

    monkeypatch.setattr(pr_verifier, "_create_followup_issue", must_not_run)
    _argv(monkeypatch, tmp_path)
    pr_verifier.main()


def test_output_falls_back_from_raw_content_to_summary(
    tmp_path, monkeypatch, capsys, clean_run_env
):
    """An empty stdout would read as "the verifier said nothing" rather than "it had no raw text"."""
    _stub_evaluation(monkeypatch, raw_content=None, summary="only a summary")
    _argv(monkeypatch, tmp_path)
    pr_verifier.main()
    assert "only a summary" in capsys.readouterr().out


def test_the_output_file_receives_the_same_text_as_stdout(
    tmp_path, monkeypatch, capsys, clean_run_env
):
    _stub_evaluation(monkeypatch)
    out = tmp_path / "evaluation.md"
    _argv(monkeypatch, tmp_path, "--output-file", str(out))
    pr_verifier.main()
    printed = capsys.readouterr().out
    assert out.read_text(encoding="utf-8") == "the raw content"
    assert "the raw content" in printed


def test_json_mode_emits_a_parseable_payload(tmp_path, monkeypatch, capsys, clean_run_env):
    """Downstream steps parse stdout; prose in JSON mode strands them."""
    import json as _json

    _stub_evaluation(monkeypatch, verdict="FAIL")
    _argv(monkeypatch, tmp_path, "--json")
    pr_verifier.main()
    payload = _json.loads(capsys.readouterr().out.strip())
    assert payload["verdict"] == "FAIL"


def test_compare_mode_never_runs_the_single_provider_path(
    tmp_path, monkeypatch, capsys, clean_run_env
):
    """The two modes are exclusive. Running both would double every LLM call in the job."""

    def must_not_run(*a, **k):
        raise AssertionError("evaluate_pr ran in compare mode")

    monkeypatch.setattr(pr_verifier, "evaluate_pr", must_not_run)
    monkeypatch.setattr(
        pr_verifier,
        "evaluate_pr_multiple",
        lambda *a, **k: [EvaluationResult(verdict="PASS", summary="one")],
    )
    _argv(monkeypatch, tmp_path, "--compare")
    pr_verifier.main()
    assert "Provider Comparison Report" in capsys.readouterr().out
