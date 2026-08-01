"""Keep the #2210 durable-tracker doc honest about Health 68's drift states (issue #2878).

The #2878 task list required both `CONSUMER_REPO_MAINTENANCE.md` and
`DURABLE_TRACKING_ISSUES.md` to carry the state and SLO contract; only the first
was updated, so the tracker page still promised a daily cron and described drift
itself as the red signal. These gates pin the doc to what the checker can
actually emit, so a sixth state cannot be added silently.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKER_DOC = REPO_ROOT / "docs" / "ops" / "DURABLE_TRACKING_ISSUES.md"
CHECKER = REPO_ROOT / "scripts" / "check_consumer_sync_drift.py"
HEALTH_68 = REPO_ROOT / ".github" / "workflows" / "health-68-consumer-sync-drift.yml"

_SECTION_2210 = re.compile(
    r"- \*\*#2210\*\* —.*?(?=\n- \*\*#|\n### |\n## |\Z)",
    re.DOTALL,
)
_ROW_2210 = re.compile(
    r"\| \[#2210\].*?\|.*?\|.*?\| (.*?) \|",
)


def _section_2210(text: str) -> str:
    match = _SECTION_2210.search(text)
    assert match, "DURABLE_TRACKING_ISSUES.md is missing the #2210 signal-flow section"
    return match.group(0)


def _per_repo_states() -> set[str]:
    """Every value the checker assigns to a per-repo `state` key."""
    source = CHECKER.read_text(encoding="utf-8")
    return set(re.findall(r"[\"']state[\"']:\s*[\"']([a-z_]+)[\"']", source))


def test_tracker_doc_documents_every_state_the_checker_emits() -> None:
    section = _section_2210(TRACKER_DOC.read_text(encoding="utf-8"))
    documented = set(re.findall(r"\| `([a-z_]+)` \|", section))
    emitted = _per_repo_states() | {"converged"}

    assert emitted == {
        "blocked",
        "converged",
        "covered",
        "stale",
        "untracked_drift",
    }, "the checker state contract changed; update this gate and the durable tracker documentation"
    assert documented == emitted, (
        f"doc/code state mismatch in the #2210 table: "
        f"extra={sorted(documented - emitted)} missing={sorted(emitted - documented)}"
    )


def test_tracker_doc_does_not_promise_a_cron_health_68_no_longer_has() -> None:
    text = TRACKER_DOC.read_text(encoding="utf-8")
    workflow = HEALTH_68.read_text(encoding="utf-8")
    row = _ROW_2210.search(text)
    assert row, "missing #2210 cadence row in the durable tracker table"
    cadence = row.group(1)

    assert "schedule:" not in workflow, "Health 68 regained a cron; update the tracker doc row"
    assert "05:10" not in cadence and "cron" not in cadence.lower()
    assert "Merge Sync PRs" in cadence
    assert "successful main-branch" in cadence
    assert "qualifying" in cadence and "push" in cadence
    assert "manual dispatch" in cadence


def test_tracker_doc_states_that_covered_drift_is_silent() -> None:
    section = _section_2210(TRACKER_DOC.read_text(encoding="utf-8"))
    covered_row = re.search(r"\| `covered` \|.*?\|.*?\|.*?\|", section)
    assert covered_row, "missing `covered` row in the #2210 state table"
    assert "| 0 |" in covered_row.group(0)
    assert "| No |" in covered_row.group(0)
    assert "silent" in section
    assert "nothing actionable" in section
    assert "CONSUMER_REPO_MAINTENANCE.md#drift-coverage-states" in section


def test_tracker_doc_red_signal_includes_global_comparison_errors() -> None:
    text = TRACKER_DOC.read_text(encoding="utf-8")
    assert "global comparison error" in text
    assert re.search(
        r"stale`/`blocked`/`untracked_drift` state or a global comparison error",
        text,
    )
