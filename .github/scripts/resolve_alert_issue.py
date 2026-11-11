#!/usr/bin/env python3
"""Close a workflow's own failure-alert issue once a later run succeeds.

Producers that open an "Action Required" alert issue on failure call this from
a success path.  The helper only touches open issues that carry every
``--label`` AND whose title matches ``--title`` (exact) or ``--title-prefix``,
so another producer's issue that shares a label is never closed.

Output is always one line that distinguishes the three outcomes:
``closed #N ...``, ``no open alert ...`` (nothing to do) and, on failure, a
non-zero exit with the gh error.  Closing is best-effort for callers: run it in
a ``continue-on-error`` step so a flaky API call cannot fail a green run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence

Runner = Callable[[Sequence[str]], str]

LIST_LIMIT = "100"


def _gh(args: Sequence[str]) -> str:
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return result.stdout


def matches(title: str, titles: Sequence[str], prefixes: Sequence[str]) -> bool:
    return title in titles or any(title.startswith(p) for p in prefixes)


def resolve_alerts(
    *,
    repo: str,
    labels: Sequence[str],
    titles: Sequence[str] = (),
    title_prefixes: Sequence[str] = (),
    run_url: str = "",
    workflow: str = "",
    run: Runner = _gh,
) -> list[int]:
    """Close matching open alert issues; return the numbers closed."""
    if not labels:
        raise ValueError("at least one --label is required")
    if not titles and not title_prefixes:
        raise ValueError("--title or --title-prefix is required")
    list_args = ["issue", "list", "--repo", repo, "--state", "open"]
    for label in labels:
        list_args += ["--label", label]
    list_args += ["--limit", LIST_LIMIT, "--json", "number,title"]
    issues = json.loads(run(list_args) or "[]")
    closed: list[int] = []
    who = workflow or "The producing workflow"
    link = f" ({run_url})" if run_url else ""
    comment = (
        f"### Resolved: later run succeeded\n\n{who} completed successfully"
        f"{link} after this alert was opened, so the condition it reported "
        "has cleared. Closing automatically; the next failure opens a new alert."
    )
    for issue in issues:
        if not matches(str(issue.get("title", "")), titles, title_prefixes):
            continue
        number = int(issue["number"])
        run(
            [
                "issue",
                "close",
                str(number),
                "--repo",
                repo,
                "--reason",
                "completed",
                "--comment",
                comment,
            ]
        )
        closed.append(number)
    return closed


def main(argv: Sequence[str] | None = None, run: Runner = _gh) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--label", action="append", default=[], dest="labels")
    parser.add_argument("--title", action="append", default=[], dest="titles")
    parser.add_argument("--title-prefix", action="append", default=[], dest="prefixes")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--workflow", default="")
    args = parser.parse_args(argv)
    if not args.labels or not (args.titles or args.prefixes):
        parser.error("need at least one --label and one --title/--title-prefix")
    try:
        closed = resolve_alerts(
            repo=args.repo,
            labels=args.labels,
            titles=args.titles,
            title_prefixes=args.prefixes,
            run_url=args.run_url,
            workflow=args.workflow,
            run=run,
        )
    except subprocess.CalledProcessError as exc:
        print(f"alert resolution failed: {exc.stderr or exc}", file=sys.stderr)
        return 1
    if closed:
        print("closed " + ", ".join(f"#{n}" for n in closed) + " (producer succeeded)")
    else:
        print(f"no open alert with labels {','.join(args.labels)} matched; nothing to close")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
