#!/usr/bin/env python3
"""Render advanced debouncing options in Markdown or JSON."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DebounceOption:
    """Structured evaluation data for a debouncing approach."""

    key: str
    title: str
    solves: str
    requirements: tuple[str, ...]
    risks: tuple[str, ...]
    next_steps: tuple[str, ...]


OPTIONS: tuple[DebounceOption, ...] = (
    DebounceOption(
        key="external-debouncer-service",
        title="External Debouncer Service",
        solves=(
            "Cancels duplicate dispatches across repos or workflow types before "
            "GitHub Actions starts a run."
        ),
        requirements=(
            "Dedicated service/runtime with authenticated ingress.",
            "Signed event ingestion and idempotent queueing.",
            "Audit log storage for replay and debugging.",
            "Per-repo policy configuration with safe defaults.",
            "Fallback path when the service is unavailable.",
        ),
        risks=(
            "Introduces a new critical dependency in the automation chain.",
            "Operational overhead (hosting, scaling, on-call support).",
        ),
        next_steps=(
            "Draft an RFC covering ownership, on-call support, and MVP scope.",
            "Scope MVP to a single repo and single workflow family.",
        ),
    ),
    DebounceOption(
        key="github-app-filtering",
        title="GitHub App Filtering",
        solves=(
            "Uses a GitHub App to gate high-frequency events and dispatch workflows "
            "only for the latest state."
        ),
        requirements=(
            "GitHub App with actions:write and pull_request scopes.",
            "Webhook receiver to enforce event ordering.",
            "Logic to collapse duplicate events.",
            "Persistent store for run locks/state.",
        ),
        risks=(
            "App rate limits and deployment complexity.",
            "Requires webhook hosting and storage lifecycle management.",
        ),
        next_steps=(
            "Prototype an event filter for one workflow type.",
            "Measure dispatch reductions before expanding.",
        ),
    ),
)


def render_markdown(options: Iterable[DebounceOption]) -> str:
    """Render a Markdown report describing debouncing options."""
    lines = ["# Advanced Debouncing Options", ""]
    for option in options:
        lines.extend(
            [
                f"## {option.title}",
                "",
                f"**What it solves:** {option.solves}",
                "",
                "**Requirements:**",
            ]
        )
        lines.extend([f"- {item}" for item in option.requirements])
        lines.extend(["", "**Risks:**"])
        lines.extend([f"- {item}" for item in option.risks])
        lines.extend(["", "**Next steps:**"])
        lines.extend([f"- {item}" for item in option.next_steps])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(options: Iterable[DebounceOption]) -> str:
    """Render a JSON report describing debouncing options."""
    payload = [
        {
            "key": option.key,
            "title": option.title,
            "solves": option.solves,
            "requirements": list(option.requirements),
            "risks": list(option.risks),
            "next_steps": list(option.next_steps),
        }
        for option in options
    ]
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="-",
        help="Output path or '-' for stdout.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    if args.format == "json":
        payload = render_json(OPTIONS)
    else:
        payload = render_markdown(OPTIONS)

    if args.output == "-":
        print(payload, end="")
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
