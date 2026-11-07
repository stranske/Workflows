#!/usr/bin/env python3
"""Collect WF#4082's complete 48-hour Gate cancellation observation with gh.

The caller must obtain --merge from the final campaign PR's current mergedAt.
gh run list paginates up to --limit; saturated results are split into smaller
date windows so the CLI/API limit cannot silently truncate the observation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

try:
    from list_registered_consumer_repos import extract_repos
except ImportError:
    from scripts.list_registered_consumer_repos import extract_repos

ROOT = Path(__file__).resolve().parents[1]
RUN_LIMIT = 1000
FIELDS = "databaseId,conclusion,headSha,createdAt,event"


class CollectionError(ValueError):
    """An incomplete read, retaining query evidence without publishing partial counts."""

    def __init__(self, message: str, commands: list[list[str]]) -> None:
        super().__init__(message)
        self.commands = commands


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def collect_runs(repo: str, start: datetime, end: datetime, deadline: float) -> tuple[list, list]:
    """Read every page, bisecting saturated windows and retaining exact commands."""
    commands = []
    try:
        runs = _collect_runs(repo, start, end, deadline, commands)
    except (ValueError, TypeError) as exc:
        raise CollectionError(str(exc), commands) from exc
    return runs, commands


def _collect_runs(
    repo: str, start: datetime, end: datetime, deadline: float, commands: list[list[str]]
) -> list:
    pending = [(start, end)]
    runs = {}
    while pending:
        lower, upper = pending.pop()
        command = [
            "gh",
            "run",
            "list",
            "-R",
            repo,
            "--workflow",
            "pr-00-gate.yml",
            "--all",  # Include historical runs even if Gate has since been disabled.
            "--created",
            f"{iso(lower)}..{iso(upper)}",
            "--limit",
            str(RUN_LIMIT),
            "--json",
            FIELDS,
        ]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("collection deadline exceeded")
        commands.append(command)
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=remaining, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"gh run list unavailable: {type(exc).__name__}") from exc
        if result.returncode:
            raise ValueError("gh run list failed")
        page = json.loads(result.stdout)
        if not isinstance(page, list):
            raise ValueError("gh run list returned an invalid run list")
        if len(page) >= RUN_LIMIT:
            seconds = int((upper - lower).total_seconds())
            if seconds <= 1:
                raise ValueError("run limit reached in a one-second window; observation incomplete")
            middle = lower + timedelta(seconds=seconds // 2)
            pending.extend([(lower, middle), (middle, upper)])
            continue
        for run in page:
            if not isinstance(run, dict) or any(field not in run for field in FIELDS.split(",")):
                raise ValueError("gh run list returned incomplete run fields")
            if (
                type(run["databaseId"]) is not int
                or not isinstance(run["headSha"], str)
                or not run["headSha"]
            ):
                raise ValueError("run identity or head is missing")
            if not isinstance(run["createdAt"], str) or not isinstance(run["event"], str):
                raise ValueError("run timestamp or event is invalid")
            created = timestamp(run["createdAt"])
            # gh's date range includes the upper endpoint; the observation does not.
            if not start <= created < end:
                continue
            if not isinstance(run["conclusion"], str) or not run["conclusion"]:
                raise ValueError("run has no final conclusion; observation incomplete")
            previous = runs.setdefault(run["databaseId"], run)
            if previous != run:
                raise ValueError("run changed during paginated collection; collect again")
    return list(runs.values())


def counts(runs: list[dict]) -> tuple[int, int]:
    """Count each cancelled PR run once, using distinct same-head siblings <=5s apart."""
    heads = defaultdict(list)
    for run in runs:
        heads[run["headSha"]].append(run)
    numerator = 0
    for siblings in heads.values():
        siblings.sort(key=lambda run: timestamp(run["createdAt"]))
        for index, run in enumerate(siblings):
            if run["conclusion"] != "cancelled" or run["event"] != "pull_request":
                continue
            neighbors = siblings[max(0, index - 1) : index] + siblings[index + 1 : index + 2]
            if any(
                abs((timestamp(other["createdAt"]) - timestamp(run["createdAt"])).total_seconds())
                <= 5
                for other in neighbors
            ):
                numerator += 1
    return numerator, len(runs)


def observe(repos: list[str], merge: datetime, now: datetime, deadline: float) -> dict:
    end = merge + timedelta(hours=48)
    report = {
        "collected_at": iso(now),
        "interval_start": iso(merge),
        "interval_end": iso(end),
        "repos": repos,
        "runs": {},
        "commands": {},
        "errors": {},
        "numerator": None,
        "denominator": None,
        "percentage": None,
        "passed": False,
    }
    if now < end:
        report["status"] = "pending"
        return report
    for repo in repos:
        try:
            report["runs"][repo], report["commands"][repo] = collect_runs(
                repo, merge, end, deadline
            )
        except CollectionError as exc:
            report["commands"][repo] = exc.commands
            report["errors"][repo] = str(exc)
        except (ValueError, TypeError) as exc:
            report["errors"][repo] = str(exc)
    if not repos or report["errors"]:
        report["status"] = "incomplete"
        return report
    totals = [counts(runs) for runs in report["runs"].values()]
    numerator = sum(item[0] for item in totals)
    denominator = sum(item[1] for item in totals)
    report.update(numerator=numerator, denominator=denominator)
    if not denominator:
        report["status"] = "no_runs"
        return report
    report.update(
        status="complete",
        percentage=100 * numerator / denominator,
        passed=numerator * 100 <= denominator * 5,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merge", required=True, help="Verified final campaign mergedAt (UTC)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        merge = timestamp(args.merge)
    except ValueError as exc:
        parser.error(f"invalid --merge: {exc}")
    if merge.microsecond:
        parser.error("mergedAt must have whole-second precision")
    repos = extract_repos(ROOT / ".github/workflows/maint-68-sync-consumer-repos.yml")
    report = observe(repos, merge, datetime.now(UTC), time.monotonic() + 110)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps({key: value for key, value in report.items() if key not in {"runs", "commands"}})
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
