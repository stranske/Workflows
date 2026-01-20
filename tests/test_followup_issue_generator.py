#!/usr/bin/env python3
"""Tests for followup_issue_generator.py"""

import pytest

from scripts.langchain.followup_issue_generator import (
    OriginalIssueData,
    VerificationData,
    extract_original_issue_data,
    extract_verification_data,
    generate_followup_issue,
)


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

    def test_extract_single_verdict(self):
        """Extract verdict from single provider format."""
        comment = """
## PR Verification Report

Verdict: **Not Ready** @75%
"""
        data = extract_verification_data(comment)

        assert "default" in data.provider_verdicts
        assert data.provider_verdicts["default"]["verdict"] == "Not Ready"

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

    def test_extract_task_completion(self):
        """Extract task completion stats."""
        comment = """
Remaining unchecked items: 3 of 10
"""
        data = extract_verification_data(comment)
        assert data.tasks_attempted == 10
        assert data.tasks_completed == 7

    def test_extract_structural_issues(self):
        """Extract structural issues detected."""
        comment = """
### ⚠️ Issues Detected in Issue Structure

**Problem:** Tasks contain code snippets instead of actionable items

- Example: `def foo(): pass`
"""
        data = extract_verification_data(comment)

        assert len(data.structural_issues) >= 1
        assert any("code snippets" in issue.lower() for issue in data.structural_issues)


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
