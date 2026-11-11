#!/usr/bin/env python3
"""Extract Gate-style per-target missing line/branch counts from coverage.json."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import sys
from pathlib import Path

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

TARGETS = (
    "scripts/aggregate_agent_metrics.py",
    "scripts/check_consumer_sync_drift.py",
    "scripts/validate_run_contract.py",
)


def read_report(path: Path) -> bytes:
    """Read a complete retained report, optionally compressed with gzip."""
    if path.suffix == ".gz":
        return gzip.decompress(path.read_bytes())
    return path.read_bytes()


def load_file_stats(coverage_path: Path) -> dict[str, dict[str, int | float]]:
    payload = json.loads(read_report(coverage_path))
    if not isinstance(payload, dict):
        raise ValueError("coverage report must be an object")
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


def check_xml_counts(xml_path: Path, stats: dict[str, dict[str, int | float]]) -> None:
    """Independently count missing statements and branch exits in coverage XML."""
    root = ET.fromstring(read_report(xml_path))
    for target in TARGETS:
        matches = []
        for entry in root.iter("class"):
            name = entry.get("filename", "").replace("\\", "/")
            if name in (target, Path(target).name) or name.endswith("/" + target):
                matches.append(entry)
        if len(matches) != 1:
            raise ValueError(f"{target}: expected exactly one XML target, found {len(matches)}")
        lines = list(matches[0].iter("line"))
        if not lines:
            raise ValueError(f"{target}: XML target has no statements")
        missing_lines = 0
        missing_branches = 0
        for line in lines:
            hits = line.get("hits", "")
            if not hits.isdecimal():
                raise ValueError(f"{target}: invalid XML hits {hits!r}")
            missing_lines += int(hits) == 0
            if line.get("branch") == "true":
                condition = line.get("condition-coverage", "")
                match = re.fullmatch(r"\d+(?:\.\d+)?% \((\d+)/(\d+)\)", condition)
                if match is None:
                    raise ValueError(f"{target}: invalid XML condition-coverage {condition!r}")
                covered, total = map(int, match.groups())
                if not 0 <= covered <= total or total == 0:
                    raise ValueError(f"{target}: invalid XML branch counts {condition!r}")
                missing_branches += total - covered
        actual = (missing_lines, missing_branches)
        expected = (stats[target]["missing_lines"], stats[target]["missing_branches"])
        if actual != expected:
            raise ValueError(f"{target}: XML missing counts {actual} differ from JSON {expected}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage_json", type=Path, help="coverage.json[.gz]")
    parser.add_argument("--xml", type=Path, help="cross-check coverage.xml[.gz] missing counts")
    parser.add_argument(
        "--max-missing", type=int, help="maximum accepted combined missing statements and branches"
    )
    args = parser.parse_args()
    if args.max_missing is not None and args.max_missing < 0:
        parser.error("--max-missing must be a nonnegative integer")
    try:
        stats = load_file_stats(args.coverage_json)
        if args.xml is not None:
            check_xml_counts(args.xml, stats)
    except (OSError, EOFError, ValueError, ET.ParseError, DefusedXmlException) as exc:
        print(f"invalid coverage: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(stats, indent=2, sort_keys=True))
    total_missing = sum(stats[t]["missing_lines"] + stats[t]["missing_branches"] for t in TARGETS)
    print(f"combined_missing_units={total_missing}", file=sys.stderr)
    if args.max_missing is not None and total_missing > args.max_missing:
        print(f"coverage budget exceeded: {total_missing} > {args.max_missing}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
