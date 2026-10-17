#!/usr/bin/env python3
"""Join keepalive completion records to PR label timelines for agent-switch cadence.

Campaign check for issue #3989: over rate-limited completions, the median number of
additional rounds between a provider rate-limit and the concrete agent switch must
be 0 (same evaluate). Rows include the completion ``reason`` column so rate-limited
events are distinguishable from stall-driven switches.

The collector accepts a portable JSON snapshot so live GitHub history and hermetic
replays share one calculator.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

SCHEMA = "workflows.agent-switch-cadence/v1"
NON_ROUTING_AGENT_SUFFIXES = frozenset({"auto", "needs-attention", "rate-limited", "retry"})
AGENT_LABEL_RE = re.compile(r"^agent:(?P<name>[a-z0-9][a-z0-9_-]*)$")
CONTROL_LABELS = frozenset(
    {
        "agent:auto",
        "agent:needs-attention",
        "agent:rate-limited",
        "agent:retry",
    }
)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except (AttributeError, OverflowError, TypeError, ValueError):
        return None


def _label_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "").strip().lower()
    return str(value or "").strip().lower()


def concrete_agent(label: str) -> str | None:
    """Return the concrete agent key for a routing label, else None."""
    match = AGENT_LABEL_RE.match(label)
    if not match:
        return None
    name = match.group("name")
    if name in NON_ROUTING_AGENT_SUFFIXES:
        return None
    return name


def _completion_reason(record: dict[str, Any]) -> str:
    completion = record.get("completion")
    if isinstance(completion, dict) and completion.get("reason"):
        return str(completion["reason"])
    return str(record.get("reason") or "")


def _completion_time(record: dict[str, Any]) -> datetime | None:
    return parse_time(
        str(record.get("completed_at") or record.get("completedAt") or record.get("at") or "")
    )


def _event_time(event: dict[str, Any]) -> datetime | None:
    return parse_time(str(event.get("created_at") or event.get("at") or ""))


def _repo_pr_key(item: dict[str, Any]) -> tuple[str, int] | None:
    repo = str(item.get("repo") or item.get("repository") or "").strip()
    try:
        pr = int(item.get("pr") or item.get("pr_number") or item.get("number") or 0)
    except (TypeError, ValueError):
        return None
    if not repo or pr <= 0:
        return None
    return repo, pr


def _sorted_completions(completions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dated: list[tuple[datetime, int, dict[str, Any]]] = []
    for index, record in enumerate(completions):
        when = _completion_time(record)
        if when is None:
            continue
        dated.append((when, index, record))
    dated.sort(key=lambda item: (item[0], item[1]))
    return [record for _, _, record in dated]


def _find_switch_event(
    events: list[dict[str, Any]],
    *,
    after: datetime,
    from_agent: str,
) -> dict[str, Any] | None:
    """First later label event that applies a different concrete agent."""
    candidates: list[tuple[datetime, int, dict[str, Any]]] = []
    for index, event in enumerate(events):
        when = _event_time(event)
        if when is None or when < after:
            continue
        if str(event.get("event") or event.get("action") or "").lower() not in {
            "labeled",
            "label",
        }:
            continue
        agent = concrete_agent(_label_name(event.get("label") or event.get("name")))
        if agent is None or agent == from_agent:
            continue
        candidates.append((when, index, event))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def additional_rounds_until_switch(
    completions: list[dict[str, Any]],
    *,
    rate_limited_at: datetime,
    switch_at: datetime,
) -> int:
    """Count completions strictly after the rate-limit and at/before the switch."""
    count = 0
    for record in completions:
        when = _completion_time(record)
        if when is None:
            continue
        if rate_limited_at < when <= switch_at:
            count += 1
    return count


def pair_rate_limited_switches(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Join rate_limited completions to the next concrete agent label add."""
    completions = list(snapshot.get("completions") or [])
    events = list(snapshot.get("label_events") or snapshot.get("label_timeline") or [])
    by_pr: dict[tuple[str, int], dict[str, list[dict[str, Any]]]] = {}
    for record in completions:
        key = _repo_pr_key(record)
        if key is None:
            continue
        by_pr.setdefault(key, {"completions": [], "events": []})["completions"].append(record)
    for event in events:
        key = _repo_pr_key(event)
        if key is None:
            continue
        by_pr.setdefault(key, {"completions": [], "events": []})["events"].append(event)

    rows: list[dict[str, Any]] = []
    for (repo, pr), bucket in sorted(by_pr.items()):
        ordered = _sorted_completions(bucket["completions"])
        for record in ordered:
            reason = _completion_reason(record)
            if reason != "rate_limited":
                continue
            when = _completion_time(record)
            if when is None:
                continue
            provider = str(record.get("provider") or record.get("agent") or "").strip().lower()
            switch = _find_switch_event(bucket["events"], after=when, from_agent=provider)
            if switch is None:
                rows.append(
                    {
                        "repo": repo,
                        "pr": pr,
                        "provider": provider,
                        "reason": reason,
                        "completed_at": when.isoformat().replace("+00:00", "Z"),
                        "switch_agent": None,
                        "switch_at": None,
                        "additional_rounds": None,
                        "same_evaluate": False,
                        "status": "switch_not_observed",
                    }
                )
                continue
            switch_at = _event_time(switch)
            assert switch_at is not None
            switch_agent = concrete_agent(_label_name(switch.get("label") or switch.get("name")))
            rounds = additional_rounds_until_switch(
                ordered, rate_limited_at=when, switch_at=switch_at
            )
            interesting = {
                f"agent:{switch_agent}",
                "agent:rate-limited",
                f"agents:tried-{provider}",
                f"agent:{provider}",
            }
            timeline: list[dict[str, str]] = []
            for item in bucket["events"]:
                item_at = _event_time(item)
                if item_at is None or item_at < when or item_at > switch_at:
                    continue
                label = _label_name(item.get("label") or item.get("name"))
                if label not in interesting and concrete_agent(label) is None:
                    continue
                if label in CONTROL_LABELS and label != "agent:rate-limited":
                    continue
                timeline.append(
                    {
                        "event": str(item.get("event") or item.get("action") or ""),
                        "label": label,
                        "created_at": item_at.isoformat().replace("+00:00", "Z"),
                    }
                )
            timeline.sort(key=lambda entry: (entry["created_at"], entry["label"]))
            rows.append(
                {
                    "repo": repo,
                    "pr": pr,
                    "provider": provider,
                    "reason": reason,
                    "completed_at": when.isoformat().replace("+00:00", "Z"),
                    "switch_agent": switch_agent,
                    "switch_at": switch_at.isoformat().replace("+00:00", "Z"),
                    "additional_rounds": rounds,
                    "same_evaluate": rounds == 0,
                    "status": "paired",
                    "label_timeline": timeline,
                }
            )
    return rows


def stale_rate_limited_on_progressed(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Open PRs whose latest completion progressed but still carry agent:rate-limited."""
    open_prs = list(snapshot.get("open_prs") or [])
    completions = _sorted_completions(list(snapshot.get("completions") or []))
    latest_by_pr: dict[tuple[str, int], dict[str, Any]] = {}
    for record in completions:
        key = _repo_pr_key(record)
        if key is None:
            continue
        latest_by_pr[key] = record

    stale: list[dict[str, Any]] = []
    for pr in open_prs:
        key = _repo_pr_key(pr)
        if key is None:
            continue
        labels = {_label_name(item) for item in (pr.get("labels") or [])}
        if "agent:rate-limited" not in labels:
            continue
        latest = latest_by_pr.get(key)
        if latest is None:
            continue
        if _completion_reason(latest) != "progressed":
            continue
        stale.append(
            {
                "repo": key[0],
                "pr": key[1],
                "reason": "progressed",
                "completed_at": (
                    (_completion_time(latest) or datetime.min.replace(tzinfo=UTC))
                    .isoformat()
                    .replace("+00:00", "Z")
                ),
                "labels": sorted(labels),
            }
        )
    return stale


def calculate(snapshot: dict[str, Any]) -> dict[str, Any]:
    rows = pair_rate_limited_switches(snapshot)
    paired_rounds = [
        int(row["additional_rounds"])
        for row in rows
        if row.get("status") == "paired" and row.get("additional_rounds") is not None
    ]
    median_rounds = float(median(paired_rounds)) if paired_rounds else None
    stale = stale_rate_limited_on_progressed(snapshot)
    return {
        "schema": SCHEMA,
        "rows": rows,
        "metrics": {
            "rate_limited_events": len(rows),
            "paired_switches": len(paired_rounds),
            "same_evaluate_switches": sum(1 for row in rows if row.get("same_evaluate")),
            "median_additional_rounds": median_rounds,
            "target_median_additional_rounds": 0,
            "passes_same_evaluate_median": median_rounds == 0.0 if paired_rounds else False,
            "stale_rate_limited_on_progressed": len(stale),
        },
        "stale_rate_limited_on_progressed": stale,
        "collection": {
            "history_complete": bool(
                (snapshot.get("collection") or {}).get("history_complete", True)
            ),
            "limitations": list((snapshot.get("collection") or {}).get("limitations") or []),
        },
    }


def label_events_from_evaluate_actions(
    actions: list[dict[str, Any]],
    *,
    repo: str,
    pr: int,
    at: str,
) -> list[dict[str, Any]]:
    """Project keepalive evaluate mutation logs into PR label timeline events.

    ``actions`` matches the shape recorded by the keepalive-loop test github stub
    (``type: label|remove-label``, ``labels`` / ``name``). Same-second events keep
    list order so the cadence join can treat them as one evaluate.
    """
    events: list[dict[str, Any]] = []
    for action in actions:
        kind = str(action.get("type") or action.get("event") or "").lower()
        if kind in {"label", "labeled"}:
            names = action.get("labels") or action.get("label") or action.get("name")
            if isinstance(names, str):
                names = [names]
            for name in names or []:
                label = _label_name(name)
                if not label:
                    continue
                events.append(
                    {
                        "repo": repo,
                        "pr": pr,
                        "event": "labeled",
                        "label": label,
                        "created_at": at,
                    }
                )
        elif kind in {"remove-label", "unlabeled", "unlabel"}:
            label = _label_name(action.get("name") or action.get("label"))
            if not label:
                continue
            events.append(
                {
                    "repo": repo,
                    "pr": pr,
                    "event": "unlabeled",
                    "label": label,
                    "created_at": at,
                }
            )
    return events


def snapshot_from_rate_limit_evaluate(
    *,
    repo: str,
    pr: int,
    provider: str,
    completed_at: str,
    switch_at: str,
    actions: list[dict[str, Any]],
    open_labels: list[str] | None = None,
) -> dict[str, Any]:
    """Build a portable snapshot for one rate-limited completion + same-evaluate switch."""
    return {
        "collection": {
            "history_complete": True,
            "limitations": ["evaluate-actions replay after #3997 merge"],
        },
        "completions": [
            {
                "repo": repo,
                "pr": pr,
                "provider": provider,
                "completed_at": completed_at,
                "completion": {"reason": "rate_limited"},
            }
        ],
        "label_events": label_events_from_evaluate_actions(actions, repo=repo, pr=pr, at=switch_at),
        "open_prs": [
            {
                "repo": repo,
                "pr": pr,
                "labels": list(open_labels or ["agent:auto", "agents:keepalive"]),
            }
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# Agent switch cadence (rate-limited completions)",
        "",
        f"Rate-limited events: **{metrics['rate_limited_events']}**",
        f"Paired switches: **{metrics['paired_switches']}**",
        f"Same-evaluate switches: **{metrics['same_evaluate_switches']}**",
        "Median additional rounds to switch: **{}** (target = 0)".format(
            metrics["median_additional_rounds"]
            if metrics["median_additional_rounds"] is not None
            else "n/a"
        ),
        f"Stale `agent:rate-limited` on progressed open PRs: **{metrics['stale_rate_limited_on_progressed']}**",
        "",
        "| Repo | PR | Provider | Reason | Completed | Switch | Additional rounds | Same evaluate |",
        "| --- | ---: | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in report["rows"]:
        lines.append(
            "| {repo} | {pr} | {provider} | {reason} | {completed} | {switch} | {rounds} | {same} |".format(
                repo=row["repo"],
                pr=row["pr"],
                provider=row.get("provider") or "",
                reason=row.get("reason") or "",
                completed=row.get("completed_at") or "",
                switch=row.get("switch_agent") or "—",
                rounds=(
                    row["additional_rounds"] if row.get("additional_rounds") is not None else "—"
                ),
                same="yes" if row.get("same_evaluate") else "no",
            )
        )
    if not report["rows"]:
        lines.append("| — | — | — | — | — | — | — | — |")
    timelines = [row for row in report["rows"] if row.get("label_timeline")]
    if timelines:
        lines.extend(["", "## Label timelines", ""])
        for row in timelines:
            lines.append(
                "### {repo}#{pr} ({provider} → {switch})".format(
                    repo=row["repo"],
                    pr=row["pr"],
                    provider=row.get("provider") or "?",
                    switch=row.get("switch_agent") or "—",
                )
            )
            lines.append("")
            for entry in row["label_timeline"]:
                lines.append(
                    "- `{created_at}` {event} `{label}`".format(
                        created_at=entry.get("created_at") or "",
                        event=entry.get("event") or "",
                        label=entry.get("label") or "",
                    )
                )
            lines.append("")
    lines.extend(["", f"Schema: `{report['schema']}`", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args(argv)
    report = calculate(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = markdown(report)
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.write_text(rendered, encoding="utf-8")
    print(rendered)
    metrics = report["metrics"]
    if metrics["paired_switches"] and not metrics["passes_same_evaluate_median"]:
        return 1
    if metrics["stale_rate_limited_on_progressed"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
