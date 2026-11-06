"""Lock the #4426 pre-round and current Gate coverage measurements.

Blended accounting is coverage.py's branch percent: covered statements plus
covered branches, over statements plus branches. The #3998 90% exception is
applied to the recovered pre-round displays before any remainder is cancelled.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4426"
MEASUREMENT_PATH = EVIDENCE / "coverage-measurement.json"
PYPROJECT = ROOT / "pyproject.toml"
TOTAL_LINE = re.compile(
    r"TOTAL\s+(?P<statements>\d+)\s+(?P<missed>\d+)\s+"
    r"(?P<branches>\d+)\s+(?P<partial>\d+)\s+(?P<display>\d+\.\d+)%"
)


def blended_coverage(totals: dict[str, int]) -> dict[str, int | float | str]:
    """Return the statement-plus-branch coverage figure for one totals object."""
    covered = totals["covered_lines"] + totals["covered_branches"]
    denominator = totals["num_statements"] + totals["num_branches"]
    if denominator <= 0:
        raise ValueError("coverage denominator must be positive")
    percent = covered / denominator * 100.0
    return {
        "covered_statements_and_branches": covered,
        "statements_and_branches": denominator,
        "percent_covered": percent,
        "percent_covered_display": f"{percent:.2f}",
    }


def ninety_percent_exception_applies(percent: float, threshold: float = 90.0) -> bool:
    """Apply the #3998 rule that only a pre-round measurement at or above 90% closes the round."""
    if threshold != 90.0:
        raise ValueError("issue #3998 threshold is 90")
    return percent >= threshold


def parse_coverage_total(line: str) -> dict[str, int | str]:
    """Parse one coverage.py term-report TOTAL line."""
    match = TOTAL_LINE.search(line)
    if match is None:
        raise ValueError(f"coverage TOTAL line not found in {line!r}")
    return {
        "num_statements": int(match.group("statements")),
        "missing_lines": int(match.group("missed")),
        "num_branches": int(match.group("branches")),
        "num_partial_branches": int(match.group("partial")),
        "percent_covered_display": match.group("display"),
    }


def _measurement() -> dict:
    return json.loads(MEASUREMENT_PATH.read_text(encoding="utf-8"))


def test_blended_accounting_rejects_an_empty_denominator() -> None:
    with pytest.raises(ValueError, match="positive"):
        blended_coverage(
            {
                "covered_lines": 0,
                "covered_branches": 0,
                "num_statements": 0,
                "num_branches": 0,
            }
        )
    with pytest.raises(ValueError, match="threshold is 90"):
        ninety_percent_exception_applies(91.0, threshold=80.0)


def test_current_gate_and_selftest_share_blended_counters() -> None:
    record = _measurement()
    gate = record["current"]["gate"]["totals"]
    computed = blended_coverage(gate)
    assert computed["covered_statements_and_branches"] == 63216
    assert computed["statements_and_branches"] == 69409
    assert computed["percent_covered_display"] == "91.08"
    assert gate["percent_covered"] == pytest.approx(computed["percent_covered"])
    assert gate["percent_covered_display"] == computed["percent_covered_display"]
    assert gate["covered_lines"] + gate["missing_lines"] == gate["num_statements"]
    assert gate["covered_branches"] + gate["missing_branches"] == gate["num_branches"]
    assert gate["percent_statements_covered"] != gate["percent_covered"]
    assert record["current"]["gate"]["xml_line_rate"] == "0.925"
    assert record["current"]["selftest"]["totals_equal_gate"] is True
    assert (
        record["current"]["gate"]["coverage_json_sha256"]
        != record["current"]["selftest"]["coverage_json_sha256"]
    )
    assert record["current"]["gate"]["python_3_13_coverage_json"] is False
    assert record["current"]["origin_main"] == record["current"]["selftest"]["tested_sha"]
    assert record["current"]["gate"]["tested_sha"] == record["current"]["gate"]["checkout_oid"]
    parsed = parse_coverage_total(record["current"]["gate"]["term_total"])
    assert parsed["num_statements"] == gate["num_statements"]
    assert parsed["missing_lines"] == gate["missing_lines"]
    assert parsed["num_branches"] == gate["num_branches"]
    assert parsed["num_partial_branches"] == gate["num_partial_branches"]
    assert parsed["percent_covered_display"] == gate["percent_covered_display"]


def test_pre_round_below_90_percent_leaves_the_180_unit_rule_in_force() -> None:
    record = _measurement()
    decision = record["contract_decision"]
    displays = []
    for runtime in record["pre_round"]["gate"]["runtimes"].values():
        assert runtime["missing_branches"] is None
        parsed = parse_coverage_total(
            "TOTAL "
            f"{runtime['num_statements']} {runtime['missing_lines']} "
            f"{runtime['num_branches']} {runtime['num_partial_branches']} "
            f"{runtime['percent_covered_display']}%"
        )
        assert parsed["percent_covered_display"] == runtime["percent_covered_display"]
        percent = float(runtime["percent_covered_display"])
        displays.append(percent)
        assert ninety_percent_exception_applies(percent) is False
    assert displays == [81.83, 81.84]
    assert (
        ninety_percent_exception_applies(record["issue_snapshot"]["blended_line_branch_percent"])
        is False
    )
    assert ninety_percent_exception_applies(decision["current_percent_covered"]) is True
    assert decision["pre_round_at_least_90"] is False
    assert decision["exception_applies"] is False
    assert decision["numerical_remainder_cancelled"] is False
    assert record["numerical_rule_about_units"] == 180
    assert record["pre_round"]["gate"]["coverage_json_available"] is False
    assert record["pre_round"]["gate"]["artifact_total_count"] == 0
    assert record["pre_round"]["selftest_artifact_total_count"] == 0
    assert record["issue_snapshot"]["blended_line_branch_percent"] == 82.29

    project = PYPROJECT.read_text(encoding="utf-8")
    assert "branch = true" in project
    assert 'source = ["scripts", "tools", "src"]' in project
    prose = (EVIDENCE / "coverage-measurement.md").read_text(encoding="utf-8")
    for phrase in (
        "81.83%",
        "81.84%",
        "82.29%",
        "91.08%",
        "63216 / 69409",
        "about-180",
        "total_count",
        "8abd5ec784c97572b2f8baf99e0157bf64728fbb",
        "21c87da23935bb2466cb55361d3296d225a92b7e",
        "d58f4aa9e54658c6f904c0cccf62dc3b094ea4e4",
        "53351df5b25d34abd6dcb91852fafcb3b53430bd",
        "pytest -p ci_test_growth",
        "does not apply",
    ):
        assert phrase in prose


def test_same_artifact_target_counters_are_not_called_a_reduction() -> None:
    record = _measurement()
    targets = record["current"]["targets_from_gate_coverage_json"]
    assert "round-wide reduction" in targets["note"]
    expected = {
        "scripts/sync_test_dependencies.py": (1, 5),
        "scripts/langchain/issue_pr_context.py": (13, 6),
        "scripts/langchain/verifier_config.py": (1, 1),
        "tools/langchain_client.py": (15, 6),
        "scripts/langchain/task_validator.py": (3, 3),
        "scripts/langchain/pr_verifier.py": (155, 118),
    }
    for path, (missing_lines, missing_branches) in expected.items():
        row = targets[path]
        assert row["missing_lines"] == missing_lines
        assert row["missing_branches"] == missing_branches
        assert row["num_statements"] > row["missing_lines"]
