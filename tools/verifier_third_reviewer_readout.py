#!/usr/bin/env python3
"""Read out the verifier's third-reviewer experiment (config/llm_slots.json `capacity_backup_experiment`).

On a sampled share of standard compare runs, one capacity backup drawn at random judges as an
uncounted third reviewer. Each record lives in that run's ``comparison-results-<run id>`` artifact
(``comparison.json``, key ``third_reviewer``). This script collects them across repositories and
prints, per backup: how many runs sampled it, how many gave a usable answer, how often it agreed
with the production pair, and how often counting it would have changed the conclusion.

Evidence class: production use on live work, unadjudicated. "Changes the conclusion" means the
third verdict would have moved the gate's verdict; whether that move was right needs the PR's later
outcome or an adjudicator.

    python tools/verifier_third_reviewer_readout.py --since 2026-11-12 --repos stranske/Workflows ...
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import zipfile
from collections import defaultdict
from typing import Any

WORKFLOW = "agents-verifier.yml"
SCHEMA = "verifier-third-reviewer/v1"


def _gh(args: list[str], *, binary: bool = False) -> Any:
    out = subprocess.run(["gh", *args], capture_output=True, check=True)
    return out.stdout if binary else json.loads(out.stdout or b"null")


def _class(verdict: str | None) -> str:
    if verdict == "PASS":
        return "PASS"
    if verdict in ("CONCERNS", "FAIL"):
        return "FINDING"
    return "UNVERIFIABLE"


def records_for_repo(repo: str, since: str, limit: int) -> list[dict[str, Any]]:
    runs = (
        _gh(
            [
                "run",
                "list",
                "-R",
                repo,
                "-w",
                WORKFLOW,
                "--created",
                f">={since}",
                "-L",
                str(limit),
                "--json",
                "databaseId",
            ]
        )
        or []
    )
    found = []
    for run in runs:
        run_id = run["databaseId"]
        name = f"comparison-results-{run_id}"
        artifacts = _gh(["api", f"repos/{repo}/actions/runs/{run_id}/artifacts?name={name}"]) or {}
        for artifact in artifacts.get("artifacts", []):
            if artifact.get("name") != name or artifact.get("expired"):
                continue
            blob = _gh(["api", f"repos/{repo}/actions/artifacts/{artifact['id']}/zip"], binary=True)
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                if "comparison.json" not in archive.namelist():
                    continue
                try:
                    payload = json.loads(archive.read("comparison.json"))
                except ValueError:
                    continue
            record = payload.get("third_reviewer") if isinstance(payload, dict) else None
            if isinstance(record, dict) and record.get("schema") == SCHEMA:
                found.append({**record, "repo": repo, "run_id": run_id})
    return found


def summarise(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in records:
        key = f"{record.get('provider') or 'unknown'}/{record.get('model') or 'unknown'}"
        row = rows[key]
        row["sampled"] += 1
        if not record.get("usable"):
            row["unusable"] += 1
            continue
        row["usable"] += 1
        third, pair = _class(record.get("verdict")), _class(record.get("pair_verdict"))
        row["agrees_with_pair"] += third == pair
        row["changes_conclusion"] += bool(record.get("changes_conclusion"))
        row["finding_where_pair_passed"] += third == "FINDING" and pair == "PASS"
        row["pass_where_pair_found"] += third == "PASS" and pair == "FINDING"
    return [{"backup": key, **dict(values)} for key, values in sorted(rows.items())]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repos", nargs="+", required=True)
    parser.add_argument("--since", required=True, help="YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=300, help="verifier runs per repository")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    records: list[dict[str, Any]] = []
    unreadable = []
    for repo in args.repos:
        try:
            records += records_for_repo(repo, args.since, args.limit)
        except subprocess.CalledProcessError as exc:
            unreadable.append(repo)
            print(f"{repo}: unreadable ({exc.returncode})", file=sys.stderr)
    if unreadable:
        # A partial read must not look like "no samples yet".
        print(f"readout incomplete: {len(unreadable)} repositories unreadable", file=sys.stderr)
        return 1
    rows = summarise(records)
    if args.json:
        print(json.dumps({"records": len(records), "backups": rows}, indent=2))
        return 0
    print(f"third-reviewer records since {args.since}: {len(records)}")
    if not rows:
        print(
            "no sampled runs yet (fully drained is not applicable: this is a sample, not a queue)"
        )
    for row in rows:
        print(
            f"{row['backup']}: sampled {row.get('sampled', 0)}, usable {row.get('usable', 0)}, "
            f"agrees with pair {row.get('agrees_with_pair', 0)}, "
            f"changes conclusion {row.get('changes_conclusion', 0)} "
            f"(finding where pair passed {row.get('finding_where_pair_passed', 0)}, "
            f"pass where pair found {row.get('pass_where_pair_found', 0)})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
