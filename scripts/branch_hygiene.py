#!/usr/bin/env python3
"""Prune stale branches in one repository, so finished work does not leave branches behind.

GitHub already deletes a head branch when its PR merges (delete_branch_on_merge). It never deletes
the branch of a PR closed without merging, nor a branch that never had a PR (local lane and agent
branches). This sweep covers those, under rules that cannot lose work:

  keep     the default branch, protected branches, KEEP_PATTERNS, any branch with an OPEN pull request,
           and any branch whose head commit is newer than --min-age-days (in-flight work).
  delete   a branch whose newest PR is merged or closed AND whose head is still that PR's head (nothing
           was pushed after it closed). GitHub's PR page can restore it.
  delete   a branch with no PR whose head is already contained in the default branch.
  archive  a branch with no PR, with commits of its own, untouched for --archive-after-days: its head
           is first written to refs/archive/branches/<name> (invisible in the branch list, keeps the
           commits reachable), then the branch is deleted. Restore with
           `git push origin refs/archive/branches/<name>:refs/heads/<name>`.
  keep     everything else, named in the report with the reason (FYI only, never a queue).

usage: branch_hygiene.py OWNER/REPO [--apply] [--min-age-days 3] [--archive-after-days 7] [--json PATH]
Dry run by default. Needs `gh` authenticated with contents:write (GH_TOKEN in Actions).
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import subprocess
import sys
import time
from urllib.parse import quote

KEEP_PATTERNS = ("main", "master", "gh-pages", "exports/*", "release-please--*", "dependabot/*", "renovate/*")


def gh(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if check and proc.returncode:
        raise RuntimeError(f"gh api {' '.join(args)} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def gh_json(*args: str):
    out = gh(*args)
    return json.loads(out) if out.strip() else None


def paginate(path: str) -> list:
    out = gh("--paginate", "--slurp", path)
    return [row for page in json.loads(out or "[]") for row in page]


def parse_ts(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def classify(branch: dict, prs: list[dict], default: str, *, head_date: dt.datetime | None,
             contained: bool | None, now: dt.datetime, min_age: int, archive_after: int) -> tuple[str, str]:
    """Return (action, reason). action is keep | delete | archive. Pure: every input is passed in."""
    name = branch["name"]
    if name == default or branch.get("protected"):
        return "keep", "default or protected branch"
    if any(fnmatch.fnmatch(name, pattern) for pattern in KEEP_PATTERNS):
        return "keep", "matches a kept pattern"
    if any(pr["state"] == "open" for pr in prs):
        return "keep", "has an open pull request"
    if head_date is None:
        return "keep", "head commit date unreadable"
    age_days = (now - head_date).total_seconds() / 86400
    if age_days < min_age:
        return "keep", f"head commit {age_days:.1f} days old (in-flight)"
    what = "no PR"
    if prs:
        newest = max(prs, key=lambda pr: pr["number"])
        state = "merged" if newest.get("merged_at") else "closed"
        if newest["head_sha"] == branch["sha"]:
            return "delete", f"PR #{newest['number']} {state}; branch unchanged since (restorable from the PR)"
        # Commits no PR carries: the same footing as a branch that never had a PR.
        what = f"commits pushed after PR #{newest['number']} {state}"
    if contained is None:
        return "keep", f"{what}; containment in the default branch unreadable"
    if contained:
        return "delete", f"{what}; already contained in the default branch"
    if age_days >= archive_after:
        return "archive", f"{what}; own commits, untouched {age_days:.0f} days (kept under refs/archive)"
    return "keep", f"{what}; own commits, {age_days:.0f} days old (< {archive_after:g})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min-age-days", type=float, default=3)
    ap.add_argument("--archive-after-days", type=float, default=7)
    ap.add_argument("--json", dest="json_path")
    args = ap.parse_args(argv)
    repo = args.repo
    now = dt.datetime.now(dt.timezone.utc)
    default = gh_json(f"repos/{repo}")["default_branch"]
    branches = [
        {"name": b["name"], "sha": b["commit"]["sha"], "protected": b.get("protected", False)}
        for b in paginate(f"repos/{repo}/branches?per_page=100")
    ]
    prs_by_ref: dict[str, list[dict]] = {}
    for pr in paginate(f"repos/{repo}/pulls?state=all&per_page=100"):
        head_repo = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
        if head_repo and head_repo != repo:
            continue  # a fork's branch of the same name is not this repository's branch
        prs_by_ref.setdefault(pr["head"]["ref"], []).append(
            {"number": pr["number"], "state": pr["state"], "merged_at": pr.get("merged_at"),
             "head_sha": pr["head"]["sha"]}
        )
    rows = []
    for branch in branches:
        prs = prs_by_ref.get(branch["name"], [])
        head_date = contained = None
        try:
            commit = gh_json(f"repos/{repo}/commits/{branch['sha']}")
            head_date = parse_ts(commit["commit"]["committer"]["date"])
        except Exception:
            pass
        newest_head = max(prs, key=lambda pr: pr["number"])["head_sha"] if prs else None
        if branch["name"] != default and newest_head != branch["sha"]:
            try:
                cmp = gh_json(f"repos/{repo}/compare/{default}...{branch['sha']}")
                contained = cmp["ahead_by"] == 0
            except Exception:
                contained = None
        action, reason = classify(branch, prs, default, head_date=head_date, contained=contained,
                                  now=now, min_age=args.min_age_days, archive_after=args.archive_after_days)
        rows.append({"branch": branch["name"], "sha": branch["sha"], "action": action, "reason": reason})

    done = {"delete": 0, "archive": 0, "failed": 0}
    if args.apply:
        for row in rows:
            if row["action"] not in ("delete", "archive"):
                continue
            ref = quote(f"heads/{row['branch']}", safe="/")
            try:
                if row["action"] == "archive":
                    gh("-X", "POST", f"repos/{repo}/git/refs", "-f",
                       f"ref=refs/archive/branches/{row['branch']}", "-f", f"sha={row['sha']}")
                current = gh_json(f"repos/{repo}/git/ref/{ref}")
                if current["object"]["sha"] != row["sha"]:
                    row["result"] = "skipped: branch moved since it was read"
                    continue
                gh("-X", "DELETE", f"repos/{repo}/git/refs/{ref}")
                row["result"] = "done"
                time.sleep(1)  # stay under GitHub's secondary limit on write requests
                done[row["action"]] += 1
            except Exception as exc:  # report and continue; one failure never stops the sweep
                row["result"] = f"failed: {exc}"
                done["failed"] += 1

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    summary = {"repo": repo, "applied": args.apply, "branches": len(rows), "counts": counts, "done": done}
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump({"summary": summary, "rows": rows}, fh, indent=1)
    verb = "pruned" if args.apply else "would prune"
    print(f"branch hygiene {repo}: {len(rows)} branches; {verb} delete={counts.get('delete', 0)} "
          f"archive={counts.get('archive', 0)}; keep={counts.get('keep', 0)}"
          + (f"; failed={done['failed']}" if args.apply else ""))
    for row in rows:
        if row["action"] != "keep":
            print(f"  {row['action']:7s} {row['branch']}  ({row['reason']}){'  -> ' + row['result'] if 'result' in row else ''}")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Branch hygiene: {repo}\n\n{json.dumps(summary)}\n\n| action | branch | reason |\n|---|---|---|\n")
            for row in rows:
                fh.write(f"| {row['action']} | `{row['branch']}` | {row['reason']} {row.get('result', '')} |\n")
    return 1 if done["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
