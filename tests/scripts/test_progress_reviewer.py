from __future__ import annotations

import json
import subprocess
import sys

from scripts.langchain import progress_reviewer


def test_progress_reviewer_default_model_is_high_quality_mini():
    assert progress_reviewer.review_progress_with_llm.__defaults__ == ("gpt-5.4-mini",)
    assert progress_reviewer.review_progress.__defaults__ == (True, "gpt-5.4-mini")


def test_build_review_payload_includes_review_fields():
    result = progress_reviewer.review_progress(
        acceptance_criteria=["Add guard to progress review comments"],
        recent_commits=["chore: update progress reviewer"],
        files_changed=["scripts/langchain/progress_reviewer.py"],
        rounds_without_completion=2,
        use_llm=False,
    )

    payload = progress_reviewer.build_review_payload(result)
    review = payload.get("review")

    assert isinstance(review, dict)
    assert review["score"] == result.alignment_score
    assert review["feedback"] == result.feedback_for_agent
    assert "suggestions" in review


def test_json_output_contains_review_fields():
    result = progress_reviewer.review_progress(
        acceptance_criteria=[],
        recent_commits=[],
        files_changed=[],
        rounds_without_completion=0,
        use_llm=False,
    )

    payload = progress_reviewer.build_review_payload(result)
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert "review" in decoded
    assert set(decoded["review"].keys()) == {"score", "feedback", "suggestions"}


def test_heuristic_alignment_handles_snake_case_tokens():
    result = progress_reviewer.review_progress(
        acceptance_criteria=[
            "Running `render_cprs_ch_png(...)` generates PNGs without errors.",
        ],
        recent_commits=[
            "Define explicit CPRS-CH PNG column layout",
        ],
        files_changed=[
            "src/counter_risk/renderers/table_png.py",
        ],
        rounds_without_completion=22,
        use_llm=False,
    )

    assert result.alignment_score > 0
    assert result.recommendation != "STOP"


def test_cli_accumulates_repeated_flags(tmp_path):
    script = "scripts/langchain/progress_reviewer.py"
    proc = subprocess.run(
        [
            sys.executable,
            script,
            "--acceptance-criteria",
            "Criterion one",
            "--acceptance-criteria",
            "Criterion two",
            "--recent-commits",
            "commit one",
            "--recent-commits",
            "commit two",
            "--files-changed",
            "a.py",
            "--files-changed",
            "b.py",
            "--rounds-without-completion",
            "10",
            "--json",
            "--no-llm",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.stdout
    payload = json.loads(proc.stdout)
    assert "summary" in payload
    # The heuristic summary embeds the denominator; ensure it saw both commits.
    assert "/2 commits" in payload["summary"]


def test_filter_bookkeeping_files_strips_claude_artifacts():
    """_filter_bookkeeping_files removes Claude orchestrator artifacts."""
    files = [
        "src/app.py",
        "claude-output-170.md",
        "claude-prompt-170.md",
        "agents/claude-42.md",
        ".agents/foo",
        "src/utils.py",
    ]
    filtered = progress_reviewer._filter_bookkeeping_files(files)
    assert filtered == ["src/app.py", "src/utils.py"]


def test_filter_bookkeeping_files_strips_codex_artifacts():
    """_filter_bookkeeping_files removes Codex orchestrator artifacts."""
    files = [
        "src/main.rs",
        "codex-output-55.md",
        "codex-prompt-55.md",
        "claude-session-12.jsonl",
        "claude-analysis-12.json",
        "autofix-lint.patch",
    ]
    filtered = progress_reviewer._filter_bookkeeping_files(files)
    assert filtered == ["src/main.rs"]


def test_filter_bookkeeping_files_leaves_legit_autofix_names():
    """_filter_bookkeeping_files keeps real source files containing 'autofix'."""
    files = [
        "src/my-autofix-helper.py",
        "scripts/autofix-runner/autofix_pipeline.py",
        "autofix-lint.patch",
    ]
    filtered = progress_reviewer._filter_bookkeeping_files(files)
    # Only the orchestrator artifact (autofix-lint.patch) is removed.
    assert filtered == [
        "src/my-autofix-helper.py",
        "scripts/autofix-runner/autofix_pipeline.py",
    ]


def test_zero_source_stop_on_empty_files():
    """review_progress returns STOP when no files changed for 2+ rounds."""
    result = progress_reviewer.review_progress(
        acceptance_criteria=["Implement feature X"],
        recent_commits=["chore: setup"],
        files_changed=[],
        rounds_without_completion=3,
        use_llm=False,
    )
    assert result.recommendation == "STOP"
    assert result.alignment_score == 0.0
    assert "Zero" in result.summary or "zero" in result.summary.lower()


def test_zero_source_stop_when_only_bookkeeping_files():
    """review_progress returns STOP when all files are bookkeeping artifacts."""
    result = progress_reviewer.review_progress(
        acceptance_criteria=["Build the API"],
        recent_commits=["Update output"],
        files_changed=[
            "claude-output-99.md",
            "claude-prompt-99.md",
        ],
        rounds_without_completion=2,
        use_llm=False,
    )
    assert result.recommendation == "STOP"
    assert result.alignment_score == 0.0


def test_no_zero_source_stop_below_threshold():
    """review_progress does NOT stop for zero files if rounds < 2."""
    result = progress_reviewer.review_progress(
        acceptance_criteria=["Implement feature X"],
        recent_commits=["chore: setup"],
        files_changed=[],
        rounds_without_completion=1,
        use_llm=False,
    )
    assert result.recommendation != "STOP"


def test_review_progress_langsmith_trace_capture():
    """Test that LangSmith trace ID/URL are captured in review_progress_with_llm."""
    import json
    from unittest import mock

    from scripts.langchain.progress_reviewer import review_progress_with_llm

    # Create mock LLM client
    mock_llm = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.content = json.dumps(
        {
            "recommendation": "CONTINUE",
            "confidence": 0.9,
            "alignment_score": 8,
            "trajectory": "advancing",
            "analysis": {"prep_work_identified": ["Task 1 done"], "scope_drift_identified": []},
            "feedback_for_agent": "Good progress",
            "summary": "On track",
        }
    )
    mock_response.response_metadata = {"run_id": "review-trace-def456"}
    mock_llm.invoke.return_value = mock_response

    # Create mock resolved object with client, provider, and model
    mock_resolved = mock.MagicMock()
    mock_resolved.client = mock_llm
    mock_resolved.provider = "test-provider"
    mock_resolved.model = "test-model"

    with (
        mock.patch("scripts.langchain._llm_client.build_client", return_value=mock_resolved),
        mock.patch.dict("os.environ", {"LANGSMITH_API_KEY": "test-key"}),
    ):
        result = review_progress_with_llm(
            acceptance_criteria=["Must work"],
            recent_commits=["Did work"],
            files_changed=["file.py"],
            rounds_without_completion=1,
        )

    # Verify config was passed to invoke
    assert mock_llm.invoke.call_count == 1
    call_args = mock_llm.invoke.call_args
    assert "config" in call_args[1]

    # Assert trace fields are populated
    assert hasattr(result, "langsmith_trace_id")
    assert hasattr(result, "langsmith_trace_url")
    assert result.langsmith_trace_id == "review-trace-def456"
    assert "review-trace-def456" in result.langsmith_trace_url
