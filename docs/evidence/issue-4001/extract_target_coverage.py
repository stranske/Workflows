#!/usr/bin/env python3
"""Extract Gate-style per-target missing line/branch counts from coverage.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TARGETS = (
    "scripts/aggregate_agent_metrics.py",
    "scripts/check_consumer_sync_drift.py",
    "scripts/validate_run_contract.py",
)


def load_file_stats(coverage_path: Path) -> dict[str, dict[str, int | float]]:
    payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    files = payload.get("files") or {}
    out: dict[str, dict[str, int | float]] = {}
    for target in TARGETS:
        match = None
        for key, entry in files.items():
            normalized = key.replace("\\", "/")
            if normalized.endswith(target):
                match = entry
                break
        if match is None:
            out[target] = {
                "missing_lines": -1,
                "missing_branches": -1,
                "percent_covered": -1.0,
            }
            continue
        summary = match.get("summary") or {}
        out[target] = {
            "missing_lines": int(summary.get("missing_lines", 0)),
            "missing_branches": int(summary.get("missing_branches", 0)),
            "percent_covered": float(summary.get("percent_covered", 0.0)),
        }
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} coverage.json", file=sys.stderr)
        return 2
    stats = load_file_stats(Path(sys.argv[1]))
    print(json.dumps(stats, indent=2, sort_keys=True))
    total_missing = sum(
        stats[t]["missing_lines"] + stats[t]["missing_branches"]
        for t in TARGETS
        if stats[t]["missing_lines"] >= 0
    )
    print(f"combined_missing_units={total_missing}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
