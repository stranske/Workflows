#!/usr/bin/env python3
"""Extract statements+branches gap units for scripts/aggregate_agent_metrics.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TARGET = "scripts/aggregate_agent_metrics.py"


def units(summary: dict) -> dict:
    missing = int(summary.get("missing_lines", 0))
    partial = int(summary.get("num_partial_branches", 0))
    return {
        "missing_statements": missing,
        "partial_branches": partial,
        "gap_units": missing + partial,
        "percent_covered": summary.get("percent_covered_display"),
        "num_statements": summary.get("num_statements"),
        "num_branches": summary.get("num_branches"),
        "missing_branches": summary.get("missing_branches"),
    }


def main() -> int:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    file_data = data["files"].get(TARGET)
    if not file_data:
        print(f"missing target in {path}", file=sys.stderr)
        return 1
    report = units(file_data["summary"])
    print(json.dumps({"target": TARGET, "coverage_json": str(path), **report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
