#!/usr/bin/env python3
"""Raise or close a workflow's own failure-alert issue.

``--mode resolve`` (the default) closes the alert once a later run succeeds.
``--mode raise`` is the matching failure path (cohesion review A5b): it edits
the body of the open alert with the exact ``--title`` if there is one, and
otherwise opens it, so each failed run produces exactly one issue update and a
daily failure never stacks duplicate issues.

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


def raise_alert(
    *,
    repo: str,
    labels: Sequence[str],
    title: str,
    body_file: str,
    run: Runner = _gh,
) -> tuple[str, int | None]:
    """Open the alert, or edit the open one with the same title; one write either way."""
    if not labels:
        raise ValueError("at least one --label is required")
    if not title:
        raise ValueError("--mode raise needs exactly one exact --title")
    list_args = ["issue", "list", "--repo", repo, "--state", "open"]
    for label in labels:
        list_args += ["--label", label]
    list_args += ["--limit", LIST_LIMIT, "--json", "number,title"]
    issues = json.loads(run(list_args) or "[]")
    existing = next((i for i in issues if str(i.get("title", "")) == title), None)
    if existing is not None:
        number = int(existing["number"])
        run(["issue", "edit", str(number), "--repo", repo, "--body-file", body_file])
        return "updated", number
    create_args = ["issue", "create", "--repo", repo, "--title", title, "--body-file", body_file]
    for label in labels:
        create_args += ["--label", label]
    url = run(create_args).strip()
    tail = url.rsplit("/", 1)[-1]
    return "opened", int(tail) if tail.isdigit() else None


def main(argv: Sequence[str] | None = None, run: Runner = _gh) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--label", action="append", default=[], dest="labels")
    parser.add_argument("--title", action="append", default=[], dest="titles")
    parser.add_argument("--title-prefix", action="append", default=[], dest="prefixes")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--workflow", default="")
    parser.add_argument("--mode", choices=("resolve", "raise"), default="resolve")
    parser.add_argument("--body-file", default="")
    args = parser.parse_args(argv)
    if not args.labels or not (args.titles or args.prefixes):
        parser.error("need at least one --label and one --title/--title-prefix")
    if args.mode == "raise":
        if len(args.titles) != 1 or args.prefixes or not args.body_file:
            parser.error("--mode raise needs exactly one --title, no --title-prefix, and --body-file")
        try:
            action, number = raise_alert(
                repo=args.repo,
                labels=args.labels,
                title=args.titles[0],
                body_file=args.body_file,
                run=run,
            )
        except subprocess.CalledProcessError as exc:
            print(f"alert raise failed: {exc.stderr or exc}", file=sys.stderr)
            return 1
        print(f"{action} #{number if number is not None else '?'} ({args.titles[0]})")
        return 0
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
