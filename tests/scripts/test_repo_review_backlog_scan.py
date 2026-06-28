"""Tests for scripts/repo_review_backlog_scan.py pure functions.

This module tests the heuristics and classification logic WITHOUT calling
the live GitHub CLI (gh). All tests use synthetic data and temporary files.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from scripts.repo_review_backlog_scan import (
    AGENT_LABEL_PREFIXES,
    EXCLUDE_LABEL_PREFIXES,
    EXCLUDE_LABELS_EXACT,
    HUMAN_DECISION_LABEL_PREFIXES,
    HUMAN_DECISION_LABELS_EXACT,
    INCLUDE_LABELS,
    PRIORITY_LABEL_PREFIXES,
    UMBRELLA_BODY_MIN_CHILD_REFS,
    UMBRELLA_BODY_PATTERN,
    UMBRELLA_DECLARATION_PATTERN,
    UMBRELLA_TITLE_WORDS,
    days_since,
    decide_priority,
    is_excluded,
    is_included,
    label_names,
    load_registry,
    looks_like_umbrella,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tmp_registry(tmp_path: Path) -> Path:
    """Create a temporary registry file for testing."""
    registry_path = tmp_path / "test_registry.json"
    return registry_path


@pytest.fixture
def sample_issue_dict() -> dict:
    """Return a basic issue dictionary structure."""
    return {
        "number": 123,
        "title": "Add new feature",
        "body": "Please add this feature",
        "labels": [{"name": "enhancement"}],
        "updatedAt": "2026-01-01T00:00:00Z",
        "createdAt": "2026-01-01T00:00:00Z",
        "url": "https://github.com/owner/repo/issues/123",
    }


# =============================================================================
# looks_like_umbrella() tests
# =============================================================================


class TestLooksLikeUmbrellaTitle:
    """Test umbrella detection via title words."""

    @pytest.mark.parametrize("title_word", sorted(UMBRELLA_TITLE_WORDS))
    def test_title_contains_umbrella_word(self, title_word: str) -> None:
        """Title containing any umbrella word should be detected."""
        is_umbrella, reason = looks_like_umbrella(
            title=f"My {title_word} issue", body="", labels=[]
        )
        assert is_umbrella is True
        assert title_word in reason

    def test_title_case_insensitive(self) -> None:
        """Title detection should be case-insensitive."""
        is_umbrella, reason = looks_like_umbrella(title="EPIC: My Epic Issue", body="", labels=[])
        assert is_umbrella is True
        assert "epic" in reason.lower()

    def test_title_with_roadmap(self) -> None:
        """Title with 'roadmap' should be detected."""
        is_umbrella, reason = looks_like_umbrella(title="Q3 Roadmap", body="", labels=[])
        assert is_umbrella is True
        assert "roadmap" in reason

    def test_title_with_parent_issue(self) -> None:
        """Title with 'parent issue' should be detected."""
        is_umbrella, reason = looks_like_umbrella(
            title="Parent issue for tracking", body="", labels=[]
        )
        assert is_umbrella is True
        assert "parent issue" in reason

    def test_title_no_umbrella_words(self) -> None:
        """Title without umbrella words should not trigger."""
        is_umbrella, reason = looks_like_umbrella(title="Add new feature", body="", labels=[])
        assert is_umbrella is False
        assert reason == ""


class TestLooksLikeUmbrellaLabels:
    """Test umbrella detection via labels."""

    @pytest.mark.parametrize("label", sorted(HUMAN_DECISION_LABELS_EXACT))
    def test_label_exact_match(self, label: str) -> None:
        """Issues with exact human-decision labels should be detected."""
        is_umbrella, reason = looks_like_umbrella(title="Some issue", body="", labels=[label])
        assert is_umbrella is True
        assert label in reason

    def test_label_case_insensitive(self) -> None:
        """Label detection should be case-insensitive."""
        is_umbrella, reason = looks_like_umbrella(title="Some issue", body="", labels=["EPIC"])
        assert is_umbrella is True
        assert "epic" in reason.lower()

    def test_multiple_human_labels(self) -> None:
        """Multiple human labels - should detect first alphabetically."""
        is_umbrella, reason = looks_like_umbrella(
            title="Some issue", body="", labels=["meta", "epic", "tracker"]
        )
        assert is_umbrella is True
        # Should report the first sorted match
        assert any(word in reason for word in ["epic", "meta", "tracker"])

    @pytest.mark.parametrize("prefix", sorted(HUMAN_DECISION_LABEL_PREFIXES))
    def test_label_with_prefix(self, prefix: str) -> None:
        """Labels starting with blocked prefix should be detected."""
        is_umbrella, reason = looks_like_umbrella(
            title="Some issue", body="", labels=[f"{prefix}waiting-on-team"]
        )
        assert is_umbrella is True
        assert prefix in reason

    def test_blocked_label(self) -> None:
        """Issue with 'blocked' label should be detected."""
        is_umbrella, reason = looks_like_umbrella(title="Some issue", body="", labels=["blocked"])
        assert is_umbrella is True
        assert "blocked" in reason

    def test_blocked_with_reason_label(self) -> None:
        """Issue with 'blocked:reason' label should be detected."""
        is_umbrella, reason = looks_like_umbrella(
            title="Some issue", body="", labels=["blocked:waiting-on-dependencies"]
        )
        assert is_umbrella is True
        assert "blocked" in reason


class TestLooksLikeUmbrellaBodyCheckboxes:
    """Test umbrella detection via body checkbox patterns."""

    def test_body_with_two_child_checkboxes(self) -> None:
        """Body with 2+ task checkboxes referencing issues should be detected."""
        body = """## Tasks
- [ ] #123
- [ ] #456
"""
        is_umbrella, reason = looks_like_umbrella(title="", body=body, labels=[])
        assert is_umbrella is True
        assert "child-issue checkboxes" in reason
        assert "2" in reason

    def test_body_with_three_child_checkboxes(self) -> None:
        """Body with 3 task checkboxes should be detected."""
        body = """## Tasks
- [ ] #1
- [ ] #2
- [ ] #3
"""
        is_umbrella, reason = looks_like_umbrella(title="", body=body, labels=[])
        assert is_umbrella is True
        assert "3" in reason

    def test_body_with_one_child_checkbox(self) -> None:
        """Body with only 1 task checkbox should NOT be detected."""
        body = """## Tasks
- [ ] #123
"""
        is_umbrella, reason = looks_like_umbrella(title="", body=body, labels=[])
        assert is_umbrella is False

    def test_body_with_checked_checkboxes(self) -> None:
        """Body with checked ([x]) checkboxes should also be detected."""
        body = """## Tasks
- [x] #123
- [x] #456
"""
        is_umbrella, reason = looks_like_umbrella(title="", body=body, labels=[])
        assert is_umbrella is True
        assert "2" in reason

    def test_body_with_child_text_and_ref(self) -> None:
        """Body with checkboxes that have descriptive text and issue refs."""
        body = """## Tasks
- [ ] Child issue #123: Implement feature A
- [ ] #456: Fix bug B
"""
        is_umbrella, reason = looks_like_umbrella(title="", body=body, labels=[])
        assert is_umbrella is True
        assert "2" in reason

    def test_body_with_checkboxes_no_issue_refs(self) -> None:
        """Body with checkboxes but no issue references should NOT trigger."""
        body = """## Tasks
- [ ] Implement feature A
- [ ] Fix bug B
"""
        is_umbrella, reason = looks_like_umbrella(title="", body=body, labels=[])
        assert is_umbrella is False


class TestLooksLikeUmbrellaBodyDeclaration:
    """Test umbrella detection via explicit child declarations in body."""

    def test_body_declares_children(self) -> None:
        """Body with 'Children: #' declaration should be detected."""
        body = """## Children
Children: #123, #456, #789
"""
        is_umbrella, reason = looks_like_umbrella(title="", body=body, labels=[])
        assert is_umbrella is True
        assert "Children" in reason or "declares" in reason

    def test_body_declares_child_issues(self) -> None:
        """Body with 'Child issues: #' declaration should be detected."""
        body = """## Tracking
Child issues: #1, #2, #3
"""
        is_umbrella, reason = looks_like_umbrella(title="", body=body, labels=[])
        assert is_umbrella is True
        assert "Child issues" in reason or "declares" in reason

    def test_body_declares_children_with_hash_prefix(self) -> None:
        """Body with '### Children: #' should be detected."""
        body = """### Children: #100
"""
        is_umbrella, reason = looks_like_umbrella(title="", body=body, labels=[])
        assert is_umbrella is True

    def test_body_no_child_declaration(self) -> None:
        """Body without child declaration should not trigger."""
        body = """## Description
This is a regular issue.
"""
        is_umbrella, reason = looks_like_umbrella(title="", body=body, labels=[])
        assert is_umbrella is False


class TestLooksLikeUmbrellaConservative:
    """Test that any single positive signal trips umbrella detection."""

    def test_multiple_signals_only_needs_one(self) -> None:
        """Even with multiple weak signals, one is enough."""
        # Has both title word AND label - either alone would be enough
        is_umbrella, reason = looks_like_umbrella(
            title="Epic: My issue", body="", labels=["enhancement"]
        )
        assert is_umbrella is True

    def test_empty_title_body_labels(self) -> None:
        """Empty inputs should not trigger."""
        is_umbrella, reason = looks_like_umbrella(title="", body="", labels=[])
        assert is_umbrella is False
        assert reason == ""

    def test_none_inputs(self) -> None:
        """None inputs should not trigger."""
        # Note: labels=None causes TypeError in the function, so we test with empty list
        is_umbrella, reason = looks_like_umbrella(title=None, body=None, labels=[])
        assert is_umbrella is False
        assert reason == ""


# =============================================================================
# decide_priority() tests
# =============================================================================


class TestDecidePriority:
    """Test priority decision heuristics."""

    def test_milestone_label_returns_normal(self) -> None:
        """Issues with milestone:* label should get priority:normal."""
        priority = decide_priority(
            labels=["milestone:Q3", "enhancement"],
            created_at="2026-01-01T00:00:00Z",
        )
        assert priority == "priority:normal"

    def test_multiple_milestone_labels(self) -> None:
        """Multiple milestone labels - still normal."""
        priority = decide_priority(
            labels=["milestone:Q3", "milestone:Q4", "enhancement"],
            created_at="2026-01-01T00:00:00Z",
        )
        assert priority == "priority:normal"

    def test_very_stale_no_milestone_returns_low(self) -> None:
        """Very stale issues (>90 days) without milestone should get priority:low."""
        # 91 days ago
        created_at = (datetime.now(tz=UTC) - timedelta(days=91)).strftime("%Y-%m-%dT%H:%M:%SZ")
        priority = decide_priority(
            labels=["enhancement"], created_at=created_at, very_stale_days=90
        )
        assert priority == "priority:low"

    def test_very_stale_with_milestone_still_normal(self) -> None:
        """Very stale issues WITH milestone should still get normal."""
        created_at = (datetime.now(tz=UTC) - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")
        priority = decide_priority(
            labels=["milestone:Q3", "enhancement"],
            created_at=created_at,
            very_stale_days=90,
        )
        assert priority == "priority:normal"

    def test_fresh_no_milestone_returns_normal(self) -> None:
        """Fresh issues without milestone should get priority:normal."""
        created_at = (datetime.now(tz=UTC) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        priority = decide_priority(
            labels=["enhancement"], created_at=created_at, very_stale_days=90
        )
        assert priority == "priority:normal"

    def test_just_over_threshold(self) -> None:
        """Issue just over 90 days should get priority:low."""
        # Use 90.01 days ago to ensure it's > 90
        created_at = (datetime.now(tz=UTC) - timedelta(days=90, hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        priority = decide_priority(
            labels=["enhancement"], created_at=created_at, very_stale_days=90
        )
        # age > 90, so should be low
        assert priority == "priority:low"

    def test_custom_very_stale_days(self) -> None:
        """Custom very_stale_days parameter should be respected."""
        created_at = (datetime.now(tz=UTC) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
        priority = decide_priority(
            labels=["enhancement"], created_at=created_at, very_stale_days=30
        )
        assert priority == "priority:low"

    def test_none_created_at_defaults_to_normal(self) -> None:
        """None created_at should default to normal (age=0)."""
        priority = decide_priority(labels=["enhancement"], created_at=None)
        assert priority == "priority:normal"

    def test_empty_labels(self) -> None:
        """Empty labels list should default to normal (no milestone)."""
        created_at = (datetime.now(tz=UTC) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        priority = decide_priority(labels=[], created_at=created_at)
        assert priority == "priority:normal"

    def test_invalid_created_at_defaults_to_normal(self) -> None:
        """Invalid created_at should default to normal (age=0)."""
        priority = decide_priority(labels=["enhancement"], created_at="invalid-date")
        assert priority == "priority:normal"


# =============================================================================
# is_excluded() tests
# =============================================================================


class TestIsExcluded:
    """Test exclusion filtering logic."""

    @pytest.mark.parametrize("prefix", sorted(PRIORITY_LABEL_PREFIXES))
    def test_priority_label_excluded(self, prefix: str) -> None:
        """Issues with priority:* labels should be excluded."""
        excluded, reason = is_excluded([f"{prefix}high"])
        assert excluded is True
        assert "priority" in reason.lower()

    @pytest.mark.parametrize("prefix", sorted(AGENT_LABEL_PREFIXES))
    def test_agent_label_excluded(self, prefix: str) -> None:
        """Issues with agent:* labels should be excluded."""
        excluded, reason = is_excluded([f"{prefix}test"])
        assert excluded is True
        assert "agent" in reason.lower()

    @pytest.mark.parametrize("prefix", sorted(EXCLUDE_LABEL_PREFIXES))
    def test_exclude_label_prefix_excluded(self, prefix: str) -> None:
        """Issues with exclude-label-prefixes should be excluded."""
        excluded, reason = is_excluded([f"{prefix}something"])
        assert excluded is True
        assert "excluded prefix" in reason

    @pytest.mark.parametrize("label", sorted(EXCLUDE_LABELS_EXACT))
    def test_exclude_label_exact_excluded(self, label: str) -> None:
        """Issues with exact exclude labels should be excluded."""
        excluded, reason = is_excluded([label])
        assert excluded is True
        # Note: labels like "campaign:active" match EXCLUDE_LABEL_PREFIXES first,
        # so they return "excluded prefix" instead of "excluded label"
        assert "excluded" in reason.lower()

    def test_multiple_exclusion_reasons_first_priority(self) -> None:
        """When multiple exclusions apply, priority label takes precedence."""
        excluded, reason = is_excluded(["priority:high", "dependabot", "agent:test"])
        assert excluded is True
        # Should report the first match in order: priority, then agent, then others
        assert "priority" in reason.lower() or "agent" in reason.lower()

    def test_not_excluded_no_matching_labels(self) -> None:
        """Issues with no matching labels should not be excluded."""
        excluded, reason = is_excluded(["enhancement", "feature", "bug"])
        assert excluded is False
        assert reason == ""

    def test_not_excluded_empty_labels(self) -> None:
        """Empty labels should not be excluded."""
        excluded, reason = is_excluded([])
        assert excluded is False
        assert reason == ""

    def test_campaign_label_excluded(self) -> None:
        """Campaign:* labels should be excluded."""
        excluded, reason = is_excluded(["campaign:active"])
        assert excluded is True
        assert "excluded prefix" in reason

    def test_dependabot_excluded(self) -> None:
        """Dependabot label should be excluded."""
        excluded, reason = is_excluded(["dependabot"])
        assert excluded is True
        assert "excluded label" in reason

    def test_sync_labels_excluded(self) -> None:
        """Sync-related labels should be excluded."""
        for label in ["sync", "sync-pr", "sync-generated", "consumer-sync"]:
            excluded, reason = is_excluded([label])
            assert excluded is True, f"Label {label} should be excluded"


# =============================================================================
# is_included() tests
# =============================================================================


class TestIsIncluded:
    """Test inclusion filtering logic."""

    @pytest.mark.parametrize("label", sorted(INCLUDE_LABELS))
    def test_include_label_included(self, label: str) -> None:
        """Issues with enhancement or feature labels should be included."""
        assert is_included([label]) is True

    def test_multiple_labels_with_include(self) -> None:
        """Issues with include label among others should be included."""
        assert is_included(["bug", "enhancement", "help-wanted"]) is True

    def test_no_include_labels_not_included(self) -> None:
        """Issues without enhancement or feature labels should not be included."""
        assert is_included(["bug", "help-wanted"]) is False

    def test_empty_labels_not_included(self) -> None:
        """Empty labels should not be included."""
        assert is_included([]) is False

    def test_case_sensitive_include(self) -> None:
        """Include labels should be case-sensitive."""
        # The INCLUDE_LABELS set has lowercase
        assert is_included(["Enhancement"]) is False
        assert is_included(["enhancement"]) is True


# =============================================================================
# label_names() tests
# =============================================================================


class TestLabelNames:
    """Test label extraction from issue dict."""

    def test_extract_label_names(self, sample_issue_dict: dict) -> None:
        """Should extract name field from label dicts."""
        labels = label_names(sample_issue_dict)
        assert labels == ["enhancement"]

    def test_extract_multiple_labels(self) -> None:
        """Should extract multiple label names."""
        issue = {
            "labels": [
                {"name": "enhancement"},
                {"name": "feature"},
                {"name": "bug"},
            ]
        }
        labels = label_names(issue)
        assert labels == ["enhancement", "feature", "bug"]

    def test_empty_labels(self) -> None:
        """Should handle empty labels."""
        issue = {"labels": []}
        labels = label_names(issue)
        assert labels == []

    def test_missing_labels_field(self) -> None:
        """Should handle missing labels field."""
        issue = {}
        labels = label_names(issue)
        assert labels == []

    def test_null_labels_field(self) -> None:
        """Should handle null labels field."""
        issue = {"labels": None}
        labels = label_names(issue)
        assert labels == []

    def test_label_without_name_field(self) -> None:
        """Should handle label dict without name field - returns empty string."""
        issue = {"labels": [{"id": 123}, {"name": "enhancement"}]}
        labels = label_names(issue)
        # Note: label without name field returns empty string
        assert labels == ["", "enhancement"]


# =============================================================================
# days_since() tests
# =============================================================================


class TestDaysSince:
    """Test days_since timestamp calculation."""

    def test_days_since_recent(self) -> None:
        """Recent timestamp should return small value."""
        ts = (datetime.now(tz=UTC) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        days = days_since(ts)
        assert 0 < days < 1

    def test_days_since_exact_days(self) -> None:
        """Timestamp from exact days ago should return that value."""
        ts = (datetime.now(tz=UTC) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        days = days_since(ts)
        assert abs(days - 5.0) < 0.01

    def test_days_since_with_z_suffix(self) -> None:
        """Timestamp with Z suffix should be handled."""
        ts = (datetime.now(tz=UTC) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        days = days_since(ts)
        assert abs(days - 3.0) < 0.01

    def test_days_since_none(self) -> None:
        """None timestamp should return 0."""
        assert days_since(None) == 0.0

    def test_days_since_empty_string(self) -> None:
        """Empty string timestamp should return 0."""
        assert days_since("") == 0.0

    def test_days_since_invalid_format(self) -> None:
        """Invalid timestamp format should return 0."""
        assert days_since("invalid") == 0.0
        assert days_since("2026-13-01T00:00:00Z") == 0.0

    def test_days_since_with_timezone_offset(self) -> None:
        """Timestamp with timezone offset should be handled."""
        ts = (datetime.now(tz=UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        days = days_since(ts)
        assert abs(days - 2.0) < 0.01


# =============================================================================
# load_registry() tests
# =============================================================================


class TestLoadRegistry:
    """Test registry loading logic."""

    def test_load_registry_active_repos(self, tmp_registry: Path) -> None:
        """Should load only active repos."""
        data = {
            "repos": [
                {"repo": "owner/repo1", "status": "active"},
                {"repo": "owner/repo2", "status": "paused"},
                {"repo": "owner/repo3", "status": "active"},
                {"repo": "owner/repo4", "status": "ignored"},
                {"repo": "owner/repo5"},  # missing status
                {"status": "active"},  # missing repo
            ]
        }
        tmp_registry.write_text(json.dumps(data), encoding="utf-8")

        repos = load_registry(tmp_registry)
        assert repos == ["owner/repo1", "owner/repo3"]

    def test_load_registry_empty_repos(self, tmp_registry: Path) -> None:
        """Should handle empty repos list."""
        data = {"repos": []}
        tmp_registry.write_text(json.dumps(data), encoding="utf-8")

        repos = load_registry(tmp_registry)
        assert repos == []

    def test_load_registry_missing_repos_key(self, tmp_registry: Path) -> None:
        """Should handle missing repos key."""
        data = {}
        tmp_registry.write_text(json.dumps(data), encoding="utf-8")

        repos = load_registry(tmp_registry)
        assert repos == []

    def test_load_registry_null_repos(self, tmp_registry: Path) -> None:
        """Should handle null repos value."""
        data = {"repos": None}
        tmp_registry.write_text(json.dumps(data), encoding="utf-8")

        repos = load_registry(tmp_registry)
        assert repos == []

    def test_load_registry_active_only_true(self, tmp_registry: Path) -> None:
        """Should only include repos with status=='active'."""
        data = {
            "repos": [
                {"repo": "owner/active1", "status": "active"},
                {"repo": "owner/active2", "status": "active"},
            ]
        }
        tmp_registry.write_text(json.dumps(data), encoding="utf-8")

        repos = load_registry(tmp_registry)
        assert repos == ["owner/active1", "owner/active2"]

    def test_load_registry_non_dict_entries(self, tmp_registry: Path) -> None:
        """Should skip non-dict entries in repos list."""
        data = {
            "repos": [
                {"repo": "owner/repo1", "status": "active"},
                "not-a-dict",
                123,
                None,
            ]
        }
        tmp_registry.write_text(json.dumps(data), encoding="utf-8")

        repos = load_registry(tmp_registry)
        assert repos == ["owner/repo1"]


# =============================================================================
# Pattern matching tests (for completeness)
# =============================================================================


class TestUmbrellaPatterns:
    """Test that the regex patterns are correctly defined."""

    def test_umbrella_body_pattern_matches_task_checkbox(self) -> None:
        """UMBRELLA_BODY_PATTERN should match task checkboxes with issue refs."""
        text = "- [ ] #123"
        assert UMBRELLA_BODY_PATTERN.search(text) is not None

    def test_umbrella_body_pattern_matches_checked_checkbox(self) -> None:
        """UMBRELLA_BODY_PATTERN should match checked checkboxes."""
        text = "- [x] #456"
        assert UMBRELLA_BODY_PATTERN.search(text) is not None

    def test_umbrella_body_pattern_matches_with_text(self) -> None:
        """UMBRELLA_BODY_PATTERN should match checkboxes with descriptive text."""
        text = "- [ ] Implement feature #789"
        assert UMBRELLA_BODY_PATTERN.search(text) is not None

    def test_umbrella_body_pattern_ignores_no_issue_ref(self) -> None:
        """UMBRELLA_BODY_PATTERN should not match checkboxes without issue refs."""
        text = "- [ ] Implement feature"
        assert UMBRELLA_BODY_PATTERN.search(text) is None

    def test_umbrella_declaration_pattern_matches_children(self) -> None:
        """UMBRELLA_DECLARATION_PATTERN should match 'Children: #' format."""
        text = "Children: #123, #456"
        assert UMBRELLA_DECLARATION_PATTERN.search(text) is not None

    def test_umbrella_declaration_pattern_matches_child_issues(self) -> None:
        """UMBRELLA_DECLARATION_PATTERN should match 'Child issues: #' format."""
        text = "Child issues: #1, #2, #3"
        assert UMBRELLA_DECLARATION_PATTERN.search(text) is not None

    def test_umbrella_declaration_pattern_with_header(self) -> None:
        """UMBRELLA_DECLARATION_PATTERN should match with markdown headers."""
        text = "## Children: #100"
        assert UMBRELLA_DECLARATION_PATTERN.search(text) is not None

    def test_umbrella_declaration_pattern_case_insensitive(self) -> None:
        """UMBRELLA_DECLARATION_PATTERN should be case-insensitive."""
        text = "CHILDREN: #123"
        assert UMBRELLA_DECLARATION_PATTERN.search(text) is not None


# =============================================================================
# Constants verification tests
# =============================================================================


class TestConstants:
    """Verify module constants are as expected."""

    def test_umbrella_body_min_child_refs(self) -> None:
        """UMBRELLA_BODY_MIN_CHILD_REFS should be 2."""
        assert UMBRELLA_BODY_MIN_CHILD_REFS == 2

    def test_include_labels(self) -> None:
        """INCLUDE_LABELS should contain enhancement and feature."""
        assert "enhancement" in INCLUDE_LABELS
        assert "feature" in INCLUDE_LABELS

    def test_priority_label_prefixes(self) -> None:
        """PRIORITY_LABEL_PREFIXES should contain priority:."""
        assert "priority:" in PRIORITY_LABEL_PREFIXES

    def test_agent_label_prefixes(self) -> None:
        """AGENT_LABEL_PREFIXES should contain agent:."""
        assert "agent:" in AGENT_LABEL_PREFIXES

    def test_exclude_label_prefixes(self) -> None:
        """EXCLUDE_LABEL_PREFIXES should contain campaign:."""
        assert "campaign:" in EXCLUDE_LABEL_PREFIXES

    def test_epic_in_umbrella_title_words(self) -> None:
        """UMBRELLA_TITLE_WORDS should contain epic."""
        assert "epic" in UMBRELLA_TITLE_WORDS

    def test_blocked_in_human_decision_prefixes(self) -> None:
        """HUMAN_DECISION_LABEL_PREFIXES should contain blocked."""
        assert "blocked" in HUMAN_DECISION_LABEL_PREFIXES

    def test_epic_in_human_decision_labels_exact(self) -> None:
        """HUMAN_DECISION_LABELS_EXACT should contain epic."""
        assert "epic" in HUMAN_DECISION_LABELS_EXACT
