#!/usr/bin/env python3
"""PASS cases from stable merges (owner decision 2026-10-18).

The approval gate's false-FAIL bound needs 35 evaluable PASS cases at zero errors. PASS cases that
join an actual verifier decision (``tools/harvest_verifier_corpus.py``) only start to appear about a
month after the decision marker was introduced, so a merged PR may also be labelled PASS by realized
outcome alone: merged at least ``minimum_age_days`` ago, not reverted, no verifier follow-up label.
Such cases carry ``provenance: stable-merge`` so they are reported apart from joined-decision PASS
cases, and only inputs the production prompt calls sufficient are used (an insufficient input would
make a correct judge answer ``UNVERIFIABLE_INPUT`` and score as a false FAIL).

The label is weaker than a joined decision: nothing ties it to a verifier run, and a repair that does
not carry a follow-up label is invisible here. A wrongly labelled PASS counts against a judge as a false
FAIL, so the error leans conservative. ``approval_stage.stable_merge_pass.enabled`` switches the
source off; the cases then stop counting.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

PROVENANCE = "stable-merge"
FOLLOWUP_LABELS = {"verify:create-issue", "verifier-followup"}
_REVERT_REF = re.compile(r"#(\d+)")


def _gh_json(args: list[str]) -> Any:
    run = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120, check=False)
    try:
        return json.loads(run.stdout)
    except ValueError:
        return None


def pr_facts(repo: str, pr: int) -> dict[str, Any] | None:
    """merged_at (ISO) and labels for one PR, or None when GitHub does not answer."""
    data = _gh_json(["pr", "view", str(pr), "--repo", repo, "--json", "mergedAt,labels,state"])
    if not isinstance(data, dict):
        return None
    return {
        "merged_at": data.get("mergedAt"),
        "labels": {str(label.get("name")) for label in data.get("labels", [])},
        "state": data.get("state"),
    }


def reverted_numbers(repo: str) -> set[int]:
    """PR numbers named by a merged revert PR (the harvester's rule)."""
    reverts = (
        _gh_json(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "merged",
                "--search",
                "revert in:title",
                "--limit",
                "100",
                "--json",
                "title,body",
            ]
        )
        or []
    )
    found: set[int] = set()
    for item in reverts:
        for match in _REVERT_REF.findall(f"{item.get('title', '')} {item.get('body', '')}"):
            found.add(int(match))
    return found


def stable_age_days(facts: dict[str, Any] | None, reverted: set[int], pr: int, now: datetime):
    """Days since merge when the PR qualifies except for age, else None."""
    if not facts or facts.get("state") != "MERGED" or not facts.get("merged_at"):
        return None
    if pr in reverted or facts["labels"] & FOLLOWUP_LABELS:
        return None
    merged = datetime.fromisoformat(str(facts["merged_at"]).replace("Z", "+00:00"))
    return (now - merged).total_seconds() / 86400.0


def stable_pass_cases(
    sources: dict[str, dict[str, Any]],
    *,
    minimum_age_days: int,
    coverage_sufficient: Callable[[dict[str, Any]], bool],
    facts_fn: Callable[[str, int], dict[str, Any] | None] = pr_facts,
    reverted_fn: Callable[[str], set[int]] = reverted_numbers,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Corpus case records for unlisted sources that qualify as stable-merge PASS."""
    now = now or datetime.now(UTC)
    reverted_cache: dict[str, set[int]] = {}
    out = []
    for case_id, case in sorted(sources.items()):
        if not case.get("source_only"):
            continue  # a corpus case already has its own label
        if not coverage_sufficient(case["production_snapshot"]):
            continue
        repo, pr = case["repo"], int(case["pr"])
        reverted = reverted_cache.setdefault(repo, reverted_fn(repo))
        age = stable_age_days(facts_fn(repo, pr), reverted, pr, now)
        if age is None or age < minimum_age_days:
            continue
        out.append(
            {
                "case_id": case_id,
                "repo": repo,
                "pr": pr,
                "expected_verdict": "PASS",
                "category": "clean-pass",
                "provenance": PROVENANCE,
                "stable_age_days_at_label": int(age),
            }
        )
    return out
