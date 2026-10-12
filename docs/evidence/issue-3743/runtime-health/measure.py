"""Collect and verify matched current runtime-health coverage in a fresh directory.

Requires pytest, pytest-cov and defusedxml. Production and historical evidence
are read-only; only --output receives reports. Run from any working directory.
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from defusedxml import ElementTree

BASE = "6020028dec510c931364fb69f63dc2a2aa297689"
SOURCE = "scripts/check_deliberate_break.py"
TEMPLATE = "templates/consumer-repo/" + SOURCE
TEST = "tests/scripts/test_check_deliberate_break_runtime_health.py"
REPAIR = "tests/scripts/test_check_deliberate_break_repair_failures.py"
MODULES = (
    "tests/scripts/test_check_deliberate_break.py",
    "tests/scripts/test_check_deliberate_break_archive.py",
    "tests/scripts/test_check_deliberate_break_launch_boundaries.py",
    "tests/scripts/test_check_deliberate_break_module_boundaries.py",
    REPAIR,
    "tests/scripts/test_check_deliberate_break_runtime_probes.py",
    "tests/scripts/test_check_deliberate_break_uv_resolution.py",
    "tests/scripts/test_module_boundary_replay_isolation.py",
)


def require(condition, message):
    """Keep evidence checks active even when Python runs with -O."""
    if not condition:
        raise ValueError(message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def hashes(root):
    paths = [SOURCE, TEMPLATE, TEST, *MODULES]
    paths.extend(
        str(path.relative_to(root))
        for path in (root / "docs/evidence/issue-3743").rglob("*")
        if path.is_file()
    )
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def nodes(path):
    tree = ElementTree.parse(path)
    require(
        not any(
            int(suite.get(field, "0"))
            for suite in tree.iter("testsuite")
            for field in ("errors", "failures")
        ),
        f"JUnit suite failure: {path}",
    )
    rows = {}
    for case in tree.iter("testcase"):
        key = f"{case.attrib['classname']}::{case.attrib['name']}"
        require(key not in rows, f"Duplicate JUnit node: {key}")
        rows[key] = next(
            (kind for kind in ("failure", "error", "skipped") if case.find(kind) is not None),
            "passed",
        )
    require(bool(rows), f"Empty JUnit report: {path}")
    return rows


def compare(output):
    baseline = nodes(output / "baseline-junit.xml")
    candidate = nodes(output / "candidate-junit.xml")
    coverage = {
        phase: json.loads((output / f"{phase}-coverage.json").read_text())["files"][SOURCE]
        for phase in ("baseline", "candidate")
    }
    b, c = coverage["baseline"], coverage["candidate"]
    comparison = {
        "baseline": b["summary"],
        "candidate": c["summary"],
        "baseline_tests": len(baseline),
        "candidate_tests": len(candidate),
        "new_nodes": sorted(candidate.keys() - baseline.keys()),
        "removed_nodes": sorted(baseline.keys() - candidate.keys()),
        "changed_old_outcomes": {
            key: [value, candidate.get(key)]
            for key, value in baseline.items()
            if value != candidate.get(key)
        },
        "covered_line_regressions": sorted(set(b["executed_lines"]) - set(c["executed_lines"])),
        "covered_branch_regressions": sorted(
            set(map(tuple, b["executed_branches"])) - set(map(tuple, c["executed_branches"]))
        ),
        "newly_covered_lines": sorted(set(c["executed_lines"]) - set(b["executed_lines"])),
        "newly_covered_branches": sorted(
            set(map(tuple, c["executed_branches"])) - set(map(tuple, b["executed_branches"]))
        ),
    }
    require(len(baseline) == 304 and len(candidate) == 312, "Expected 304/312 current cases")
    require(set(candidate.values()) == {"passed"}, "All candidate nodes must pass")
    expected = sorted(
        "tests.scripts.test_check_deliberate_break_runtime_health::"
        "test_active_runtime_health_requires_distribution_version_and_real_import"
        f"[{variant}-{health}]"
        for variant in ("root", "template")
        for health in ("missing", "stale", "broken", "healthy")
    )
    require(comparison["new_nodes"] == expected, "Unexpected added test nodes")
    for field in (
        "removed_nodes",
        "changed_old_outcomes",
        "covered_line_regressions",
        "covered_branch_regressions",
    ):
        require(not comparison[field], f"Matched comparison regressed: {field}")
    for row in coverage.values():
        summary = row["summary"]
        require(
            (summary["num_statements"], summary["num_branches"], summary["excluded_lines"])
            == (591, 262, 0),
            "Coverage universe changed",
        )
    for phase in ("runtime-health", "current-repair"):
        rows = nodes(output / f"{phase}-junit.xml")
        require(len(rows) == 8 and set(rows.values()) == {"passed"}, f"Expected 8 PASS: {phase}")
    require(
        nodes(output / "runtime-health-junit.xml") == dict.fromkeys(expected, "passed"),
        "Focused runtime-health nodes differ from matched additions",
    )
    comparison["historical_reconciliation"] = {
        "old_repair_snapshot": {
            "tests": 6,
            "baseline": 294,
            "candidate": 300,
            "status": "historical; unchanged",
        },
        "current_repair_tests": 8,
        "current_matched_scope": "eight existing test modules, plus runtime-health only for candidate",
    }
    return comparison


def run(root, output, phase, selected, coverage=False):
    env = os.environ.copy()
    # Neither user pytest options nor a dependency staging path may change the
    # matched suite or the production helper's PYTHONPATH branch coverage.
    for key in ("PYTEST_ADDOPTS", "PYTHONPATH"):
        env.pop(key, None)
    env["COVERAGE_FILE"] = str(output / f"{phase}.coverage")
    argv = [sys.executable, "-m", "pytest", *selected, "-q", "-o", "addopts=", "-m", "not slow"]
    if coverage:
        argv.extend(
            [
                "--cov=scripts.check_deliberate_break",
                "--cov-branch",
                "--cov-report=term-missing",
                f"--cov-report=json:{output / (phase + '-coverage.json')}",
            ]
        )
    argv.append(f"--junitxml={output / (phase + '-junit.xml')}")
    receipt = {
        "argv": argv,
        "cwd": str(root),
        "env": {"PYTEST_ADDOPTS": None, "PYTHONPATH": None, "COVERAGE_FILE": env["COVERAGE_FILE"]},
    }
    with (output / f"{phase}-console.log").open("wb") as console:
        try:
            result = subprocess.run(
                argv,
                cwd=root,
                env=env,
                stdout=console,
                stderr=subprocess.STDOUT,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired:
            receipt.update(exit=None, timeout_seconds=300)
            write_json(output / f"{phase}-command.json", receipt)
            raise
    receipt["exit"] = result.returncode
    write_json(output / f"{phase}-command.json", receipt)
    require(result.returncode == 0, f"{phase} exited {result.returncode}; see raw console")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    output = args.output.resolve()
    require(not output.is_relative_to(root), "Keep generated reports outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    before = hashes(root)
    write_json(output / "source-before.json", before)
    require(before[SOURCE] == before[TEMPLATE], "Root/template source bytes differ")
    for path in (SOURCE, TEMPLATE):
        base = subprocess.run(
            ["git", "show", f"{BASE}:{path}"], cwd=root, capture_output=True, check=True
        ).stdout
        require(
            hashlib.sha256(base).hexdigest() == before[path], f"Source changed from base: {path}"
        )
    try:
        run(root, output, "baseline", MODULES, coverage=True)
        run(root, output, "candidate", (*MODULES, TEST), coverage=True)
        run(root, output, "runtime-health", (TEST,))
        run(root, output, "current-repair", (REPAIR,))
        comparison = compare(output)
    finally:
        after = hashes(root)
        write_json(output / "source-after.json", after)
        require(
            before == after,
            "Measured source/tests or historical evidence changed during collection",
        )
    comparison.update(
        base=BASE,
        interpreter=sys.executable,
        python=sys.version,
        platform=platform.platform(),
        production_unchanged=True,
        root_template_identical=True,
        file_sha256=before,
        requested_interpreter_available=Path("/opt/anaconda3/bin/python3").is_file(),
    )
    write_json(output / "comparison.json", comparison)
    print(json.dumps({"baseline_pass": 304, "candidate_pass": 312, "new_nodes": 8}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
