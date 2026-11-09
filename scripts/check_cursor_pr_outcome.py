#!/usr/bin/env python3
"""Collect the read-only PR-search component of Cursor's post-merge acceptance.

Usage: python scripts/check_cursor_pr_outcome.py --fix-pr stranske/Workflows#4564

Exit codes: 0 = complete search window with no matches, 1 = regression,
2 = pending or unavailable evidence. Even exit 0 requires separate evidence of
the next keepalive target merging during Run Cursor; this command cannot prove
that event. All PR states are searched, including closed orphan PRs.

Optional --target-pr owner/repository#number --job-id ID records merge timing
and the completed guard/push steps. Add --receipt-comment-id ID to verify the
source-issue receipt linking that job to the target PR and retain reported SHAs.
The next-target ordering still needs separate evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
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


def pr_reference(value: str) -> tuple[str, str]:
    match = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)", value)
    if not match:
        raise ValueError("Use owner/repository#number for PR references")
    repo, number = match.groups()
    if repo.lower() in EXCLUDED_REPOS:
        raise ValueError("PR repository is excluded by owner policy")
    return repo, number


def collect_mid_run_merge(
    target_pr: str,
    job_id: int,
    *,
    start: datetime,
    end: datetime,
    now: datetime,
    api=gh_json,
    receipt_comment_id: int | None = None,
) -> dict:
    """Check timing and optionally bind the target/run via its source-issue receipt."""
    repo, number = pr_reference(target_pr)
    if type(job_id) is not int or job_id <= 0:
        raise ValueError("Job ID must be a positive integer")
    if receipt_comment_id is not None and (
        type(receipt_comment_id) is not int or receipt_comment_id <= 0
    ):
        raise ValueError("Receipt comment ID must be a positive integer")
    pull = api(f"repos/{repo}/pulls/{number}")
    merged = timestamp(pull["merged_at"])
    job = api(f"repos/{repo}/actions/jobs/{job_id}")
    if job["id"] != job_id or job["status"] != "completed" or job["conclusion"] != "success":
        raise ValueError("Expected the requested job to have completed successfully")
    run_id = job["run_id"]
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("Invalid job run ID")
    evidence_steps = []
    for name, conclusion in (
        ("Run Cursor", "success"),
        ("Check target PR before pushing", "success"),
        ("Commit and push changes", "skipped"),
    ):
        matching = [step for step in job["steps"] if step["name"] == name]
        if len(matching) != 1:
            raise ValueError("Missing or ambiguous Cursor evidence step")
        step = matching[0]
        if step["status"] != "completed" or step["conclusion"] != conclusion:
            raise ValueError("Cursor guard/push outcomes do not establish a successful skip")
        if type(step["number"]) is not int or step["number"] <= 0:
            raise ValueError("Invalid Cursor step number")
        evidence_steps.append(step)
    cursor, guard, push = evidence_steps
    cursor_start = timestamp(cursor["started_at"])
    cursor_end = timestamp(cursor["completed_at"])
    guard_start = timestamp(guard["started_at"])
    guard_end = timestamp(guard["completed_at"])
    # Equal merge/step boundaries are ambiguous at GitHub's timestamp precision.
    if not (
        start <= cursor_start < merged < cursor_end <= guard_start <= guard_end <= now
        and merged <= end
        and cursor["number"] < guard["number"] < push["number"]
    ):
        raise ValueError("Merge was not demonstrably during Run Cursor after deployment")
    evidence = {
        "status": "timing_verified",
        "target_pr": target_pr,
        "merged_at": pull["merged_at"],
        "job_id": job_id,
        "run_url": f"https://github.com/{repo}/actions/runs/{run_id}",
        "cursor_started_at": cursor["started_at"],
        "cursor_completed_at": cursor["completed_at"],
        "guard_conclusion": guard["conclusion"],
        "push_conclusion": push["conclusion"],
        "target_run_association": "required separately from the source-issue receipt",
        "next_target_verification": "required separately; this may not be the next matching run",
    }
    if receipt_comment_id is not None:
        comment = api(f"repos/{repo}/issues/comments/{receipt_comment_id}")
        if type(comment["id"]) is not int or comment["id"] != receipt_comment_id:
            raise ValueError("Receipt comment ID does not match the requested comment")
        created = timestamp(comment["created_at"])
        if not guard_start <= created <= guard_end or timestamp(comment["updated_at"]) != created:
            raise ValueError("Receipt must be unedited and created during the guard step")
        # A fixed local Node entry point shares the workflow's actual source
        # resolver. JSON travels on stdin, never through shell interpolation.
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("check_cursor_receipt.js"))],
            input=json.dumps(
                {"pull": pull, "comment": comment, "repo": repo, "number": number, "runId": run_id}
            ),
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        receipt = json.loads(result.stdout)
        evidence.update(
            source_issue_receipt=receipt,
            target_run_association="verified from the source-issue receipt",
        )
    return evidence


def collect(
    fix_pr: str,
    *,
    now: datetime,
    api=gh_json,
    target_pr: str | None = None,
    job_id: int | None = None,
    receipt_comment_id: int | None = None,
) -> dict:
    """Search a fixed 14-day window; reject incomplete or truncated evidence."""
    repo, number = pr_reference(fix_pr)
    owner = repo.split("/")[0]
    if (target_pr is None) != (job_id is None):
        raise ValueError("Supply both target PR and job ID")
    if receipt_comment_id is not None and (
        target_pr is None or type(receipt_comment_id) is not int or receipt_comment_id <= 0
    ):
        raise ValueError("Receipt comment ID requires a target/job and must be a positive integer")
    if target_pr is not None:
        target_repo, _ = pr_reference(target_pr)
        if target_repo.split("/")[0].lower() != owner.lower():
            raise ValueError("Target PR must belong to the fix repository owner")
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
    if target_pr is not None:
        report["mid_run_merge_verification"] = collect_mid_run_merge(
            target_pr,
            job_id,
            start=start,
            end=end,
            now=now,
            api=api,
            receipt_comment_id=receipt_comment_id,
        )
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix-pr", required=True, help="Merged fix PR: owner/repository#number")
    parser.add_argument("--target-pr", help="Candidate mid-run merged PR: owner/repository#number")
    parser.add_argument(
        "--job-id", type=int, help="Completed Cursor job ID in the target repository"
    )
    parser.add_argument(
        "--receipt-comment-id", type=int, help="Source-issue comment ID for the candidate run"
    )
    args = parser.parse_args(argv)
    try:
        report = collect(
            args.fix_pr,
            now=datetime.now(UTC),
            target_pr=args.target_pr,
            job_id=args.job_id,
            receipt_comment_id=args.receipt_comment_id,
        )
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        # Do not print subprocess output: it can include authentication details.
        report = {"status": "unknown", "reason": "GitHub evidence unavailable or incomplete"}
    print(json.dumps(report, indent=2, sort_keys=True))
    return {"clear_search": 0, "regression": 1}.get(report["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
