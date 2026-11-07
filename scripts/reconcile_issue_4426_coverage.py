#!/usr/bin/env python3
"""Reconcile the #4481 Gate archive offline without overwriting historical evidence.

The pinned log/metadata record binds the archive digest to the PR head and actual
merge checkout. A report from this tool establishes final artifact counters and
missing-unit inventories only; comparable original-round execution is still owed.
Use --reports-only to recover bounded log counters when archive bytes are unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shlex
import sys
import tomllib
import zipfile
from pathlib import Path

from coverage.results import Numbers

EVIDENCE = Path(__file__).resolve().parents[1] / "docs/evidence/issue-4426"
REPORT_INPUTS_SHA256 = "edef0047a34517cdbd3543e0bc308e180865305bcc5f618ba3ea1619dc5e4a3c"
EXECUTION_INPUTS_SHA256 = "67cb772aca252bac4e27b186b8c3b59d0f9b193ea3787f15524222656c380599"
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


def _validate_summary(summary: dict, name: str) -> None:
    """Require coverage.py's counters and blended percentage to agree."""
    statements, missed, branches, missing_branches, partial = (
        summary[key]
        for key in (
            "num_statements",
            "missing_lines",
            "num_branches",
            "missing_branches",
            "num_partial_branches",
        )
    )
    if (
        any(
            type(value) is not int
            for value in (statements, missed, branches, missing_branches, partial)
        )
        or not 0 <= missed <= statements
        or not 0 <= partial <= missing_branches <= branches
    ):
        raise ValueError(f"invalid coverage counters: {name}")
    for field, expected in (
        ("covered_lines", statements - missed),
        ("covered_branches", branches - missing_branches),
    ):
        if type(summary[field]) is not int or summary[field] != expected:
            raise ValueError(f"inconsistent covered counters: {name}")
    display = Numbers(
        precision=2,
        n_statements=statements,
        n_missing=missed,
        n_branches=branches,
        n_missing_branches=missing_branches,
    ).pc_covered_str
    if display != summary["percent_covered_display"]:
        raise ValueError(f"branch counters disagree with coverage percentage: {name}")


def _validate_inventory(missing_lines: list, missing_branches: list, name: str) -> None:
    """Reject repeated or malformed units that could inflate artifact accounting."""
    if (
        not isinstance(missing_lines, list)
        or any(type(line) is not int or line <= 0 for line in missing_lines)
        or len(set(missing_lines)) != len(missing_lines)
    ):
        raise ValueError(f"invalid missing-line inventory: {name}")
    if (
        not isinstance(missing_branches, list)
        or any(
            not isinstance(arc, list)
            or len(arc) != 2
            or any(type(line) is not int for line in arc)
            or arc[0] <= 0
            or arc[1] == 0
            for arc in missing_branches
        )
        or len({tuple(arc) for arc in missing_branches}) != len(missing_branches)
    ):
        raise ValueError(f"invalid missing-branch inventory: {name}")


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
    _validate_summary(summary, name)


def _read_inputs(evidence: Path) -> dict:
    """Pin run/head/checkout identities and log bytes for either reconciliation mode."""
    with (evidence / "gate-report-inputs.json").open("rb") as stream:
        inputs_bytes = stream.read(30_001)
    if hashlib.sha256(inputs_bytes).hexdigest() != REPORT_INPUTS_SHA256:
        raise ValueError("pinned Gate metadata digest mismatch")
    return json.loads(inputs_bytes)


def _recover_report_targets(lines: list[str]) -> dict:
    """Recover missing branch counts only when one integer fits the rounded display.

    BrPart counts partial branches, not all missing outcomes. A rounded display
    can admit multiple missing counts; such a report must not supply a baseline.
    No branch positions can be recovered from the counters.
    """
    if len(lines) > 16 or any(len(line) > 5000 for line in lines):
        raise ValueError("report excerpts exceed the bound")
    targets = {}
    for path in TARGETS:
        pattern = re.compile(
            r"(?:^|\s)" + re.escape(path) + r"\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+\.\d+)%"
        )
        matches = [match for line in lines if (match := pattern.search(line)) is not None]
        if len(matches) != 1:
            raise ValueError(f"expected one pinned term report for {path}")
        statements, missed, branches, partial = map(int, matches[0].groups()[:4])
        if not 0 <= missed <= statements <= 100_000 or not 0 <= partial <= branches <= 100_000:
            raise ValueError(f"invalid or unbounded coverage counters: {path}")
        display = matches[0].group(5)
        candidates = [
            missing
            for missing in range(partial, branches + 1)
            if Numbers(
                precision=2,
                n_statements=statements,
                n_missing=missed,
                n_branches=branches,
                n_missing_branches=missing,
            ).pc_covered_str
            == display
        ]
        if len(candidates) != 1:
            raise ValueError(f"missing branch count is not unique: {path}")
        targets[path] = {
            "num_statements": statements,
            "missing_lines": missed,
            "num_branches": branches,
            "num_partial_branches": partial,
            "percent_covered_display": display,
            "missing_branches": candidates[0],
        }
    return targets


def _execution_settings(project: dict, runtime: dict) -> dict:
    """Read coverage/report policy and observed settings from immutable evidence."""
    tools = tomllib.loads(project["content"])["tool"]
    lines = runtime["log_excerpts"]

    def one(pattern: str) -> str:
        matches = [match[1] for line in lines if (match := re.search(pattern, line))]
        if len(matches) != 1:
            raise ValueError(f"expected one execution setting: {pattern}")
        return matches[0]

    return {
        "python": one(r"platform linux -- Python ([\d.]+),"),
        "pytest": one(r"platform linux -- Python [\d.]+, pytest-([\d.]+),"),
        "coverage_version": one(r" \+ coverage==([\d.]+)$"),
        "plugins": sorted(one(r" plugins: (.+)$").split(", ")),
        "marker": one(r" PYTEST_MARKERS: (.+)$"),
        "extra_args": shlex.split(one(r" PYTEST_ARGS: (.*)$")),
        "entrypoint": one(r'(pytest(?: -p ci_test_growth)?) "\$\{args\[@\]\}"'),
        "workers_observed": int(one(r" created: (\d+)/\d+ workers$")),
        "coverage": tools["coverage"],
        "pytest_ini": tools["pytest"]["ini_options"],
    }


def _configuration_differences(before: dict, after: dict, prefix: str = "") -> dict:
    """Retain concrete differences, including report exclusions and pytest selection."""
    differences = {}
    for key in sorted(before.keys() | after.keys()):
        name = f"{prefix}.{key}" if prefix else key
        old, new = before.get(key), after.get(key)
        if isinstance(old, dict) and isinstance(new, dict):
            differences.update(_configuration_differences(old, new, name))
        elif old != new:
            differences[name] = {"baseline": old, "final": new}
    return differences


def reconcile_execution_configurations(evidence: Path = EVIDENCE) -> dict:
    """Explain why historical Gate counts cannot serve as a comparable baseline.

    Even equal runner settings would not prove an attributable reduction: source
    and test changes still need controlled executions with accessible artifacts.
    """
    with (evidence / "gate-execution-inputs.json").open("rb") as stream:
        data = stream.read(60_001)
    if hashlib.sha256(data).hexdigest() != EXECUTION_INPUTS_SHA256:
        raise ValueError("pinned Gate execution digest mismatch")
    inputs = json.loads(data)
    identities = _read_inputs(evidence)
    for name in ("pre_round", "final_head"):
        if inputs[name]["checkout_sha"] != identities[name]["run"]["checkout_sha"]:
            raise ValueError("execution checkout identity mismatch")
    baseline, final = inputs["pre_round"], inputs["final_head"]
    final_settings = _execution_settings(final["pyproject"], final["runtime"])
    baselines = {}
    for version, runtime in baseline["runtimes"].items():
        settings = _execution_settings(baseline["pyproject"], runtime)
        differences = _configuration_differences(settings, final_settings)
        baselines[version] = {
            "settings": settings,
            "differences_from_final": differences,
            "settings_equal": not differences,
        }
    return {
        "schema": "workflows.issue-4426-execution-comparison/v1",
        "source": "gate-execution-inputs.json",
        "source_sha256": EXECUTION_INPUTS_SHA256,
        "baseline_checkout": baseline["checkout_sha"],
        "final_checkout": final["checkout_sha"],
        "final_settings": final_settings,
        "baselines_by_runtime": baselines,
        "comparable_execution_configuration": False,
        "source_and_test_equivalence_verified": False,
        "attributable_round_reduction": None,
    }


def reconcile_reports(evidence: Path = EVIDENCE) -> dict:
    """Reproduce historical per-target accounting without granting round-wide credit."""
    inputs = _read_inputs(evidence)
    final = inputs["final_head"]
    baselines = {
        version: _recover_report_targets(runtime["lines"])
        for version, runtime in inputs["pre_round"]["runtimes"].items()
    }
    final_targets = _recover_report_targets(final["runtime"]["lines"])
    targets = []
    for path in TARGETS:
        current = final_targets[path]
        original = {version: rows[path] for version, rows in baselines.items()}
        final_units = current["missing_lines"] + current["missing_branches"]
        original_units = {
            version: row["missing_lines"] + row["missing_branches"]
            for version, row in original.items()
        }
        targets.append(
            {
                "path": path,
                "baseline_counters_by_runtime": original,
                "final_counters": current,
                "baseline_missing_units_by_runtime": original_units,
                "final_missing_units": final_units,
                "unattributed_difference_by_runtime": {
                    version: units - final_units for version, units in original_units.items()
                },
                "denominator_change_by_runtime": {
                    version: current["num_statements"]
                    + current["num_branches"]
                    - row["num_statements"]
                    - row["num_branches"]
                    for version, row in original.items()
                },
                "attributable_round_reduction": None,
                "disposition": "requires_comparable_execution",
                "target_exclusion": None,
            }
        )
    return {
        "schema": "workflows.issue-4426-report-reconciliation/v1",
        "source": "gate-report-inputs.json",
        "source_sha256": REPORT_INPUTS_SHA256,
        "baseline_run_id": inputs["pre_round"]["run"]["id"],
        "final_run_id": final["run"]["id"],
        "final_artifact_id": final["artifact"]["id"],
        "head_sha": final["run"]["head_sha"],
        "tested_checkout": final["checkout"],
        "counter_source": "uniquely_recovered_term_reports",
        "targets": targets,
        "attributable_round_reduction": None,
        "comparable_execution_configuration": False,
        "branch_arcs_recovered": False,
        "archive_bytes_verified": False,
        "execution_configuration_comparison": reconcile_execution_configurations(evidence),
    }


def reconcile_archive(archive: Path, evidence: Path = EVIDENCE) -> dict:
    """Return final counters and exact gaps while retaining unknown attribution."""
    final = _read_inputs(evidence)["final_head"]
    coverage, coverage_digest = read_coverage_archive(archive, final["artifact"]["digest"])
    lines = final["runtime"]["lines"]
    _match_report(coverage["totals"], [FINAL_TOTAL_LINE], "TOTAL")
    targets = {}
    for path in TARGETS:
        row = coverage["files"][path]
        summary = row["summary"]
        _match_report(summary, lines, path)
        missing_lines, missing_branches = row["missing_lines"], row["missing_branches"]
        _validate_inventory(missing_lines, missing_branches, path)
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


def reconcile_current_archive(archive: Path, evidence: Path = EVIDENCE) -> dict:
    """Validate current #4520 evidence separately from the historical #4481 record."""
    inputs = json.loads((evidence / "current-gate-inputs.json").read_bytes())
    artifact, run = inputs["artifact"], inputs["run"]
    head = "02130e674dc2c69e8976edc51771c8a2038bfbf1"
    checkout = "c8e25743a017cc6ca41c8589b058b3fb36712ec0"
    digest = "sha256:452f3bdb6ff19f6db02ec10363a6662608d8fbc6708ad08151d03dac95b752f0"
    if (
        artifact["id"] != 13575534246
        or artifact["digest"] != digest
        or artifact["workflow_run"]["id"] != 42376857143
        or artifact["workflow_run"]["head_sha"] != head
        or run["id"] != 42376857143
        or run["head_sha"] != head
        or run["conclusion"] != "success"
        or inputs["tested_checkout"] != checkout
    ):
        raise ValueError("current Gate identity mismatch")
    if not any(f"Merge {head} into " in line for line in inputs["checkout_lines"]):
        raise ValueError("current Gate checkout log mismatch")
    if not any(line.endswith(checkout) for line in inputs["checkout_lines"]):
        raise ValueError("current Gate tested checkout missing")
    coverage, coverage_digest = read_coverage_archive(archive, digest)
    _match_report(coverage["totals"], inputs["report_lines"], "TOTAL")
    targets = {}
    for path in TARGETS:
        row = coverage["files"][path]
        _match_report(row["summary"], inputs["report_lines"], path)
        _validate_inventory(row["missing_lines"], row["missing_branches"], path)
        if (
            len(row["missing_lines"]) != row["summary"]["missing_lines"]
            or len(row["missing_branches"]) != row["summary"]["missing_branches"]
        ):
            raise ValueError(f"missing-unit inventory disagrees with summary: {path}")
        targets[path] = {key: row[key] for key in ("summary", "missing_lines", "missing_branches")}
    return {
        "schema": "workflows.issue-4426-current-archive/v1",
        "run_id": run["id"],
        "head_sha": head,
        "tested_checkout": checkout,
        "artifact_id": artifact["id"],
        "archive_digest": digest,
        "coverage_json_sha256": coverage_digest,
        "coverage_meta": coverage["meta"],
        "totals": coverage["totals"],
        "targets": targets,
        "attributable_round_reduction": None,
        "original_round_comparable_baseline": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", help="local artifact 13537639987 ZIP")
    parser.add_argument("--reports-only", action="store_true", help="recover pinned log counters")
    parser.add_argument(
        "--current-gate", action="store_true", help="validate separately pinned #4520 archive"
    )
    args = parser.parse_args(argv)
    if args.current_gate and args.archive is None:
        parser.error("--current-gate requires an archive")
    if (args.archive is None) == (not args.reports_only):
        parser.error("provide either an archive or --reports-only")
    try:
        result = (
            reconcile_reports()
            if args.reports_only
            else (
                reconcile_current_archive(args.archive)
                if args.current_gate
                else reconcile_archive(args.archive)
            )
        )
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print(f"Cannot reconcile final Gate artifact: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
