#!/usr/bin/env python3
"""Extract Gate-style per-target missing line/branch counts from coverage.json."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

TARGETS = (
    "scripts/aggregate_agent_metrics.py",
    "scripts/check_consumer_sync_drift.py",
    "scripts/validate_run_contract.py",
)


def load_file_stats(coverage_path: Path) -> dict[str, dict[str, int | float]]:
    payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("coverage files must be an object")
    out: dict[str, dict[str, int | float]] = {}
    for target in TARGETS:
        matches = []
        for key, entry in files.items():
            normalized = key.replace("\\", "/")
            if normalized == target or normalized.endswith("/" + target):
                matches.append(entry)
        if len(matches) != 1:
            raise ValueError(f"{target}: expected exactly one target, found {len(matches)}")
        match = matches[0]
        summary = match.get("summary") if isinstance(match, dict) else None
        if not isinstance(summary, dict):
            raise ValueError(f"{target}: missing summary")
        for count in ("missing_lines", "missing_branches"):
            value = summary.get(count)
            if type(value) is not int or value < 0:
                raise ValueError(f"{target}: {count} must be a nonnegative integer")
        percent = summary.get("percent_covered")
        if (
            type(percent) not in (int, float)
            or not math.isfinite(percent)
            or not 0 <= percent <= 100
        ):
            raise ValueError(f"{target}: percent_covered must be between 0 and 100")
        out[target] = {
            "missing_lines": summary["missing_lines"],
            "missing_branches": summary["missing_branches"],
            "percent_covered": float(percent),
        }
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} coverage.json", file=sys.stderr)
        return 2
    try:
        stats = load_file_stats(Path(sys.argv[1]))
    except (OSError, ValueError) as exc:
        print(f"invalid coverage: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(stats, indent=2, sort_keys=True))
    total_missing = sum(stats[t]["missing_lines"] + stats[t]["missing_branches"] for t in TARGETS)
    print(f"combined_missing_units={total_missing}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
