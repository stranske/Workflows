#!/usr/bin/env python3
"""Count missing statements and partial branches for #4013 targets in coverage.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TARGETS = (
    "scripts/langchain/verifier_config.py",
    "scripts/reusable_ci_scope.py",
    "tools/post_ci_summary.py",
)


def gap_units(file_entry: dict) -> tuple[int, int, int]:
    missing_lines = file_entry.get("missing_lines") or []
    missing_branches = file_entry.get("missing_branches") or []
    excluded_lines = file_entry.get("excluded_lines") or []
    stmts = len(missing_lines) + len(excluded_lines)
    branches = len(missing_branches)
    return stmts, branches, stmts + branches


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "coverage.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files") or {}
    total = {"statements": 0, "branches": 0, "combined": 0}
    print(f"source={path.resolve()}")
    for target in TARGETS:
        entry = files.get(target)
        if not entry:
            print(f"{target}: MISSING FROM REPORT")
            continue
        stmts, branches, combined = gap_units(entry)
        total["statements"] += stmts
        total["branches"] += branches
        total["combined"] += combined
        print(
            f"{target}: missing_statements={stmts} missing_branches={branches} combined={combined}"
        )
    print(
        "TOTAL: "
        f"missing_statements={total['statements']} "
        f"missing_branches={total['branches']} "
        f"combined={total['combined']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
