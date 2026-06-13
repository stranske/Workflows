"""Tests for scripts/prune_agent_stubs.py — select_prunable is pure/unit-testable."""

from scripts.prune_agent_stubs import select_prunable

# ---------------------------------------------------------------------------
# Core acceptance-criteria test (from issue #2336)
# ---------------------------------------------------------------------------


def test_select_prunable_acceptance() -> None:
    """Closed stub pruned, open stub kept, non-stub ignored."""
    result = select_prunable(
        ["auto-pilot-100.md", "auto-pilot-200.md", "README.md"],
        {100},
    )
    assert result == ["auto-pilot-100.md"]


# ---------------------------------------------------------------------------
# Additional unit tests
# ---------------------------------------------------------------------------


def test_select_prunable_empty_inputs() -> None:
    assert select_prunable([], set()) == []


def test_select_prunable_no_closed_issues() -> None:
    """When no issue numbers are closed, nothing should be pruned."""
    stubs = ["auto-pilot-755.md", "codex-10.md"]
    assert select_prunable(stubs, set()) == []


def test_select_prunable_all_closed() -> None:
    """All matching stubs are returned when all are closed."""
    stubs = ["auto-pilot-100.md", "auto-pilot-200.md"]
    result = select_prunable(stubs, {100, 200})
    assert result == ["auto-pilot-100.md", "auto-pilot-200.md"]


def test_select_prunable_non_stub_names_ignored() -> None:
    """Files that don't match the pattern are never returned."""
    non_stubs = [
        "README.md",
        "AUTO-PILOT-100.md",  # uppercase start — does not match
        "auto-pilot.md",  # no trailing issue number
        ".hidden-1.md",  # starts with dot
        "auto_pilot-100.md",  # underscore not in pattern
    ]
    assert select_prunable(non_stubs, {100}) == []


def test_select_prunable_open_stubs_kept() -> None:
    """Stubs whose issue number is NOT in closed_issue_numbers are left alone."""
    stubs = ["auto-pilot-100.md", "auto-pilot-200.md", "codex-300.md"]
    # Only 100 is closed; 200 and 300 are open.
    result = select_prunable(stubs, {100})
    assert result == ["auto-pilot-100.md"]
    assert "auto-pilot-200.md" not in result
    assert "codex-300.md" not in result


def test_select_prunable_result_is_sorted() -> None:
    """Results come back in sorted order regardless of input order."""
    stubs = ["codex-300.md", "auto-pilot-100.md", "auto-pilot-200.md"]
    result = select_prunable(stubs, {100, 200, 300})
    assert result == sorted(result)


def test_select_prunable_multiple_agents() -> None:
    """Works correctly with stubs from different agent prefixes."""
    stubs = ["auto-pilot-10.md", "codex-10.md", "auto-pilot-20.md"]
    # Both issue-10 stubs (different agents) should be pruned; 20 kept.
    result = select_prunable(stubs, {10})
    assert "auto-pilot-10.md" in result
    assert "codex-10.md" in result
    assert "auto-pilot-20.md" not in result
