#!/usr/bin/env python3
"""Collect the read-only PR-search component of Cursor's post-merge acceptance.

Usage: python scripts/check_cursor_pr_outcome.py --fix-pr stranske/Workflows#4564

Exit codes: 0 = complete search window with no matches, 1 = regression,
2 = pending or unavailable evidence. Even exit 0 requires separate evidence of
the next keepalive target merging during Run Cursor; this command cannot prove
that event. All PR states are searched, including closed orphan PRs.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

SLUG_BRANCH = re.compile(r"cursor/issue-[1-9][0-9]*-[A-Za-z0-9][A-Za-z0-9_-]*")
EXCLUDED_REPOS = frozenset({"stranske/collab-admin"})


def timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Evidence timestamps must be strings")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Evidence timestamps must include a timezone")
    return parsed.astimezone(UTC)


def gh_json(endpoint: str) -> dict:
    result = subprocess.run(
        ["gh", "api", "--method", "GET", endpoint],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError("Expected a GitHub API object")
    return data


def collect(fix_pr: str, *, now: datetime, api=gh_json) -> dict:
    """Search a fixed 14-day window; reject incomplete or truncated evidence."""
    match = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)", fix_pr)
    if not match:
        raise ValueError("Use owner/repository#number for --fix-pr")
    repo, number = match.groups()
    if repo.lower() in EXCLUDED_REPOS:
        raise ValueError("Fix PR repository is excluded by owner policy")
    owner = repo.split("/")[0]
    report = {
        "fix_pr": fix_pr,
        "observed_at": now.isoformat(),
        "status": "pending",
        "matches": [],
        "mid_run_merge_verification": "required separately; search alone is not acceptance",
    }
    fix = api(f"repos/{repo}/pulls/{number}")
    if not fix.get("merged_at"):
        return {**report, "reason": "fix PR has not merged"}
    start = timestamp(fix["merged_at"])
    if start > now:
        raise ValueError("Fix merge timestamp is later than the observation")
    end = start + timedelta(days=14)
    observed_end = min(now, end)
    # Fetch all bot PRs in the date range. Inspect actual heads instead of relying
    # on search's head prefix matching or a slug mentioned in a PR body.
    query = (
        f"is:pr user:{owner} author:app/github-actions "
        f"created:{start.date()}..{observed_end.date()} "
        + " ".join(f"-repo:{name}" for name in sorted(EXCLUDED_REPOS))
    )
    report.update(window_start=start.isoformat(), window_end=end.isoformat(), query=query)
    seen = set()
    total = None
    for page in range(1, 11):
        response = api("search/issues?" + urlencode({"q": query, "per_page": 100, "page": page}))
        count = response["total_count"]
        if (
            response.get("incomplete_results") is not False
            or type(count) is not int
            or not 0 <= count <= 1000
        ):
            raise ValueError("GitHub search is incomplete or exceeds its 1000-result cap")
        if total is not None and total != count:
            raise ValueError("GitHub search changed during pagination; retry collection")
        total = count
        items = response["items"]
        if not isinstance(items, list):
            raise ValueError("GitHub search items must be an array")
        if len(items) != min(100, total - (page - 1) * 100):
            raise ValueError("GitHub search page does not match its result count")
        for item in items:
            item_repo_match = re.fullmatch(
                r"https://api\.github\.com/repos/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
                item["repository_url"],
            )
            if not item_repo_match:
                raise ValueError("Unexpected search repository URL")
            item_repo = item_repo_match[1]
            if item_repo.lower() in EXCLUDED_REPOS:
                continue
            if item_repo.split("/")[0].lower() != owner.lower():
                raise ValueError("Search returned a repository outside the requested owner")
            item_number = item["number"]
            if type(item_number) is not int or item_number <= 0:
                raise ValueError("Invalid search PR number")
            key = (item_repo.lower(), item_number)
            if key in seen:
                raise ValueError("GitHub search repeated a PR across pages; retry collection")
            seen.add(key)
            pull = api(f"repos/{item_repo}/pulls/{item_number}")
            branch = pull["head"]["ref"]
            created = timestamp(pull["created_at"])
            if (
                SLUG_BRANCH.fullmatch(branch)
                and pull["user"]["login"] == "github-actions[bot]"
                and start <= created <= observed_end
            ):
                report["matches"].append(
                    {"url": pull["html_url"], "branch": branch, "created_at": pull["created_at"]}
                )
        if page * 100 >= total:
            break
    # Excluded rows also count toward the transport's total, even though they
    # must never trigger an individual repository read or enter the report.
    report["searched_count"] = total
    if report["matches"]:
        report.update(status="regression", reason="new bot-authored Cursor slug PRs found")
    elif now < end:
        report["reason"] = "14-day observation window is still open"
    else:
        report.update(status="clear_search", reason="no matching PRs in the full 14-day window")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix-pr", required=True, help="Merged fix PR: owner/repository#number")
    args = parser.parse_args(argv)
    try:
        report = collect(args.fix_pr, now=datetime.now(UTC))
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        # Do not print subprocess output: it can include authentication details.
        report = {"status": "unknown", "reason": "GitHub evidence unavailable or incomplete"}
    print(json.dumps(report, indent=2, sort_keys=True))
    return {"clear_search": 0, "regression": 1}.get(report["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
