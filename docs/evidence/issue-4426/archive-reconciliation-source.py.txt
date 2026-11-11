#!/usr/bin/env python3
"""Reconcile the #4481 Gate archive offline without overwriting historical evidence.

The pinned log/metadata record binds the archive digest to the PR head and actual
merge checkout. A report from this tool establishes final artifact counters and
missing-unit inventories only; comparable original-round execution is still owed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parents[1] / "docs/evidence/issue-4426"
REPORT_INPUTS_SHA256 = "edef0047a34517cdbd3543e0bc308e180865305bcc5f618ba3ea1619dc5e4a3c"
# Job 128131232558's TOTAL row is retained in final-head-gate.json, separately
# from the bounded target excerpts pinned above. Never infer its branch count.
FINAL_TOTAL_LINE = "TOTAL 49564 3657 19862 1833 91.21%"
COVERAGE_MEMBER = "runtimes/3.14/coverage.json"
MAX_BYTES = 16_000_000
TARGETS = (
    "scripts/sync_test_dependencies.py",
    "scripts/langchain/issue_pr_context.py",
    "scripts/langchain/verifier_config.py",
    "tools/langchain_client.py",
    "scripts/langchain/task_validator.py",
    "scripts/langchain/pr_verifier.py",
)


def read_coverage_archive(path: Path, digest: str) -> tuple[dict, str]:
    """Read the recorded Gate runtime's coverage.json from a verified local ZIP."""
    with path.open("rb") as stream:
        archive_bytes = stream.read(MAX_BYTES + 1)
    if len(archive_bytes) > MAX_BYTES:
        raise ValueError("archive exceeds byte limit")
    if "sha256:" + hashlib.sha256(archive_bytes).hexdigest() != digest:
        raise ValueError("archive digest mismatch")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        members = [member for member in archive.infolist() if member.filename == COVERAGE_MEMBER]
        if len(members) != 1:
            raise ValueError(f"archive must contain exactly one {COVERAGE_MEMBER}")
        if members[0].file_size > MAX_BYTES:
            raise ValueError("coverage.json exceeds byte limit")
        with archive.open(members[0]) as stream:
            data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("coverage.json exceeds byte limit")
    coverage = json.loads(data)
    if coverage["meta"]["branch_coverage"] is not True:
        raise ValueError("branch coverage is required")
    return coverage, hashlib.sha256(data).hexdigest()


def _match_report(summary: dict, lines: list[str], name: str) -> None:
    """Check JSON counters against the pinned precision-two Gate term report."""
    pattern = re.compile(
        r"(?:^|\s)" + re.escape(name) + r"\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+\.\d+)%"
    )
    matches = [match for line in lines if (match := pattern.search(line)) is not None]
    if len(matches) != 1:
        raise ValueError(f"expected one pinned term report for {name}")
    values = matches[0].groups()
    keys = ("num_statements", "missing_lines", "num_branches", "num_partial_branches")
    if any(summary[key] != int(value) for key, value in zip(keys, values[:4], strict=True)):
        raise ValueError(f"coverage counters disagree with Gate log: {name}")
    if summary["percent_covered_display"] != values[4]:
        raise ValueError(f"coverage percentage disagrees with Gate log: {name}")


def reconcile_archive(archive: Path, evidence: Path = EVIDENCE) -> dict:
    """Return final counters and exact gaps while retaining unknown attribution."""
    with (evidence / "gate-report-inputs.json").open("rb") as stream:
        inputs_bytes = stream.read(30_001)
    if hashlib.sha256(inputs_bytes).hexdigest() != REPORT_INPUTS_SHA256:
        raise ValueError("pinned Gate metadata digest mismatch")
    final = json.loads(inputs_bytes)["final_head"]
    coverage, coverage_digest = read_coverage_archive(archive, final["artifact"]["digest"])
    lines = final["runtime"]["lines"]
    _match_report(coverage["totals"], [FINAL_TOTAL_LINE], "TOTAL")
    targets = {}
    for path in TARGETS:
        row = coverage["files"][path]
        summary = row["summary"]
        _match_report(summary, lines, path)
        missing_lines, missing_branches = row["missing_lines"], row["missing_branches"]
        if (
            len(missing_lines) != summary["missing_lines"]
            or len(missing_branches) != summary["missing_branches"]
        ):
            raise ValueError(f"missing-unit inventory disagrees with summary: {path}")
        targets[path] = {
            "summary": summary,
            "missing_lines": missing_lines,
            "missing_branches": missing_branches,
            "missing_units": len(missing_lines) + len(missing_branches),
        }
    return {
        "schema": "workflows.issue-4426-archive-reconciliation/v1",
        "run_id": final["run"]["id"],
        "artifact_id": final["artifact"]["id"],
        "archive_digest": final["artifact"]["digest"],
        "head_sha": final["run"]["head_sha"],
        "tested_checkout": final["checkout"],
        "python": final["runtime"]["python"],
        "job_id": final["runtime"]["job_id"],
        "report_inputs_sha256": REPORT_INPUTS_SHA256,
        "coverage_json_sha256": coverage_digest,
        "coverage_json_member": COVERAGE_MEMBER,
        "coverage_meta": coverage["meta"],
        "totals": coverage["totals"],
        "targets": targets,
        "target_missing_units": sum(row["missing_units"] for row in targets.values()),
        "attributable_round_reduction": None,
        "original_round_comparable_baseline": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="local artifact 13537639987 ZIP")
    args = parser.parse_args(argv)
    try:
        result = reconcile_archive(args.archive)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print(f"Cannot reconcile final Gate artifact: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
