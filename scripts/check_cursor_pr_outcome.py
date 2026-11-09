#!/usr/bin/env python3
"""Read-only Cursor PR search; a separate mid-run merge observation is required.

Exit 0: clear 14-day search; 1: matching PR; 2: pending/unavailable.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit

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
    command = ["gh", "api", "--method", "GET", endpoint]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError("Expected a GitHub API object")
    return data


def collect(fix_pr: str, *, now: datetime, api=gh_json) -> dict:
    """Search a fixed 14-day window; reject incomplete or truncated evidence."""
    match = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)", fix_pr)
    if not match:
        raise ValueError("Use owner/repository#number for PR references")
    repo, number = match.groups()
    if repo.lower() in EXCLUDED_REPOS:
        raise ValueError("PR repository is excluded by owner policy")
    owner = repo.split("/")[0]
    report = {
        "fix_pr": fix_pr,
        "observed_at": now.isoformat(),
        "status": "pending",
        "matches": [],
        "blocking": 1,
        "drainable": 1,
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
    query = (
        f"is:pr user:{owner} author:app/github-actions "
        f"created:{start.date()}..{now.date()} "
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
            path = urlsplit(item["repository_url"]).path
            item_repo_match = re.fullmatch(r"/repos/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", path)
            if not item_repo_match:
                raise ValueError("Unexpected search repository path")
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
    report["searched_count"] = len(seen)
    if report["matches"]:
        report.update(status="regression", reason="new bot-authored Cursor slug PRs found")
    elif now < end:
        report["reason"] = "14-day observation window is still open"
    else:
        report.update(status="clear_search", reason="no matching PRs in the full 14-day window")
    report["blocking"] = len(report["matches"]) or int(report["status"] != "clear_search")
    report["drainable"] = int(report["status"] != "clear_search")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix-pr", required=True, help="Merged fix PR: owner/repository#number")
    args = parser.parse_args(argv)
    try:
        report = collect(args.fix_pr, now=datetime.now(UTC))
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        report = {
            "status": "unknown",
            "reason": "GitHub evidence unavailable or incomplete",
            "blocking": 1,
            "drainable": 1,
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return {"clear_search": 0, "regression": 1}.get(report["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
