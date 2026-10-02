"""Keep the weekly review roster aligned with repositories delivering substantive code."""

import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "config" / "repo_review_registry.json"
ACTIVE_CODE_REPOS = {
    "stranske/Doc-Lineage",
    "stranske/Deliverable-Render",
    "stranske/Manager-Mosaic",
    "stranske/Orchestrator",
    "stranske/Ready",
}


def test_recent_product_code_repos_are_in_weekly_review():
    data = json.loads(REGISTRY.read_text())
    by_repo = {r["repo"]: r for r in data["repos"]}
    for repo in sorted(ACTIVE_CODE_REPOS):
        assert repo in by_repo, f"{repo} is missing from the review registry"
        assert (
            by_repo[repo]["status"] == "active"
        ), f"{repo} is producing substantive code and must be included in the weekly review"
        assert by_repo[repo]["cadence"] == "weekly"
        assert by_repo[repo]["decision_anchor"].strip()
