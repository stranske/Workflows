"""Tests for tools/codex_log_analyzer.py."""

from tools.codex_log_analyzer import _extract_tasks_from_markdown


def test_extract_tasks_ignores_details_summary_tags() -> None:
    markdown = """
- [ ] <details>
- [ ] <summary>What should I do?</summary>
- [ ] Actual task
- [x] Completed task
- [ ] </details>
"""
    tasks = _extract_tasks_from_markdown(markdown, include_checked=False)
    assert tasks == ["Actual task"]


def test_extract_tasks_keeps_completed_but_skips_tags() -> None:
    markdown = """
- [ ] <details>
- [ ] Actual task
- [x] Completed task
- [ ] </details>
"""
    tasks = _extract_tasks_from_markdown(markdown, include_checked=True)
    assert tasks == ["Actual task", "Completed task"]
