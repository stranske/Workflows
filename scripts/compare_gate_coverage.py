#!/usr/bin/env python3
"""Map ranked Gate inventories across source revisions without inferring attribution.

Coverage files may be plain JSON or gzip. Source revisions identify the mapping
inputs; they do not prove which checkout produced a supplied coverage file.
Runner, dependency, selection and policy receipts are still needed for attribution.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

from scripts.reconcile_issue_4426_coverage import EVIDENCE, MAX_BYTES, TARGETS, _validate_inventory


def _units(row: dict) -> tuple[set[int], set[tuple[int, int]], set[int], set[tuple[int, int]]]:
    for prefix in ("missing", "executed"):
        _validate_inventory(row[f"{prefix}_lines"], row[f"{prefix}_branches"], prefix)
    missing_lines = set(row["missing_lines"])
    missing_arcs = set(map(tuple, row["missing_branches"]))
    lines = set(row["executed_lines"])
    arcs = set(map(tuple, row["executed_branches"]))
    if missing_lines & lines or missing_arcs & arcs:
        raise ValueError("executed and missing inventories overlap")
    summary = row["summary"]
    for field, expected in (
        ("num_statements", len(missing_lines | lines)),
        ("covered_lines", len(lines)),
        ("missing_lines", len(missing_lines)),
        ("num_branches", len(missing_arcs | arcs)),
        ("covered_branches", len(arcs)),
        ("missing_branches", len(missing_arcs)),
    ):
        if type(summary[field]) is not int or summary[field] != expected:
            raise ValueError(f"coverage inventory disagrees with summary: {field}")
    return missing_lines | lines, missing_arcs | arcs, missing_lines, missing_arcs


def compare_target(before: dict, after: dict, before_source: str, after_source: str) -> dict:
    """Match exact source lines and arcs with both endpoints in matching blocks.

    Negative destinations encode a function exit at the corresponding definition
    line. Removed/excluded units and changed endpoints never count as covered.
    Text correspondence alone does not establish behavioral equivalence.
    """
    before_lines, before_arcs, before_missing, before_missing_arcs = _units(before)
    after_lines, after_arcs, after_missing, after_missing_arcs = _units(after)
    old_text, new_text = before_source.splitlines(), after_source.splitlines()
    for lines, arcs, text in (
        (before_lines, before_arcs, old_text),
        (after_lines, after_arcs, new_text),
    ):
        positions = lines | {abs(endpoint) for arc in arcs for endpoint in arc}
        if any(position > len(text) for position in positions):
            raise ValueError("coverage position exceeds source length")
    mapping = {}
    for block in SequenceMatcher(None, old_text, new_text, autojunk=False).get_matching_blocks():
        mapping.update({block.a + offset + 1: block.b + offset + 1 for offset in range(block.size)})

    line_pairs = [
        (line, mapping[line]) for line in sorted(before_lines) if mapping.get(line) in after_lines
    ]
    arc_pairs = []
    for arc in sorted(before_arcs):
        if all(abs(endpoint) in mapping for endpoint in arc):
            mapped = tuple(mapping[abs(endpoint)] * (1 if endpoint > 0 else -1) for endpoint in arc)
            if mapped in after_arcs:
                arc_pairs.append((arc, mapped))

    def accounting(pairs, old_units, new_units, old_missing, new_missing):
        return {
            "mapped": [[old, new] for old, new in pairs],
            "newly_covered": [
                [old, new] for old, new in pairs if old in old_missing and new not in new_missing
            ],
            "newly_missing": [
                [old, new] for old, new in pairs if old not in old_missing and new in new_missing
            ],
            "unmatched_baseline": sorted(old_units - {old for old, _ in pairs}),
            "unmatched_final": sorted(new_units - {new for _, new in pairs}),
            "unmatched_baseline_missing": sorted(old_missing - {old for old, _ in pairs}),
            "unmatched_final_missing": sorted(new_missing - {new for _, new in pairs}),
        }

    lines = accounting(line_pairs, before_lines, after_lines, before_missing, after_missing)
    arcs = accounting(arc_pairs, before_arcs, after_arcs, before_missing_arcs, after_missing_arcs)
    counts = {
        "baseline_missing_units": len(before_missing) + len(before_missing_arcs),
        "final_missing_units": len(after_missing) + len(after_missing_arcs),
        **{
            key: len(lines[key]) + len(arcs[key])
            for key in (
                "newly_covered",
                "newly_missing",
                "unmatched_baseline_missing",
                "unmatched_final_missing",
            )
        },
    }
    # Unmatched missing units explain denominator changes; they are never gains.
    counts["mapped_net_reduction"] = counts["newly_covered"] - counts["newly_missing"]
    counts["unmatched_net_difference"] = (
        counts["unmatched_baseline_missing"] - counts["unmatched_final_missing"]
    )
    counts["snapshot_difference"] = counts["baseline_missing_units"] - counts["final_missing_units"]
    return {
        "source_sha256": {
            "baseline": hashlib.sha256(before_source.encode()).hexdigest(),
            "final": hashlib.sha256(after_source.encode()).hexdigest(),
        },
        "changed_baseline_lines": sorted(set(range(1, len(old_text) + 1)) - mapping.keys()),
        "changed_final_lines": sorted(set(range(1, len(new_text) + 1)) - set(mapping.values())),
        "lines": lines,
        "arcs": arcs,
        "missing_unit_accounting": counts,
        "observed_newly_covered_units": len(lines["newly_covered"]) + len(arcs["newly_covered"]),
        "observed_newly_missing_units": len(lines["newly_missing"]) + len(arcs["newly_missing"]),
        "attributable_round_reduction": None,
    }


def compare_checkouts(
    repository: Path, baseline: str, final: str, before_path: Path, after_path: Path, ranking: Path
) -> dict:
    """Build a six-target mapping; missing sources/inventories fail the comparison."""
    paths = json.loads(ranking.read_text())["historical_issue_order"]
    if len(paths) != len(TARGETS) or set(paths) != set(TARGETS):
        raise ValueError("ranking must contain exactly the six selected targets")

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repository), *args], check=True, capture_output=True
        ).stdout.decode()

    revisions = {
        "baseline": git(
            "rev-parse", "--verify", "--end-of-options", baseline + "^{commit}"
        ).strip(),
        "final": git("rev-parse", "--verify", "--end-of-options", final + "^{commit}").strip(),
    }
    inventories, digests = [], {}
    for label, path in (("baseline", before_path), ("final", after_path)):
        with path.open("rb") as stream:
            compressed = stream.read(2) == b"\x1f\x8b"
            stream.seek(0)
            if compressed:
                with gzip.GzipFile(fileobj=stream) as expanded:
                    data = expanded.read(MAX_BYTES + 1)
            else:
                data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("coverage.json exceeds byte limit")
        inventory = json.loads(data)
        if inventory["meta"]["branch_coverage"] is not True:
            raise ValueError("branch coverage is required")
        inventories.append(inventory)
        digests[label] = hashlib.sha256(data).hexdigest()
    before, after = inventories
    targets = {
        path: compare_target(
            before["files"][path],
            after["files"][path],
            git("show", f"{revisions['baseline']}:{path}"),
            git("show", f"{revisions['final']}:{path}"),
        )
        for path in paths
    }
    return {
        "schema": "workflows.issue-4663-source-mapping/v1",
        "source_checkouts": revisions,
        "coverage_json_sha256": digests,
        "tested_checkout_binding_verified": False,
        "execution_configuration_verified": False,
        "attributable_round_reduction": None,
        "targets": targets,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_coverage", type=Path)
    parser.add_argument("final_coverage", type=Path)
    parser.add_argument("--baseline-checkout", required=True)
    parser.add_argument("--final-checkout", required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--ranking", type=Path, default=EVIDENCE / "ranking.json")
    args = parser.parse_args(argv)
    try:
        result = compare_checkouts(
            args.repository,
            args.baseline_checkout,
            args.final_checkout,
            args.baseline_coverage,
            args.final_coverage,
            args.ranking,
        )
    except (
        OSError,
        EOFError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.CalledProcessError,
    ) as exc:
        parser.exit(1, f"Cannot compare Gate inventories: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
