"""Print uncovered statements + branches for the issue 4433 integration targets."""

import json
import sys
from pathlib import Path

TARGETS = [
    "scripts/aggregate_agent_metrics.py",
    "scripts/check_consumer_sync_drift.py",
    "tools/llm_provider.py",
]

data = json.loads(Path(sys.argv[1]).read_text())
totals = data["totals"]
units = totals["num_statements"] + totals["num_branches"]
covered = totals["covered_lines"] + totals["covered_branches"]
print("TOTAL", covered, units, 100 * covered / units)
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
