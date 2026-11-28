"""Maint 69 label sync must fail the job when any label write errors.

The label_rules_assert.py helper this file also tested had no caller and was retired on
2026-11-28 (round-2 E4); the file keeps its name because tests/scripts/
test_check_deliberate_break.py cites this test by path.
"""

from __future__ import annotations

from pathlib import Path

LABEL_SYNC_WORKFLOW = (
    Path(__file__).resolve().parents[3] / ".github" / "workflows" / "maint-69-sync-labels.yml"
)


def test_label_sync_fails_when_any_label_write_errors() -> None:
    workflow = LABEL_SYNC_WORKFLOW.read_text(encoding="utf-8")

    summary_index = workflow.index("await core.summary.addRaw(summary.join('')).write()")
    aggregate_index = workflow.index("if (totalErrors > 0)")
    failure_index = workflow.index("core.setFailed", aggregate_index)

    assert summary_index < aggregate_index < failure_index
