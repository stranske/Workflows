#!/usr/bin/env python3
"""Retain native daily sources and deliver #4501 evidence when it really qualifies.

Runs after the existing Health85 measurement, under its single-writer concurrency.
Unknown and over-target dates leave acceptance open. A qualifying immutable bundle
gets one ready PR, delivered by the normal closer with all merge gates intact.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.ci_time_budget import SOURCE_REPO, GitHub, load_report, timestamp
from scripts.health85_budget_observations import build_observations, build_report
from scripts.issue_4284_completion import reconcile_completion

ROOT = f"/repos/{SOURCE_REPO}"
EVIDENCE = "docs/evidence/issue-4284"
DELIVERY_BRANCH = "health85/issue-4501"
MARKER = "<!-- health85-followup/v1 -->"


def encoded(value: dict | list) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def evaluate(report: dict, now: datetime, *, previous_day: bool = False) -> dict:
    row = report.get(SOURCE_REPO, {})
    retained = row.get("daily_observations", {})
    end = now.date() - timedelta(days=int(previous_day))
    days = [(end - timedelta(days=n)).isoformat() for n in reversed(range(7))]
    rows, missing = [], []
    for day in days:
        item = retained.get(day)
        if not item:
            missing.append(day)
            continue
        value = item.get("p50_minutes")
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"invalid native p50 on {day}")
        measured = timestamp(item["measured_at"])
        if (
            measured.date().isoformat() != day
            or measured > now
            or measured - timestamp(item["window_start"]) != timedelta(days=7)
            or type(item.get("run_id")) is not int
            or item["run_id"] <= 0
        ):
            raise ValueError(f"invalid native observation identity on {day}")
        rows.append({**item, "date": day})
    budget = (
        build_observations(rows)
        if rows
        else {
            "observations": [],
            "qualifying_seven_day_series": False,
            "failures": ["no source-bound native observations retained"],
        }
    )
    for item in budget["observations"]:
        original = retained[item["date"]]
        for key in ("run_attempt", "measured_at", "window_start"):
            item[key] = original.get(key)
    if missing:
        budget["qualifying_seven_day_series"] = False
        budget["failures"].append("missing native dates: " + ", ".join(missing))
    return budget


def file_object(api: GitHub, path: str, ref: str = "main") -> dict:
    raw = api.request("GET", f"{ROOT}/contents/{path}?ref={ref}")
    return json.loads(base64.b64decode(raw["content"]))


def comment_once(api: GitHub, number: int, body: str) -> None:
    digest = hashlib.sha256(body.encode()).hexdigest()
    marker = f"{MARKER}\n<!-- evidence-sha256={digest} -->"
    comments = api.pages(f"{ROOT}/issues/{number}/comments")
    if any(marker in item.get("body", "") for item in comments):
        return
    # A failed/unknown POST is never retried in this run. Next round reads comments.
    api.request("POST", f"{ROOT}/issues/{number}/comments", {"body": marker + "\n" + body})


def sources_completed(api: GitHub, budget: dict) -> bool:
    for row in budget["observations"]:
        run = api.request("GET", f"{ROOT}/actions/runs/{row['run_id']}")
        if (
            run.get("path") != ".github/workflows/health-85-ci-time-budget.yml"
            or run.get("head_branch") != "main"
            or run.get("event") not in {"schedule", "workflow_dispatch"}
            or timestamp(run["created_at"]).date().isoformat() != row["date"]
            or run.get("run_attempt") != row.get("run_attempt", 1)
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
        ):
            return False
    return True


def reconcile(api: GitHub, report: dict, now: datetime) -> dict:
    today = (
        report.get(SOURCE_REPO, {}).get("daily_observations", {}).get(now.date().isoformat(), {})
    )
    # An in-progress native invocation cannot certify its own final conclusion.
    previous_day = str(today.get("run_id", "")) == os.environ.get("GITHUB_RUN_ID", "absent")
    budget = evaluate(report, now, previous_day=previous_day)
    result = {
        "checked_at": now.isoformat(),
        "completion_reconciled": False,
        "budget": budget,
        "action": "retain_incomplete",
        "blocking": 1,
        "drainable": 1,
    }
    branch = DELIVERY_BRANCH
    # One delivery identity survives daily window changes and eventual completion.
    pulls = api.pages(f"{ROOT}/pulls", state="all", head=f"stranske:{branch}")
    if pulls:
        pr = pulls[0]
        result.update(
            action="evidence_pr_merged" if pr.get("merged_at") else "existing_evidence_pr",
            pull_request=pr["html_url"],
            completion_reconciled=bool(pr.get("merged_at")),
        )
        return result
    existing = api.optional(f"{ROOT}/git/ref/heads/{branch}")
    if existing is not None:
        # A ref-created / PR-not-created crash resumes the original frozen series,
        # even when today's observations differ or no longer qualify.
        budget = file_object(api, "docs/reports/ci-budget.json", branch)
        issue = file_object(api, f"{EVIDENCE}/issue-view-4284.json", branch)
        gate = file_object(api, f"{EVIDENCE}/gate-run-40551187519.json")
        decision = reconcile_completion(issue, gate, budget, checked_on=now.date().isoformat())
        result.update(budget=budget, decision=decision)
        if not decision["completion_reconciled"] or not sources_completed(api, budget):
            result["action"] = "existing_branch_requires_reconciliation"
            return result
    else:
        if not budget["qualifying_seven_day_series"]:
            return result
        if not sources_completed(api, budget):
            result["action"] = "await_completed_native_sources"
            return result
        workflow = api.request("GET", f"{ROOT}/actions/workflows/health-85-ci-time-budget.yml")
        report_file = api.request(
            "GET", f"{ROOT}/contents/docs/reports/ci-budget.json?ref=ci-time-budget"
        )
        rows = budget["observations"]
        budget = build_report(
            [workflow], rows, report_branch="ci-time-budget", report_blob_sha=report_file["sha"]
        )
        for row, original in zip(budget["observations"], rows, strict=True):
            for key in ("run_attempt", "measured_at", "window_start"):
                row[key] = original.get(key)
        result["budget"] = budget
        gate = file_object(api, f"{EVIDENCE}/gate-run-40551187519.json")
        series = "\n".join(
            f"- {r['date']}: p50 {r['p50_seconds']:.1f} seconds; {r['source_run_url']}"
            for r in budget["observations"]
        )
        comment_once(api, 4284, "Genuine trailing-seven-day Health85 observations:\n" + series)
        issue = api.request("GET", f"{ROOT}/issues/4284")
        issue["comments"] = api.pages(f"{ROOT}/issues/4284/comments")
        decision = reconcile_completion(issue, gate, budget, checked_on=now.date().isoformat())
        result["decision"] = decision
        if not decision["completion_reconciled"]:
            return result
        bundle = {
            f"{EVIDENCE}/health85-daily-observations.json": budget["observations"],
            "docs/reports/ci-budget.json": budget,
            f"{EVIDENCE}/issue-view-4284.json": issue,
            f"{EVIDENCE}/completion-reconciliation.json": decision,
        }
        parent = api.request("GET", f"{ROOT}/git/ref/heads/main")["object"]["sha"]
        tree = api.request("GET", f"{ROOT}/git/commits/{parent}")["tree"]["sha"]
        entries = []
        for path, data in bundle.items():
            blob = api.request(
                "POST", f"{ROOT}/git/blobs", {"content": encoded(data), "encoding": "utf-8"}
            )
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = api.request("POST", f"{ROOT}/git/trees", {"base_tree": tree, "tree": entries})["sha"]
        commit = api.request(
            "POST",
            f"{ROOT}/git/commits",
            {
                "message": "docs: retain qualifying Health85 series for #4501",
                "tree": tree,
                "parents": [parent],
            },
        )
        api.request(
            "POST", f"{ROOT}/git/refs", {"ref": "refs/heads/" + branch, "sha": commit["sha"]}
        )
    series = "\n".join(
        f"- {r['date']}: p50 {r['p50_seconds']:.1f} seconds; {r['source_run_url']}"
        for r in budget["observations"]
    )
    pr = api.request(
        "POST",
        f"{ROOT}/pulls",
        {
            "head": branch,
            "base": "main",
            "draft": False,
            "title": "docs: retain qualifying Health85 performance evidence",
            "body": "Closes #4501.\n\nSeven actual dated trailing-seven-day Gate p50 observations are <=600 seconds. "
            "The retained #4284 view and completion helper agree. Native run URLs are retained per date. "
            "Normal CI, review, thread and exact-head merge guards apply.\n\n" + series,
        },
    )
    result.update(action="evidence_pr_created", pull_request=pr["html_url"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path, default=Path("health85-followup.json"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    now = datetime.now(UTC)
    api = GitHub(os.environ.get("GH_TOKEN", ""))
    report = json.loads(args.report.read_text()) if args.report else load_report(api)[0]
    result = (
        reconcile(api, report, now)
        if args.apply
        else {
            "completion_reconciled": False,
            "budget": evaluate(report, now),
            "action": "read_only",
        }
    )
    args.output.write_text(encoded(result))
    print(
        f"outcome1 completion_reconciled={result['completion_reconciled']} action={result['action']} "
        f"failures={result['budget']['failures']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
