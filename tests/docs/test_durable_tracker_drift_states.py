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


def _per_repo_states() -> set[str]:
    """Every value the checker assigns to a per-repo `state` key."""
    source = CHECKER.read_text(encoding="utf-8")
    return set(re.findall(r"[\"']state[\"']:\s*[\"']([a-z_]+)[\"']", source))


def test_tracker_doc_documents_every_state_the_checker_emits() -> None:
    documented = set(re.findall(r"\| `([a-z_]+)` \|", TRACKER_DOC.read_text(encoding="utf-8")))
    emitted = _per_repo_states() | {"converged"}

    assert emitted == {"blocked", "converged", "covered", "stale", "untracked_drift"}, (
        "the checker state contract changed; update this gate and the durable tracker documentation"
    )
    assert emitted <= documented, (
        f"states missing from DURABLE_TRACKING_ISSUES.md: {sorted(emitted - documented)}"
    )


def test_tracker_doc_does_not_promise_a_cron_health_68_no_longer_has() -> None:
    text = TRACKER_DOC.read_text(encoding="utf-8")
    workflow = HEALTH_68.read_text(encoding="utf-8")

    assert "schedule:" not in workflow, "Health 68 regained a cron; update the tracker doc row"
    assert "05:10" not in text, "the tracker row still advertises the removed daily 05:10 cron"
    assert "Merge Sync PRs" in text


def test_tracker_doc_states_that_covered_drift_is_silent() -> None:
    text = TRACKER_DOC.read_text(encoding="utf-8")

    # The whole point of #2878: a covered run exits zero and appends nothing, so
    # a quiet tracker must not be read as a broken workflow.
    assert "covered" in text
    assert "actionable" in text
    assert "CONSUMER_REPO_MAINTENANCE.md#drift-coverage-states" in text
