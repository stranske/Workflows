"""Repos that produce no output are `ignored` in the review registry — by name.

The owner has said more than once that Collab-Admin and Workflows-Integration-Tests produce no
output and must not be pulled into fleet, ingest, audit or report sets. That instruction lived in
conversations and was re-broken on 2026-09-21, when a consumer treated `paused` (review cadence
paused) as "still produces output" and ingested both. The registry is the one place every consumer
reads, so the exclusion lives here as a status, and this test pins it by name the way the lane-fleet
guard pins Template and Workflows-Integration-Tests — a change to either status must edit this file
and say why.
"""

import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "config" / "repo_review_registry.json"
NO_OUTPUT_REPOS = {"stranske/Collab-Admin", "stranske/Workflows-Integration-Tests"}


def test_no_output_repos_are_ignored_not_paused():
    data = json.loads(REGISTRY.read_text())
    by_repo = {r["repo"]: r for r in data["repos"]}
    for repo in sorted(NO_OUTPUT_REPOS):
        assert repo in by_repo, f"{repo} missing from the registry"
        assert by_repo[repo]["status"] == "ignored", (
            f"{repo} is {by_repo[repo]['status']!r}; it produces no output and must stay 'ignored' "
            "(owner instruction) — consumers read status, so 'paused' would re-admit it"
        )
        assert "no output" in by_repo[repo].get("decision_anchor", "").lower()
