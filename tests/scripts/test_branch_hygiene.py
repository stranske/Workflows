"""scripts/branch_hygiene.py: the keep / delete / archive rules can never lose work."""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "branch_hygiene", Path(__file__).resolve().parents[2] / "scripts" / "branch_hygiene.py"
)
bh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bh)

NOW = dt.datetime(2026, 11, 16, tzinfo=dt.timezone.utc)


def ago(days: float) -> dt.datetime:
    return NOW - dt.timedelta(days=days)


def run(name="codex/issue-1", sha="aaa", prs=(), *, days=30, contained=False, protected=False):
    branch = {"name": name, "sha": sha, "protected": protected}
    return bh.classify(branch, list(prs), "main", head_date=ago(days) if days is not None else None,
                       contained=contained, now=NOW, min_age=3, archive_after=7)[0]


def pr(number=10, state="closed", merged=False, head="aaa"):
    return {"number": number, "state": state, "merged_at": "2026-11-01T00:00:00Z" if merged else None,
            "head_sha": head}


@pytest.mark.parametrize("name", ["main", "exports/route-weights", "release-please--branches--main", "gh-pages"])
def test_default_and_kept_patterns_are_never_touched(name):
    assert run(name=name, days=400) == "keep"


def test_protected_branch_is_kept():
    assert run(protected=True, days=400) == "keep"


def test_open_pr_branch_is_kept_however_old():
    assert run(prs=[pr(state="open")], days=400) == "keep"


def test_recent_branch_is_kept_as_in_flight():
    assert run(prs=[pr(merged=True)], days=1) == "keep"
    assert run(days=1) == "keep"


def test_unreadable_head_date_is_kept_not_guessed():
    assert run(days=None) == "keep"


def test_closed_or_merged_pr_branch_unchanged_since_is_deleted():
    assert run(prs=[pr(merged=True)]) == "delete"
    assert run(prs=[pr(merged=False)]) == "delete"


def test_newest_pr_decides():
    assert run(prs=[pr(number=1, head="old"), pr(number=2, head="aaa")]) == "delete"


def test_commits_after_the_pr_closed_are_archived_not_deleted():
    assert run(prs=[pr(head="older")], contained=False, days=30) == "archive"
    assert run(prs=[pr(head="older")], contained=True, days=30) == "delete"
    assert run(prs=[pr(head="older")], contained=False, days=5) == "keep"


def test_no_pr_branch_contained_in_main_is_deleted():
    assert run(contained=True) == "delete"


def test_no_pr_branch_with_own_commits_is_archived_only_after_the_threshold():
    assert run(contained=False, days=8) == "archive"
    assert run(contained=False, days=5) == "keep"


def test_unreadable_containment_is_kept():
    assert run(contained=None) == "keep"
