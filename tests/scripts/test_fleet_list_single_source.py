from __future__ import annotations

from pathlib import Path

from scripts import cleanup_labels, langsmith_fleet
from scripts.list_registered_consumer_repos import extract_repos

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".github/workflows/maint-68-sync-consumer-repos.yml"


def test_no_second_consumer_repo_literal() -> None:
    registered = extract_repos(MANIFEST)

    assert registered == cleanup_labels.CONSUMER_REPOS
    assert set(registered) == langsmith_fleet.MANAGED_CONSUMER_REPOS
