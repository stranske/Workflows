"""Print uncovered statements + branches for the issue 4433 integration targets."""

import json
import sys
from pathlib import Path

TARGETS = [
    "scripts/aggregate_agent_metrics.py",
    "scripts/check_consumer_sync_drift.py",
    "tools/llm_provider.py",
]


def summarize_coverage(coverage_path: str | Path) -> int:
    """Print total and per-target missing lines/branches and return missing_total."""
    data = json.loads(Path(coverage_path).read_text(encoding="utf-8"))
    totals = data["totals"]
    units = totals["num_statements"] + totals["num_branches"]
    covered = totals["covered_lines"] + totals["covered_branches"]
    pct = (100 * covered / units) if units else 0.0
    print("TOTAL", covered, units, pct)
    missing_total = 0
    for target in TARGETS:
        record = data["files"][target]
        summary = record["summary"]
        missing = summary["missing_lines"] + summary["missing_branches"]
        missing_total += missing
        print(
            target,
            summary["missing_lines"],
            "+",
            summary["missing_branches"],
            "=",
            missing,
            record["missing_lines"],
            record.get("missing_branches"),
        )
    print("TARGET_MISSING", missing_total)
    return missing_total


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for target_missing.py."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        raise SystemExit("Usage: target_missing.py <coverage.json>")
    summarize_coverage(args[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
