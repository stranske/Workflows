#!/usr/bin/env python3
"""Tests for followup_issue_generator.py"""

import json
import logging
import sys
from types import ModuleType, SimpleNamespace

import pytest
from scripts.langchain import followup_issue_generator
from scripts.langchain.followup_issue_generator import (
    OriginalIssueData,
    VerificationData,
    _select_followup_acceptance_criteria,
    extract_original_issue_data,
    extract_verification_data,
    generate_disposition_comment,
    generate_followup_issue,
    generate_issue_disposition_link_comment,
)


def test_select_followup_acceptance_criteria_drops_workflow_sync_items() -> None:
    original_issue = OriginalIssueData(
        title="Database verifier follow-up",
        number=42,
        tasks=[],
        acceptance_criteria=[
            "Database migrations preserve existing records",
            "Workflow template sync PRs are merged across consumers",
            "Pension report rows remain queryable after import",
        ],
    )
    verification_data = VerificationData(concerns=["Database rows were not preserved"])

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == [
        "Database migrations preserve existing records",
        "Pension report rows remain queryable after import",
    ]


def test_budget_followup_tasks_reserves_prompt_overhead(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(followup_issue_generator, "EVAL_FOLLOW_UP_BUDGET_TOKENS", 10)
    monkeypatch.setattr(
        followup_issue_generator,
        "estimate_tokens",
        lambda value: 1 if "first" in value else 10,
    )

    selected = followup_issue_generator._budget_followup_tasks(["first task", "second task"])

    assert selected == ["first task"]


def test_budget_followup_tasks_truncates_single_oversized_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(followup_issue_generator, "EVAL_FOLLOW_UP_BUDGET_TOKENS", 40)
    monkeypatch.setattr(
        followup_issue_generator,
        "estimate_tokens",
        lambda value: max(1, len(value) // 4),
    )

    selected = followup_issue_generator._budget_followup_tasks(["x" * 500])

    assert len(selected) == 1
    assert selected[0].endswith("...")
    assert len(selected[0]) < 500


def test_select_followup_acceptance_criteria_keeps_workflow_items_for_workflow_feedback() -> None:
    original_issue = OriginalIssueData(
        title="Mixed verifier follow-up",
        number=44,
        tasks=[],
        acceptance_criteria=[
            "Database migrations preserve existing records",
            "Workflow template sync PRs are merged across consumers",
        ],
    )
    verification_data = VerificationData(
        concerns=["Workflow template sync acceptance was not satisfied"]
    )

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == original_issue.acceptance_criteria


def test_select_followup_acceptance_criteria_keeps_workflow_items_for_sync_context_feedback() -> (
    None
):
    original_issue = OriginalIssueData(
        title="Mixed sync follow-up",
        number=52,
        tasks=[],
        acceptance_criteria=[
            "Workflow template sync PRs are merged across consumers",
            "Database migrations preserve existing records",
        ],
    )
    verification_data = VerificationData(
        concerns=["Consumer sync output is not synced in generated repos"]
    )

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == original_issue.acceptance_criteria


def test_select_followup_acceptance_criteria_accepts_plain_list() -> None:
    criteria = [
        "Workflows-owned scripts in Pension-Data stay synced",
        "Imported records keep their account IDs",
    ]
    verification_data = VerificationData(concerns=["Imported records lost account IDs"])

    selected = _select_followup_acceptance_criteria(criteria, verification_data)

    assert selected == ["Imported records keep their account IDs"]


def test_select_followup_acceptance_criteria_detects_workflow_file_markers() -> None:
    original_issue = OriginalIssueData(
        title="Workflow path rollout",
        number=46,
        tasks=[],
        acceptance_criteria=[
            "Update .github/workflows/agents-verifier.yml from the template",
            "The dashboard export renders for the selected account",
        ],
    )
    verification_data = VerificationData(concerns=["The dashboard export failed"])

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == ["The dashboard export renders for the selected account"]


def test_select_followup_acceptance_criteria_detects_workflow_dir_without_slash() -> None:
    original_issue = OriginalIssueData(
        title="Workflow path rollout",
        number=47,
        tasks=[],
        acceptance_criteria=[
            "Changes under .github/workflows are synced to consumers",
            "The dashboard export renders for the selected account",
        ],
    )
    verification_data = VerificationData(concerns=["The dashboard export failed"])

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == ["The dashboard export renders for the selected account"]


def test_select_followup_acceptance_criteria_detects_synced_scripts() -> None:
    original_issue = OriginalIssueData(
        title="Script rollout",
        number=48,
        tasks=[],
        acceptance_criteria=[
            "Synced .github/scripts helpers are updated across consumers",
            "The dashboard export renders for the selected account",
        ],
    )
    verification_data = VerificationData(concerns=["The dashboard export failed"])

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == ["The dashboard export renders for the selected account"]


def test_select_followup_acceptance_criteria_detects_synced_actions() -> None:
    original_issue = OriginalIssueData(
        title="Action rollout",
        number=49,
        tasks=[],
        acceptance_criteria=[
            "Synced .github/actions helpers are updated across consumers",
            "The dashboard export renders for the selected account",
        ],
    )
    verification_data = VerificationData(concerns=["The dashboard export failed"])

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == ["The dashboard export renders for the selected account"]


def test_select_followup_acceptance_criteria_keeps_repo_local_actions() -> None:
    original_issue = OriginalIssueData(
        title="Repo-local action",
        number=50,
        tasks=[],
        acceptance_criteria=[
            "The repo-local .github/actions/build-dashboard action handles missing config",
            "The dashboard export renders for the selected account",
        ],
    )
    verification_data = VerificationData(concerns=["The dashboard export failed"])

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == original_issue.acceptance_criteria


def test_select_followup_acceptance_criteria_keeps_repo_local_workflow_file_items() -> None:
    original_issue = OriginalIssueData(
        title="Repo-local workflow",
        number=52,
        tasks=[],
        acceptance_criteria=[
            "The workflow file in this repo handles nightly dashboard exports",
            "The dashboard export renders for the selected account",
        ],
    )
    verification_data = VerificationData(concerns=["The dashboard export failed"])

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == original_issue.acceptance_criteria


def test_select_followup_acceptance_criteria_keeps_explicit_sync_pr_items() -> None:
    original_issue = OriginalIssueData(
        title="Workflow sync rollout",
        number=53,
        tasks=[],
        acceptance_criteria=[
            "The sync PR is opened in this repo for workflow template sync",
            "The dashboard export renders for the selected account",
        ],
    )
    verification_data = VerificationData(concerns=["The dashboard export failed"])

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == ["The dashboard export renders for the selected account"]


def test_select_followup_acceptance_criteria_treats_workflow_paths_as_sync_by_default() -> None:
    original_issue = OriginalIssueData(
        title="Workflow path rollout",
        number=51,
        tasks=[],
        acceptance_criteria=[
            "Update .github/scripts/sync_tracker_state for tracker reuse",
            "The dashboard export renders for the selected account",
        ],
    )
    verification_data = VerificationData(concerns=["The dashboard export failed"])

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == ["The dashboard export renders for the selected account"]


def test_select_followup_acceptance_criteria_keeps_repo_local_agent_items() -> None:
    original_issue = OriginalIssueData(
        title="Repo-local agent UI",
        number=45,
        tasks=[],
        acceptance_criteria=[
            "The portal UI can reopen saved workflow state after refresh",
            "Update .github/agents/registry.yml with repo-local agent config",
        ],
    )
    verification_data = VerificationData(concerns=["The portal did not reopen saved state"])

    selected = _select_followup_acceptance_criteria(original_issue, verification_data)

    assert selected == original_issue.acceptance_criteria


def test_build_why_section_explains_mixed_surface_deemphasis() -> None:
    original_issue = OriginalIssueData(
        title="Mixed rollout",
        number=43,
        tasks=[],
        acceptance_criteria=[
            "Workflow template sync PRs are merged across consumers",
            "Database exports include the new field",
        ],
    )
    verification_data = VerificationData(
        provider_verdicts={"openai": {"verdict": "CONCERNS", "confidence": 70}},
        concerns=["Database export omitted the new field"],
    )

    why = followup_issue_generator._build_why_section(
        verification_data,
        original_issue,
        pr_number=99,
        verdict="CONCERNS",
    )

    assert "Workflow-sync acceptance criteria were de-emphasized" in why


class TestExtractVerificationData:
    """Tests for extract_verification_data function."""

    def test_extract_provider_verdicts_comparison_format(self):
        """Extract verdicts from comparison table format."""
        comment = """
## PR Verification Comparison

| Provider | Model | Verdict | Confidence |
|----------|-------|---------|------------|
| openai | gpt-4o | Not Ready | 45% |
| anthropic | claude-3.5-sonnet | Needs Work | 60% |
"""
        data = extract_verification_data(comment)

        assert "openai" in data.provider_verdicts
        assert data.provider_verdicts["openai"]["verdict"] == "Not Ready"
        assert data.provider_verdicts["openai"]["confidence"] == 45

        assert "anthropic" in data.provider_verdicts
        assert data.provider_verdicts["anthropic"]["verdict"] == "Needs Work"

    def test_extract_provider_verdicts_normalizes_provider_and_confidence(self):
        """Normalize provider labels and parse fractional confidence values."""
        comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai/gpt-5.2 | gpt-5.2 | CONCERNS | 0.72 | Needs follow-up. |
| anthropic/claude-sonnet-4-5 | claude-sonnet-4-5 | PASS | 92% | Looks good. |
"""
        data = extract_verification_data(comment)

        assert "openai" in data.provider_verdicts
        assert data.provider_verdicts["openai"]["verdict"] == "CONCERNS"
        assert data.provider_verdicts["openai"]["confidence"] == 72
        assert "anthropic" in data.provider_verdicts
        assert data.provider_verdicts["anthropic"]["confidence"] == 92
        assert data.non_pass_output == [
            "Provider=openai; Model=gpt-5.2; Verdict=CONCERNS; Confidence=72%"
        ]
        assert data.non_pass_findings == [
            "Provider=openai; Verdict=CONCERNS; Difference=Needs follow-up."
        ]

    def test_extract_provider_verdicts_prefers_percent_confidence(self):
        """Parse percent-bearing confidence when mixed numeric formats appear."""
        comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5 | FAIL | 0.61 (61%) | Regression |
"""

        data = extract_verification_data(comment)

        assert data.provider_verdicts["openai"]["confidence"] == 61
        assert data.non_pass_output == [
            "Provider=openai; Model=gpt-5; Verdict=FAIL; Confidence=61%"
        ]

    def test_generate_disposition_comment_includes_evidence_decision_and_rationale(self):
        comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5 | FAIL | 60% | Regression in parsing |
"""
        verification_data = extract_verification_data(comment)

        disposition = generate_disposition_comment(verification_data, pr_number=49)

        assert "## verify:compare Disposition" in disposition
        assert "Source: verify:compare non-PASS output from PR #49" in disposition
        assert "`Provider=openai; Model=gpt-5; Verdict=FAIL; Confidence=60%`" in disposition
        assert "non-PASS output requires code changes: **yes**" in disposition
        assert "technical rationale: Difference describes a functional defect" in disposition

    def test_generate_disposition_comment_includes_source_link_when_provided(self):
        comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5 | CONCERNS | 74% | Missing edge case |
"""
        verification_data = extract_verification_data(comment)

        disposition = generate_disposition_comment(
            verification_data,
            pr_number=49,
            source_url="https://github.com/stranske/Workflows/pull/49#issuecomment-123",
        )

        assert "Source: verify:compare non-PASS output from PR #49" in disposition
        assert (
            "Source link: https://github.com/stranske/Workflows/pull/49#issuecomment-123"
            in disposition
        )

    def test_generate_issue_disposition_link_comment_includes_url(self):
        body = generate_issue_disposition_link_comment(
            disposition_url="https://github.com/stranske/Workflows/pull/49#issuecomment-123"
        )

        assert "Disposition documentation for verify:compare is recorded here" in body
        assert "https://github.com/stranske/Workflows/pull/49#issuecomment-123" in body

    def test_non_pass_evidence_backfills_from_provider_detail_sections(self):
        comment = """
## Provider Comparison Report

#### openai
- **Verdict:** FAIL
- **Confidence:** 61%
"""

        data = extract_verification_data(comment)

        assert data.non_pass_output == ["Provider=openai; Model=; Verdict=FAIL; Confidence=61%"]

    def test_non_pass_evidence_handles_unknown_confidence(self):
        data = VerificationData(
            provider_verdicts={
                "openai": {"model": "gpt-5", "verdict": "FAIL", "confidence": "Unknown"}
            }
        )

        followup_issue_generator._refresh_non_pass_evidence(data)

        assert data.non_pass_output == ["Provider=openai; Model=gpt-5; Verdict=FAIL; Confidence=0%"]

    def test_non_pass_evidence_keeps_integer_confidence_percent(self):
        data = VerificationData(
            provider_verdicts={"openai": {"model": "gpt-5", "verdict": "FAIL", "confidence": 1}}
        )

        followup_issue_generator._refresh_non_pass_evidence(data)

        assert data.non_pass_output == ["Provider=openai; Model=gpt-5; Verdict=FAIL; Confidence=1%"]

    def test_generate_disposition_comment_caps_findings(self):
        verification_data = VerificationData(
            provider_verdicts={
                f"provider-{index}": {
                    "model": f"model-{index}",
                    "verdict": "FAIL",
                    "confidence": 50,
                    "summary": f"Regression {index}",
                }
                for index in range(12)
            }
        )
        followup_issue_generator._refresh_non_pass_evidence(verification_data)

        disposition = generate_disposition_comment(verification_data, pr_number=49)

        assert "Provider=provider-9; Verdict=FAIL; Difference=Regression 9" in disposition
        assert "Provider=provider-10; Verdict=FAIL; Difference=Regression 10" not in disposition
        assert "... plus 2 more findings" in disposition

    def test_generate_followup_issue_caps_non_pass_output_entries(self):
        verification_data = VerificationData(
            provider_verdicts={
                f"provider-{index}": {
                    "model": f"model-{index}",
                    "verdict": "FAIL",
                    "confidence": 50,
                    "summary": f"Regression {index}",
                }
                for index in range(12)
            },
            concerns=["Regression in parser behavior"],
        )
        followup_issue_generator._refresh_non_pass_evidence(verification_data)
        original_issue = OriginalIssueData(title="Issue title", number=92)

        followup = generate_followup_issue(
            verification_data,
            original_issue,
            pr_number=49,
            use_llm=False,
        )

        assert "Provider=provider-9; Model=model-9; Verdict=FAIL; Confidence=50%" in followup.body
        assert "Provider=provider-10; Model=model-10; Verdict=FAIL; Confidence=50%" not in (
            followup.body
        )
        assert "... plus 2 more evidence entries" in followup.body

    def test_extract_provider_verdicts_comparison_report_summary(self):
        """Extract verdicts from Provider Comparison Report format."""
        comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| github-models | gpt-4o | PASS | 80% | Looks good overall. |
| openai | gpt-4o-mini | Needs Work | N/A | Missing tests. |

<details>
<summary>Full Provider Details (click to expand)</summary>

#### github-models
- **Model:** gpt-4o
- **Verdict:** PASS
- **Confidence:** 80%

#### openai
- **Model:** gpt-4o-mini
- **Verdict:** Needs Work
- **Confidence:** 60%

</details>
"""
        data = extract_verification_data(comment)

        assert "github-models" in data.provider_verdicts
        assert data.provider_verdicts["github-models"]["verdict"] == "PASS"
        assert data.provider_verdicts["github-models"]["confidence"] == 80

        assert "openai" in data.provider_verdicts
        assert data.provider_verdicts["openai"]["verdict"] == "Needs Work"
        assert data.provider_verdicts["openai"]["confidence"] == 60

    def test_extract_provider_summary_adds_non_pass_summary_to_concerns(self):
        """Use non-PASS provider summaries as fallback concerns."""
        comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-4o-mini | CONCERNS | 72% | Missing regression coverage. |
| anthropic | claude-sonnet | PASS | 91% | Looks good. |
"""
        data = extract_verification_data(comment)

        assert "Missing regression coverage." in data.concerns
        assert data.provider_verdicts["openai"]["summary"] == "Missing regression coverage."

    def test_extract_non_pass_without_summary_marks_missing_concerns(self):
        """Non-PASS provider verdicts without summaries still produce a deterministic task."""
        comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence |
| --- | --- | --- | --- |
| openai | gpt-4o-mini | CONCERNS | 72% |
| anthropic | claude-sonnet | PASS | 91% |
"""
        data = extract_verification_data(comment)

        assert data.missing_concerns is True
        assert data.concerns == [
            "Verification output did not include extractable concerns; "
            "re-run verification to capture verifier-context.md and verifier-diff-summary.md."
        ]

    def test_extract_single_verdict(self):
        """Extract verdict from single provider format."""
        comment = """
## PR Verification Report

Verdict: **Not Ready** @75%
"""
        data = extract_verification_data(comment)

        assert "default" in data.provider_verdicts
        assert data.provider_verdicts["default"]["verdict"] == "Not Ready"

    def test_extract_single_verdict_fractional_confidence(self):
        """Extract fractional confidence from single provider format."""
        comment = """
## PR Verification Report

Verdict: **CONCERNS** @0.72
"""
        data = extract_verification_data(comment)

        assert "default" in data.provider_verdicts
        assert data.provider_verdicts["default"]["confidence"] == 72

    def test_extract_concerns(self):
        """Extract concerns list."""
        comment = """
### Concerns

- Missing test coverage for edge cases
- Error handling not comprehensive
- Documentation needs update
"""
        data = extract_verification_data(comment)

        assert len(data.concerns) == 3
        assert "Missing test coverage for edge cases" in data.concerns
        assert "Error handling not comprehensive" in data.concerns

    def test_extract_concerns_heading_variants(self):
        """Extract concerns from alternate heading levels."""
        comment = """
## Concerns from Verification

- Missing unit tests for edge cases
- Error handling needs improvement
"""
        data = extract_verification_data(comment)

        assert len(data.concerns) == 2
        assert "Missing unit tests for edge cases" in data.concerns
        assert "Error handling needs improvement" in data.concerns

    def test_extract_concerns_label_format(self):
        """Extract concerns from plain label + bullets."""
        comment = """
Concerns:
- Coverage gap in workflow_health_check.py
- Missing tests for error classification
"""
        data = extract_verification_data(comment)

        assert len(data.concerns) == 2
        assert "Coverage gap in workflow_health_check.py" in data.concerns
        assert "Missing tests for error classification" in data.concerns

    def test_extract_missing_concerns_for_unknown_verdict(self):
        """Add a default concern when verdict is unknown and concerns are missing."""
        comment = """
## PR Verification Report

Verdict: **Unknown** @0%
"""
        data = extract_verification_data(comment)

        assert data.concerns == [
            "Verification output did not include extractable concerns; "
            "re-run verification to capture verifier-context.md and verifier-diff-summary.md."
        ]
        assert data.missing_concerns is True

    def test_extract_missing_concerns_for_error_verdict(self):
        """Add a default concern when verifier crashes report an error verdict."""
        comment = """
## PR Verification Report

Verdict: **Error** @0%
"""
        data = extract_verification_data(comment)

        assert data.concerns == [
            "Verification output did not include extractable concerns; "
            "re-run verification to capture verifier-context.md and verifier-diff-summary.md."
        ]
        assert data.missing_concerns is True

    def test_extract_low_scores(self):
        """Extract scores below 7/10."""
        comment = """
| Category | Score |
|----------|-------|
| Completeness: 8/10
| Quality: 5/10
| Testing: 4/10
| Performance: 9/10
"""
        data = extract_verification_data(comment)

        assert "Quality" in data.low_scores
        assert data.low_scores["Quality"] == 5
        assert "Testing" in data.low_scores
        assert data.low_scores["Testing"] == 4
        assert "Completeness" not in data.low_scores  # 8 >= 7

    def test_extract_iteration_count(self):
        """Extract agent iteration count."""
        comment = """
Agent ran 5 iterations before completion.
"""
        data = extract_verification_data(comment)
        assert data.iteration_count == 5


def test_main_guard_blocks_llm(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    injection_samples: list[dict[str, str]],
) -> None:
    raw = injection_samples[0]["text"]

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("LLM should not be invoked when guard blocks input.")

    monkeypatch.setattr(followup_issue_generator, "generate_followup_issue", _fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "followup_issue_generator.py",
            "--pr-number",
            "123",
            "--verification-comment",
            raw,
            "--original-issue",
            "Original issue body",
            "--json",
        ],
    )

    exit_code = followup_issue_generator.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out.strip())
    assert payload["guard_blocked"] is True
    assert payload["guard_reason"]


def test_guard_blocked_followup_structure(
    injection_samples: list[dict[str, str]],
) -> None:
    """Verify the generated guard-blocked follow-up meets documented requirements."""
    from scripts.langchain.followup_issue_generator import _generate_guard_blocked_followup

    followup = _generate_guard_blocked_followup(
        pr_number=42,
        original_issue_number=100,
        original_issue_title="Test issue title",
        guard_reason="INSTRUCTION_OVERRIDE: test reason",
    )

    # Title format
    assert "PR #42" in followup.title
    assert "Human review" in followup.title

    # Body structure: must contain Why, Source, Tasks, Acceptance Criteria sections
    assert "## Why" in followup.body
    assert "## Source" in followup.body
    assert "## Tasks" in followup.body
    assert "## Acceptance Criteria" in followup.body
    assert "## Implementation Notes" in followup.body

    # Body references
    assert "#42" in followup.body  # PR number
    assert "#100" in followup.body  # original issue number
    assert "Test issue title" in followup.body

    # Guard reason mention
    assert "INSTRUCTION_OVERRIDE" in followup.body

    # Labels match workflow expected schema
    assert "needs-human" in followup.labels
    assert "agents:auto-pilot-pause" in followup.labels


def test_guard_blocked_followup_labels_match_workflow_schema() -> None:
    """Labels on guard-blocked followup must match what auto-pilot expects."""
    from scripts.langchain.followup_issue_generator import _generate_guard_blocked_followup

    followup = _generate_guard_blocked_followup(
        pr_number=1,
        original_issue_number=None,
        original_issue_title=None,
        guard_reason="test",
    )

    # These are the exact labels the auto-pilot workflow checks
    assert set(followup.labels) == {"needs-human", "agents:auto-pilot-pause"}

    # Unknown issue fields handled gracefully
    assert "unknown" in followup.body


def test_extract_task_completion():
    """Extract task completion stats."""
    comment = """
Remaining unchecked items: 3 of 10
"""
    data = extract_verification_data(comment)
    assert data.tasks_attempted == 10
    assert data.tasks_completed == 7


def test_extract_structural_issues():
    """Extract structural issues detected."""
    comment = """
### ⚠️ Issues Detected in Issue Structure

**Problem:** Tasks contain code snippets instead of actionable items

- Example: `def foo(): pass`
"""
    data = extract_verification_data(comment)

    assert len(data.structural_issues) >= 1
    assert any("code snippets" in issue.lower() for issue in data.structural_issues)


def test_get_llm_client_defaults_to_expected_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standard and reasoning follow-up paths should use the documented defaults."""

    calls: list[tuple[str | None, str | None]] = []

    def fake_build_chat_client(*, model: str | None = None, provider: str | None = None):
        calls.append((model, provider))
        return SimpleNamespace(
            client=object(), model=model or "fallback", provider=provider or "auto"
        )

    fake_module = ModuleType("tools.langchain_client")
    fake_module.build_chat_client = fake_build_chat_client

    monkeypatch.setitem(sys.modules, "tools.langchain_client", fake_module)
    monkeypatch.delenv("FOLLOWUP_MODEL", raising=False)
    monkeypatch.delenv("FOLLOWUP_REASONING_MODEL", raising=False)

    standard_client = followup_issue_generator._get_llm_client(reasoning=False)
    reasoning_client = followup_issue_generator._get_llm_client(reasoning=True)

    assert standard_client is not None
    assert reasoning_client is not None
    assert standard_client[1] == "gpt-5.4"
    assert reasoning_client[1] == "o3-mini"
    assert calls == [("gpt-5.4", None), ("o3-mini", "openai")]


class TestExtractOriginalIssueData:
    """Tests for extract_original_issue_data function."""

    def test_extract_sections(self):
        """Extract all standard sections."""
        issue_body = """
## Why

This feature improves user experience by reducing load times.

## Scope

Update the caching layer to use Redis.

## Tasks

- [ ] Install Redis client library
- [ ] Configure connection pooling
- [x] Add environment variables

## Acceptance Criteria

- [ ] Response time < 100ms for cached items
- [ ] Cache hit rate > 90%

## Implementation Notes

Use the `redis-py` library version 4.x.
"""
        data = extract_original_issue_data(issue_body, issue_number=123, title="Test Issue")

        assert data.number == 123
        assert data.title == "Test Issue"
        assert "improves user experience" in data.why
        assert "caching layer" in data.scope
        assert len(data.tasks) == 3
        assert len(data.acceptance_criteria) == 2
        assert "redis-py" in data.implementation_notes

    def test_extract_tasks_with_checkboxes(self):
        """Extract tasks from various checkbox formats."""
        issue_body = """
## Tasks

- [ ] Task with dash
* [ ] Task with asterisk
+ [ ] Task with plus
- [x] Completed task
"""
        data = extract_original_issue_data(issue_body)

        assert len(data.tasks) == 4
        assert "Task with dash" in data.tasks
        assert "Task with asterisk" in data.tasks

    def test_extract_tasks_without_list_marker(self):
        """Extract tasks and acceptance criteria without list markers."""
        issue_body = """
## Tasks

[ ] Task without dash
[x] Completed task without dash

## Acceptance Criteria

[ ] Acceptance without dash
"""
        data = extract_original_issue_data(issue_body)

        assert len(data.tasks) == 2
        assert "Task without dash" in data.tasks
        assert "Completed task without dash" in data.tasks
        assert len(data.acceptance_criteria) == 1
        assert "Acceptance without dash" in data.acceptance_criteria

    def test_extract_tasks_from_task_list_heading(self):
        """Extract tasks from Task List heading with plain bullets."""
        issue_body = """
## Task List

- Draft integration plan
- Update parser for edge cases
"""
        data = extract_original_issue_data(issue_body)

        assert len(data.tasks) == 2
        assert "Draft integration plan" in data.tasks
        assert "Update parser for edge cases" in data.tasks

    def test_extract_alpha_enumerated_tasks_and_acceptance(self):
        """Extract tasks and acceptance criteria from alpha-enumerated lists."""
        issue_body = """
## Tasks

a) First task
b) Second task

## Acceptance Criteria

A) Criteria one
B) Criteria two
"""
        data = extract_original_issue_data(issue_body)

        assert len(data.tasks) == 2
        assert "First task" in data.tasks
        assert "Second task" in data.tasks
        assert len(data.acceptance_criteria) == 2
        assert "Criteria one" in data.acceptance_criteria
        assert "Criteria two" in data.acceptance_criteria

    def test_extract_acceptance_from_definition_of_done(self):
        """Extract acceptance criteria from Definition of Done heading."""
        issue_body = """
## Definition of Done

- All lint checks pass
- Coverage stays above 90%
"""
        data = extract_original_issue_data(issue_body)

        assert len(data.acceptance_criteria) == 2
        assert "All lint checks pass" in data.acceptance_criteria
        assert "Coverage stays above 90%" in data.acceptance_criteria

    def test_handles_missing_sections(self):
        """Handle issues with missing standard sections."""
        issue_body = """
# Summary

Just a basic description without standard sections.
"""
        data = extract_original_issue_data(issue_body)

        assert "basic description" in data.why
        assert data.tasks == []
        assert data.acceptance_criteria == []


class TestGenerateFollowupIssue:
    """Tests for generate_followup_issue function."""

    def test_generate_without_llm(self):
        """Generate follow-up issue using structured extraction only."""
        verification_data = VerificationData(
            provider_verdicts={"openai": {"verdict": "Not Ready", "confidence": 45}},
            concerns=["Missing test coverage", "Error handling incomplete"],
            low_scores={"Testing": 4},
            iteration_count=3,
            tasks_attempted=5,
            tasks_completed=2,
        )

        original_issue = OriginalIssueData(
            number=100,
            title="Add caching feature",
            acceptance_criteria=["Response time < 100ms", "Cache hit rate > 90%"],
        )

        followup = generate_followup_issue(
            verification_data=verification_data,
            original_issue=original_issue,
            pr_number=200,
            use_llm=False,
        )

        assert "Follow-up" in followup.title
        assert "200" in followup.title
        assert "## Source" in followup.body
        assert "- Original PR: #200" in followup.body
        assert "- Parent issue: #100" in followup.body
        assert "Missing test coverage" in followup.body
        assert "Response time < 100ms" in followup.body
        assert "Not Ready" in followup.body
        assert "follow-up" in followup.labels

    def test_split_verdicts_use_worst_case(self):
        """Split verdicts should resolve to the worst-case provider verdict."""
        verification_data = VerificationData(
            provider_verdicts={
                "openai": {"verdict": "PASS", "confidence": 90},
                "anthropic": {"verdict": "CONCERNS", "confidence": 80},
            },
            concerns=["Missing test coverage"],
        )

        verdict = followup_issue_generator._resolve_verdict_policy(verification_data).verdict

        assert verdict == "CONCERNS"

    def test_advisory_concerns_are_notes(self):
        """Advisory concerns should be placed in Notes instead of tasks."""
        verification_data = VerificationData(
            provider_verdicts={"openai": {"verdict": "CONCERNS", "confidence": 70}},
            concerns=["Missing tests for edge cases", "Could add a clarifying comment"],
        )

        original_issue = OriginalIssueData(number=100, title="Add caching feature")

        followup = generate_followup_issue(
            verification_data=verification_data,
            original_issue=original_issue,
            pr_number=200,
            use_llm=False,
        )

        assert "Missing tests for edge cases" in followup.body
        assert "Could add a clarifying comment" in followup.body
        assert "- [ ] Address: Missing tests for edge cases" in followup.body
        assert "- [ ] Address: Could add a clarifying comment" not in followup.body
        assert "## Notes" in followup.body

    def test_split_high_confidence_requires_needs_human(self):
        """High-confidence CONCERNS in a split verdict should trigger needs-human labeling."""
        verification_data = VerificationData(
            provider_verdicts={
                "openai": {"verdict": "PASS", "confidence": 90},
                "anthropic": {"verdict": "CONCERNS", "confidence": 92},
            },
            concerns=["Missing test coverage"],
        )

        original_issue = OriginalIssueData(number=100, title="Add caching feature")

        followup = generate_followup_issue(
            verification_data=verification_data,
            original_issue=original_issue,
            pr_number=200,
            use_llm=False,
        )

        assert "needs-human" in followup.labels

    def test_generate_without_llm_missing_concerns_adds_rerun_task(self):
        """Missing concerns should yield a concrete re-verification task."""
        verification_data = VerificationData(
            provider_verdicts={"openai": {"verdict": "Unknown", "confidence": 0}},
            concerns=[
                "Verification output did not include extractable concerns; "
                "re-run verification to capture verifier-context.md and verifier-diff-summary.md."
            ],
            missing_concerns=True,
        )

        original_issue = OriginalIssueData(number=100, title="Add caching feature")

        followup = generate_followup_issue(
            verification_data=verification_data,
            original_issue=original_issue,
            pr_number=200,
            use_llm=False,
        )

        assert (
            "Re-run verification to capture verifier-context.md and verifier-diff-summary.md."
            in (followup.body)
        )

        decision = followup_issue_generator._format_code_change_decision(verification_data)
        assert "non-PASS output requires code changes: **no**" in decision
        assert "rerun verification with complete context" in decision

    def test_generate_without_llm_restores_verify_compare_sections(self):
        """Non-LLM output should keep analysis/evidence sections for downstream tooling."""
        verification_data = VerificationData(
            provider_verdicts={
                "openai": {
                    "verdict": "CONCERNS",
                    "confidence": 72,
                    "summary": "Missing regression coverage.",
                }
            },
            concerns=["Missing regression coverage."],
        )

        original_issue = OriginalIssueData(number=100, title="Add caching feature")

        followup = generate_followup_issue(
            verification_data=verification_data,
            original_issue=original_issue,
            pr_number=200,
            use_llm=False,
        )

        assert "## verify:compare Analysis" in followup.body
        assert "## verify:compare Evidence" in followup.body
        assert "Concern: Missing regression coverage." in followup.body
        assert "openai: CONCERNS @ 72% (Missing regression coverage.)" in followup.body

    def test_generate_without_llm_normalizes_provider_evidence_confidence(self):
        """Fractional provider confidences should render as percentages."""
        verification_data = VerificationData(
            provider_verdicts={
                "openai": {
                    "verdict": "CONCERNS",
                    "confidence": 0.92,
                    "summary": "Missing regression coverage.",
                }
            },
            concerns=["Missing regression coverage."],
        )
        original_issue = OriginalIssueData(number=100, title="Add caching feature")

        followup = generate_followup_issue(
            verification_data=verification_data,
            original_issue=original_issue,
            pr_number=200,
            use_llm=False,
        )

        assert "openai: CONCERNS @ 92%" in followup.body

    def test_includes_background_context(self):
        """Follow-up should include collapsible background section."""
        verification_data = VerificationData(
            provider_verdicts={"openai": {"verdict": "Needs Work", "confidence": 60}},
            concerns=["Test concern"],
            structural_issues=["Task format issue"],
        )

        original_issue = OriginalIssueData(number=100, title="Test")

        followup = generate_followup_issue(
            verification_data=verification_data,
            original_issue=original_issue,
            pr_number=200,
            use_llm=False,
        )

        assert "<details>" in followup.body
        assert "Structural Issues" in followup.body

    def test_why_section_explains_context(self):
        """Why section should explain the follow-up context."""
        verification_data = VerificationData(
            provider_verdicts={"openai": {"verdict": "Not Ready", "confidence": 45}},
            concerns=["Issue"],
            iteration_count=5,
            tasks_attempted=10,
            tasks_completed=7,
        )

        original_issue = OriginalIssueData(number=100, title="Test")

        followup = generate_followup_issue(
            verification_data=verification_data,
            original_issue=original_issue,
            pr_number=200,
            use_llm=False,
        )

        # Check why section contains relevant info
        assert "#200" in followup.body or "200" in followup.body
        assert "Not Ready" in followup.body
        assert "7" in followup.body and "10" in followup.body  # Completion stats


class TestRealWorldExample:
    """Test with real-world verification data (like issue #4287)."""

    def test_issue_4287_style_input(self):
        """Process data similar to issue #4287 from Trend_Model_Project."""
        verification_comment = """
## PR Verification Comparison

| Provider | Model | Verdict | Confidence |
|----------|-------|---------|------------|
| openai | gpt-4o | Not Ready | 52% |
| anthropic | claude-3.5-sonnet | Needs Work | 48% |

### Concerns

- Missing unit tests for new data processing functions
- Error handling doesn't cover all edge cases
- Configuration validation incomplete

### ⚠️ Issues Detected in Issue Structure

**Problem:** 52 tasks listed, many are code snippets not actionable work items

Agent ran 4 iterations before stopping.

Remaining unchecked items: 8 of 52
"""

        original_issue_body = """
## Why

Implement data processing pipeline for new input format.

## Scope

Create parsers and validators for JSON and CSV formats.

## Tasks

- [ ] Create JSON parser
- [ ] Create CSV parser
- [ ] Add validation layer
- [ ] Write unit tests

## Acceptance Criteria

- [ ] JSON parser handles nested objects up to 5 levels
- [ ] CSV parser supports custom delimiters
- [ ] All edge cases documented and tested
- [ ] Performance: process 1MB file in < 1 second
"""

        verification_data = extract_verification_data(verification_comment)
        original_issue = extract_original_issue_data(
            original_issue_body, issue_number=4184, title="Implement data processing pipeline"
        )

        followup = generate_followup_issue(
            verification_data=verification_data,
            original_issue=original_issue,
            pr_number=4200,
            use_llm=False,
        )

        # Verify structure is agent-ready
        assert "## Why" in followup.body
        assert "## Tasks" in followup.body
        assert "## Acceptance Criteria" in followup.body

        # Verify concerns are converted to tasks
        assert any("test" in line.lower() for line in followup.body.split("\n") if "[ ]" in line)

        # Verify original acceptance criteria carried forward
        assert any("JSON" in line or "CSV" in line for line in followup.body.split("\n"))

        # Verify background context is collapsible
        assert "<details>" in followup.body
        # Verify structural issues are captured in background
        assert "52" in followup.body or "structural" in followup.body.lower()


def test_build_llm_config_includes_standard_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "octo/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "999")
    monkeypatch.setenv("RUN_ID", "999")

    config = followup_issue_generator._build_llm_config(
        operation="generate_tasks",
        pr_number=42,
        issue_number=7,
    )

    metadata = config["metadata"]
    assert metadata["repo"] == "octo/repo"
    assert metadata["run_id"] == "999"
    assert metadata["issue_or_pr_number"] == "42"
    assert metadata["operation"] == "generate_tasks"
    assert metadata["pr_number"] == "42"
    assert metadata["issue_number"] == "7"

    tags = config["tags"]
    assert "workflows-agents" in tags
    assert "operation:generate_tasks" in tags
    assert "repo:octo/repo" in tags
    assert "issue_or_pr:42" in tags
    assert "run_id:999" in tags


def test_invoke_llm_passes_config_metadata(llm_config_sentinel) -> None:
    class DummyResponse:
        def __init__(self, content: str) -> None:
            self.content = content

    class DummyClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def invoke(self, *args: object, **kwargs: object) -> DummyResponse:
            self.calls.append(dict(kwargs))
            return DummyResponse("ok")

    client = DummyClient()
    result, trace_id, trace_url = followup_issue_generator._invoke_llm(
        "prompt",
        client,
        operation="generate_tasks",
        pr_number=111,
        issue_number=222,
    )

    expected_config = llm_config_sentinel(
        operation="generate_tasks",
        pr_number=111,
        issue_number=222,
    )

    assert result == "ok"
    assert trace_id is None  # No trace ID from DummyClient
    assert trace_url is None
    assert client.calls
    assert client.calls[0]["config"] == expected_config


def test_generate_with_llm_passes_config_metadata(llm_config_sentinel) -> None:
    class DummyResponse:
        def __init__(self, content: str) -> None:
            self.content = content

    class DummyClient:
        def __init__(self, responses: list[str]) -> None:
            self.responses = list(responses)
            self.calls: list[dict[str, object]] = []

        def invoke(self, *args: object, **kwargs: object) -> DummyResponse:
            self.calls.append(dict(kwargs))
            return DummyResponse(self.responses.pop(0))

    analysis_payload = {
        "rewritten_acceptance_criteria": [],
        "blockers_to_avoid": [],
        "concrete_tasks": [{"task": "Fix issue"}],
    }
    tasks_payload = {"tasks": ["Task 1"], "deferred": []}
    ac_payload = {"acceptance_criteria": ["AC 1"]}

    reasoning_client = DummyClient([json.dumps(analysis_payload)])
    standard_client = DummyClient([json.dumps(tasks_payload), json.dumps(ac_payload), "Issue body"])

    verification_data = VerificationData(
        provider_verdicts={"default": {"verdict": "FAIL", "confidence": 50}},
        concerns=["Missing tests"],
    )
    original_issue = OriginalIssueData(
        title="Original issue",
        number=99,
        tasks=["Do the thing"],
        acceptance_criteria=["AC 1"],
    )

    issue = followup_issue_generator._generate_with_llm(
        verification_data,
        original_issue,
        pr_number=123,
        codex_log=None,
        blocking_concerns=["Missing tests"],
        advisory_concerns=[],
        verdict="FAIL",
        needs_human_reason="",
        reasoning_client=reasoning_client,
        reasoning_model="o3-mini",
        standard_client=standard_client,
        standard_model="gpt-4o",
    )

    def expected_config(operation: str) -> dict[str, object]:
        return llm_config_sentinel(
            operation=operation,
            pr_number=123,
            issue_number=99,
        )

    assert issue.body == "Issue body"
    assert reasoning_client.calls[0]["config"] == expected_config("analyze_verification")
    assert standard_client.calls[0]["config"] == expected_config("generate_tasks")
    assert standard_client.calls[1]["config"] == expected_config("generate_acceptance_criteria")
    assert standard_client.calls[2]["config"] == expected_config("format_followup_issue")


@pytest.mark.parametrize(
    ("client_kind", "call_index", "operation"),
    [
        ("reasoning", 0, "analyze_verification"),
        ("standard", 0, "generate_tasks"),
        ("standard", 1, "generate_acceptance_criteria"),
        ("standard", 2, "format_followup_issue"),
    ],
)
def test_generate_with_llm_config_propagation(
    client_kind: str,
    call_index: int,
    operation: str,
    llm_config_sentinel,
) -> None:
    class DummyResponse:
        def __init__(self, content: str) -> None:
            self.content = content

    class DummyClient:
        def __init__(self, responses: list[str]) -> None:
            self.responses = list(responses)
            self.calls: list[dict[str, object]] = []

        def invoke(self, *args: object, **kwargs: object) -> DummyResponse:
            self.calls.append(dict(kwargs))
            return DummyResponse(self.responses.pop(0))

    analysis_payload = {
        "rewritten_acceptance_criteria": [],
        "blockers_to_avoid": [],
        "concrete_tasks": [{"task": "Fix issue"}],
    }
    tasks_payload = {"tasks": ["Task 1"], "deferred": []}
    ac_payload = {"acceptance_criteria": ["AC 1"]}

    reasoning_client = DummyClient([json.dumps(analysis_payload)])
    standard_client = DummyClient([json.dumps(tasks_payload), json.dumps(ac_payload), "Issue body"])

    verification_data = VerificationData(
        provider_verdicts={"default": {"verdict": "FAIL", "confidence": 50}},
        concerns=["Missing tests"],
    )
    original_issue = OriginalIssueData(
        title="Original issue",
        number=99,
        tasks=["Do the thing"],
        acceptance_criteria=["AC 1"],
    )

    followup_issue_generator._generate_with_llm(
        verification_data,
        original_issue,
        pr_number=123,
        codex_log=None,
        blocking_concerns=["Missing tests"],
        advisory_concerns=[],
        verdict="FAIL",
        needs_human_reason="",
        reasoning_client=reasoning_client,
        reasoning_model="o3-mini",
        standard_client=standard_client,
        standard_model="gpt-4o",
    )

    expected_config = llm_config_sentinel(
        operation=operation,
        pr_number=123,
        issue_number=99,
    )
    calls = reasoning_client.calls if client_kind == "reasoning" else standard_client.calls
    assert calls[call_index]["config"] == expected_config


@pytest.mark.parametrize(
    ("client_kind", "call_index", "operation"),
    [
        ("reasoning", 0, "analyze_verification"),
        ("standard", 0, "generate_tasks"),
        ("standard", 1, "generate_acceptance_criteria"),
        ("standard", 2, "format_followup_issue"),
    ],
)
def test_generate_with_llm_metadata_propagation(
    client_kind: str,
    call_index: int,
    operation: str,
    llm_metadata_sentinel,
) -> None:
    class DummyResponse:
        def __init__(self, content: str) -> None:
            self.content = content

    class DummyClient:
        def __init__(self, responses: list[str]) -> None:
            self.responses = list(responses)
            self.calls: list[dict[str, object]] = []

        def invoke(self, *args: object, **kwargs: object) -> DummyResponse:
            self.calls.append(dict(kwargs))
            return DummyResponse(self.responses.pop(0))

    analysis_payload = {
        "rewritten_acceptance_criteria": [],
        "blockers_to_avoid": [],
        "concrete_tasks": [{"task": "Fix issue"}],
    }
    tasks_payload = {"tasks": ["Task 1"], "deferred": []}
    ac_payload = {"acceptance_criteria": ["AC 1"]}

    reasoning_client = DummyClient([json.dumps(analysis_payload)])
    standard_client = DummyClient([json.dumps(tasks_payload), json.dumps(ac_payload), "Issue body"])

    verification_data = VerificationData(
        provider_verdicts={"default": {"verdict": "FAIL", "confidence": 50}},
        concerns=["Missing tests"],
    )
    original_issue = OriginalIssueData(
        title="Original issue",
        number=99,
        tasks=["Do the thing"],
        acceptance_criteria=["AC 1"],
    )

    followup_issue_generator._generate_with_llm(
        verification_data,
        original_issue,
        pr_number=123,
        codex_log=None,
        blocking_concerns=["Missing tests"],
        advisory_concerns=[],
        verdict="FAIL",
        needs_human_reason="",
        reasoning_client=reasoning_client,
        reasoning_model="o3-mini",
        standard_client=standard_client,
        standard_model="gpt-4o",
    )

    expected_metadata = llm_metadata_sentinel(
        operation=operation,
        pr_number=123,
        issue_number=99,
    )
    calls = reasoning_client.calls if client_kind == "reasoning" else standard_client.calls
    assert calls[call_index]["config"]["metadata"] == expected_metadata


def test_invoke_llm_typeerror_fallback_logs_and_retries(
    caplog: pytest.LogCaptureFixture,
    llm_typeerror_client_factory,
) -> None:
    class DummyResponse:
        def __init__(self, content: str) -> None:
            self.content = content

    client = llm_typeerror_client_factory(DummyResponse("ok"), message="bad config")
    caplog.set_level(logging.WARNING, logger=followup_issue_generator.__name__)

    result, trace_id, trace_url = followup_issue_generator._invoke_llm(
        "prompt",
        client,
        operation="generate_tasks",
        pr_number=101,
        issue_number=202,
    )

    assert result == "ok"
    assert trace_id is None  # No trace ID from DummyClient
    assert trace_url is None
    assert len(client.calls) == 2
    assert "config" in client.calls[0][1]
    assert "config" not in client.calls[1][1]
    assert "config/metadata fallback" in caplog.text
    assert "bad config" in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
