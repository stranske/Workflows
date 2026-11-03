"""Regression checks for complete, unambiguous target accounting."""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "docs/evidence/issue-4001/extract_target_coverage.py"
SPEC = importlib.util.spec_from_file_location("target_coverage", SCRIPT)
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


def payload():
    return {
        "files": {
            target: {"summary": {"missing_lines": 2, "missing_branches": 3, "percent_covered": 90}}
            for target in extractor.TARGETS
        }
    }


def run_cli(tmp_path, data):
    source = tmp_path / "coverage.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(source)], capture_output=True, text=True, check=False
    )


def test_complete_input_reports_all_targets_and_exact_total(tmp_path):
    data = payload()
    target = extractor.TARGETS[0]
    data["files"]["C:\\repo\\" + target.replace("/", "\\")] = data["files"].pop(target)
    result = run_cli(tmp_path, data)
    assert result.returncode == 0
    assert set(json.loads(result.stdout)) == set(extractor.TARGETS)
    assert result.stderr.strip() == "combined_missing_units=15"


@pytest.mark.parametrize("count", ["missing_lines", "missing_branches"])
@pytest.mark.parametrize("value", [None, -1, True, "3", 1.5])
def test_missing_or_invalid_counts_never_print_partial_success(tmp_path, count, value):
    data = payload()
    summary = data["files"][extractor.TARGETS[0]]["summary"]
    if value is None:
        del summary[count]
    else:
        summary[count] = value
    result = run_cli(tmp_path, data)
    assert result.returncode == 2
    assert result.stdout == ""
    assert count in result.stderr
    assert "combined_missing_units=" not in result.stderr


@pytest.mark.parametrize("case", ["absent", "suffix", "duplicate", "summary", "files"])
def test_absent_or_ambiguous_targets_fail_without_a_total(tmp_path, case):
    data = payload()
    target = extractor.TARGETS[0]
    if case == "absent":
        del data["files"][target]
    elif case == "suffix":
        data["files"]["not_" + target] = data["files"].pop(target)
    elif case == "duplicate":
        data["files"]["/another/" + target] = data["files"][target]
    elif case == "summary":
        del data["files"][target]["summary"]
    else:
        del data["files"]
    result = run_cli(tmp_path, data)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "combined_missing_units=" not in result.stderr


def test_historical_gate_counts_are_uniquely_recoverable_from_raw_rows():
    totals = []
    for stage in ("before", "after"):
        folder = SCRIPT.parent / "gate-ci" / stage
        data = json.loads((folder / "target-coverage.json").read_text())
        raw = (folder / "job-excerpt.txt").read_text()
        assert set(data["files"]) == set(extractor.TARGETS)
        total = 0
        for target in extractor.TARGETS:
            row = re.search(
                re.escape(target) + r"\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)%",
                raw,
            )
            statements, missing_lines, branches, partial = map(int, row.groups()[:4])
            percent = row.group(5)
            candidates = [
                missing
                for missing in range(branches + 1)
                if f"{100 * (statements + branches - missing_lines - missing) / (statements + branches):.2f}"
                == percent
            ]
            summary = data["files"][target]["summary"]
            assert candidates == [summary["missing_branches"]]
            assert missing_lines == summary["missing_lines"]
            assert partial == summary["num_partial_branches"]
            total += missing_lines + candidates[0]
        totals.append(total)
    assert totals == [226, 153]
    assert totals[0] - totals[1] == 73
