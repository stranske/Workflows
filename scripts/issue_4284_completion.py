#!/usr/bin/env python3
"""Reconcile issue #4284 completion only after both live-verification gates pass.

The check consumes ``gh issue view 4284 --json state,body,comments`` together
with the retained Gate-run evidence and ``docs/reports/ci-budget.json``.
Completion is reconciled only when the named Python jobs finished within 600
seconds and the issue text matches a qualifying seven-day Health 85 series.
A closed follow-up transfer does not count as acceptance.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.gate_run_view_evidence import DEFAULT_MAX_SECONDS, DEFAULT_RUN_ID, NAMED_JOBS

ISSUE_NUMBER = 4284
SCHEMA = "issue-4284-completion-reconciliation/v1"
ISSUE_VIEW_COMMAND = "gh issue view 4284 --repo stranske/Workflows --json state,body,comments"
_FOLLOWUP_RE = re.compile(r"followup=#(\d+)")
_CHECKED_HEALTH85_RE = re.compile(
    r"(?m)^- \[x\] Live-verification gate: Health 85 reports",
    re.IGNORECASE,
)


def issue_text(issue: Mapping[str, Any]) -> str:
    """Join the issue body and comment bodies in payload order."""
    parts = [str(issue.get("body") or "")]
    comments = issue.get("comments")
    if isinstance(comments, list):
        for comment in comments:
            if isinstance(comment, Mapping):
                parts.append(str(comment.get("body") or ""))
    return "\n".join(parts)


def followup_issue(issue: Mapping[str, Any]) -> int | None:
    """Return the last closer-core follow-up issue id, if one was recorded."""
    found: int | None = None
    comments = issue.get("comments")
    if not isinstance(comments, list):
        return None
    for comment in comments:
        if not isinstance(comment, Mapping):
            continue
        body = str(comment.get("body") or "")
        if "action=followup" not in body:
            continue
        match = _FOLLOWUP_RE.search(body)
        if match:
            found = int(match.group(1))
    return found


def sustained_checkbox_checked(issue: Mapping[str, Any]) -> bool:
    """True when the issue body already checks the Health 85 acceptance gate."""
    return _CHECKED_HEALTH85_RE.search(str(issue.get("body") or "")) is not None


def gate_run_supported(evidence: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Require run 40551187519 and both named Python jobs within 600 seconds."""
    failures: list[str] = []
    if evidence.get("run_id") != DEFAULT_RUN_ID:
        failures.append(f"run_id is {evidence.get('run_id')!r}, expected {DEFAULT_RUN_ID}")
    jobs = evidence.get("jobs")
    by_name: dict[str, Mapping[str, Any]] = {}
    if isinstance(jobs, list):
        for row in jobs:
            if isinstance(row, Mapping) and isinstance(row.get("name"), str):
                by_name[row["name"]] = row
    for name in NAMED_JOBS:
        row = by_name.get(name)
        if row is None:
            failures.append(f"missing job {name}")
            continue
        seconds = row.get("seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            failures.append(f"{name} has no duration")
        elif float(seconds) > DEFAULT_MAX_SECONDS:
            failures.append(f"{name} took {float(seconds):.0f}s (limit {DEFAULT_MAX_SECONDS:.0f}s)")
        if row.get("status") != "completed" or row.get("conclusion") != "success":
            failures.append(f"{name} is not completed/success")
        url = row.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            failures.append(f"{name} has no job URL")
    if evidence.get("passed") is not True:
        if not failures:
            failures.append("gate evidence passed flag is false")
        for item in evidence.get("failures") or []:
            text = str(item)
            if text not in failures:
                failures.append(text)
    return not failures, failures


def _computed_series_failures(report: Mapping[str, Any]) -> list[str]:
    observations = report.get("observations")
    if not isinstance(observations, list):
        return ["observations must be a list"]
    failures: list[str] = []
    if len(observations) != 7:
        failures.append(f"expected 7 daily observations, found {len(observations)}")
    dates: list[date] = []
    for row in observations:
        if not isinstance(row, Mapping):
            failures.append("observation is not an object")
            continue
        raw_day = str(row.get("date") or "")
        try:
            day = date.fromisoformat(raw_day)
        except ValueError:
            failures.append(f"invalid observation date: {raw_day!r}")
            continue
        dates.append(day)
        seconds = row.get("p50_seconds")
        if seconds is None or isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            failures.append(f"{day.isoformat()}: p50 missing")
        elif float(seconds) > DEFAULT_MAX_SECONDS:
            failures.append(
                f"{day.isoformat()}: p50 {float(seconds):.1f}s exceeds {DEFAULT_MAX_SECONDS:.0f}s"
            )
        url = row.get("source_run_url")
        if not isinstance(url, str) or "/actions/runs/" not in url:
            failures.append(f"{day.isoformat()}: missing Health 85 source URL")
    if len(dates) == len(observations) and dates:
        consecutive = dates == sorted(dates) and all(
            later - earlier == timedelta(days=1) for earlier, later in zip(dates, dates[1:])
        )
        if not consecutive:
            failures.append("observation dates are not consecutive calendar days")
    return failures


def sustained_series_supported(report: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Accept a seven-day series only when every stored p50 is at or below 600 seconds."""
    computed = _computed_series_failures(report)
    flagged = report.get("qualifying_seven_day_series") is True
    if flagged and not computed:
        return True, []
    if not flagged:
        stored = [str(item) for item in (report.get("failures") or [])]
        if stored:
            return False, stored
        if computed:
            return False, computed
        return False, ["qualifying_seven_day_series is false"]
    return False, computed


def matching_observation_dates(
    report: Mapping[str, Any], issue: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    """Require each budget row's date, p50 seconds, and Health 85 URL on one issue line."""
    lines = issue_text(issue).splitlines()
    observations = report.get("observations")
    if not isinstance(observations, list):
        return [], ["budget observations are missing"]
    matched: list[str] = []
    failures: list[str] = []
    for row in observations:
        if not isinstance(row, Mapping):
            failures.append("observation is not an object")
            continue
        day = str(row.get("date") or "")
        url = str(row.get("source_run_url") or "")
        seconds = row.get("p50_seconds")
        found = False
        for line in lines:
            if not day or day not in line or not url or url not in line:
                continue
            if seconds is None:
                found = "missing" in line.lower()
            elif isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
                found = f"{float(seconds):.1f}" in line
            if found:
                break
        if found:
            matched.append(day)
        else:
            failures.append(f"{day}: issue text has no matching Health 85 p50 line")
    return matched, failures


def _flag(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def reconciliation_comment(decision: Mapping[str, Any]) -> str:
    """Render the issue comment that records the reconciliation decision."""
    followup = decision.get("followup_issue")
    followup_text = f"#{followup}" if followup else "none"
    lines = [
        f"## Completion reconciliation checked {decision['checked_on']}",
        "",
        f"`{ISSUE_VIEW_COMMAND}`",
        "",
        f"- state: `{decision['state']}`",
        f"- follow-up issue: {followup_text}",
        f"- Gate run {DEFAULT_RUN_ID} jobs within 600s: {_flag(decision['gate_run_supported'])}",
        "- qualifying seven-day Health 85 series: "
        f"{_flag(decision['sustained_series_supported'])}",
        "- ci-budget.json observations match #4284: "
        f"{_flag(decision['observations_match_issue'])}",
        f"- completion reconciled: {_flag(decision['completion_reconciled'])}",
        "",
    ]
    if decision["completion_reconciled"]:
        lines.append(
            "Both acceptance gates have supporting evidence. "
            "Completion may be reconciled from this record."
        )
    else:
        lines.append(
            "Completion stays unreconciled until both the named Gate jobs "
            "and a matching seven-day Health 85 series at or below 600 seconds are supported. "
            "The sustained-performance criterion stays incomplete. "
            "Issue state and acceptance checkboxes were left unchanged."
        )
    failures = decision.get("failures") or []
    if failures:
        lines.extend(["", "Failures:"])
        lines.extend(f"- {failure}" for failure in failures)
    lines.append("")
    return "\n".join(lines)


def reconcile_completion(
    issue: Mapping[str, Any],
    gate_evidence: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    checked_on: str = "2026-11-06",
) -> dict[str, Any]:
    """Decide whether #4284 completion is supported. This function does not edit GitHub."""
    state = issue.get("state")
    if not isinstance(state, str) or not state:
        raise ValueError("issue view state must be a non-empty string")
    comments = issue.get("comments")
    comment_count = len(comments) if isinstance(comments, list) else 0
    gate_ok, gate_failures = gate_run_supported(gate_evidence)
    series_ok, series_failures = sustained_series_supported(report)
    matched_dates, match_failures = matching_observation_dates(report, issue)
    match_ok = not match_failures
    both = gate_ok and series_ok and match_ok
    failures = [*gate_failures, *series_failures, *match_failures]
    if sustained_checkbox_checked(issue) and not both:
        failures.append("issue body checks the Health 85 gate without qualifying evidence")
    decision = {
        "schema": SCHEMA,
        "issue": ISSUE_NUMBER,
        "command": ISSUE_VIEW_COMMAND,
        "checked_on": checked_on,
        "state": state,
        "comment_count": comment_count,
        "followup_issue": followup_issue(issue),
        "gate_run_supported": gate_ok,
        "sustained_series_supported": series_ok,
        "observations_match_issue": match_ok,
        "both_gates_supported": both,
        "completion_reconciled": both,
        "action": "mark_complete" if both else "leave_incomplete",
        "issue_mutation": "none",
        "sustained_performance_criterion": "complete" if series_ok and match_ok else "incomplete",
        "matched_dates": matched_dates,
        "failures": failures,
    }
    decision["comment"] = reconciliation_comment(decision)
    return decision


def decision_json(decision: Mapping[str, Any]) -> str:
    return json.dumps(decision, indent=2) + "\n"


def _load_object(path: Path) -> dict[str, Any] | None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print(f"{path} must contain a JSON object", file=sys.stderr)
        return None
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue-view", type=Path, required=True)
    parser.add_argument("--gate-evidence", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checked-on", default="2026-11-06")
    args = parser.parse_args(argv)
    issue = _load_object(args.issue_view)
    evidence = _load_object(args.gate_evidence)
    report = _load_object(args.budget)
    if issue is None or evidence is None or report is None:
        return 1
    try:
        decision = reconcile_completion(
            issue,
            evidence,
            report,
            checked_on=args.checked_on,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(decision_json(decision), encoding="utf-8")
    print(
        f"action={decision['action']} "
        f"completion_reconciled={decision['completion_reconciled']} "
        f"state={decision['state']} "
        f"followup_issue={decision['followup_issue']}"
    )
    for failure in decision["failures"]:
        print(f"  - {failure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
