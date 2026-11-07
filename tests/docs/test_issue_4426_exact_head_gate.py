"""Lock exact-head Gate coverage after the delivered #4426 chunks.

Uncovered units are missing statements plus missing branches. The about-180
rule is the #3998 numerical rule. A smaller measured reduction does not
replace it, and incidental coverage outside the six targets is not counted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4426"
RECORD_PATH = EVIDENCE / "exact-head-gate.json"
PROSE_PATH = EVIDENCE / "exact-head-gate.md"
MEASUREMENT_PATH = EVIDENCE / "coverage-measurement.json"
CONTRACT_PATH = EVIDENCE / "contract-3998.json"

TARGET_ORDER = (
    "scripts/langchain/pr_verifier.py",
    "scripts/sync_test_dependencies.py",
    "tools/langchain_client.py",
    "scripts/langchain/task_validator.py",
    "scripts/langchain/verifier_config.py",
    "scripts/langchain/issue_pr_context.py",
)


def uncovered_units(summary: dict[str, int]) -> int:
    """Return missing statements plus missing branches for one coverage summary."""
    missing_lines = summary["missing_lines"]
    missing_branches = summary["missing_branches"]
    if missing_lines < 0 or missing_branches < 0:
        raise ValueError("missing coverage counters cannot be negative")
    return missing_lines + missing_branches


def blended_coverage(totals: dict[str, int]) -> dict[str, int | float | str]:
    """Return statement-plus-branch coverage for one Gate totals object."""
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


def target_units(files: dict[str, dict[str, dict[str, int]]], point: str) -> int:
    """Sum uncovered units for the six #3998 targets at one measurement point."""
    if point not in {"baseline", "after_expanded_comparison_verdict", "exact_head"}:
        raise ValueError(f"unknown measurement point {point}")
    return sum(uncovered_units(files[path][point]) for path in TARGET_ORDER)


def function_delta(row: dict) -> int:
    """Return one symbol's drop in uncovered units from baseline to exact head."""
    return uncovered_units(row["baseline"]) - uncovered_units(row["exact_head"])


def counted_reduction(function_rows: list[dict]) -> int:
    """Sum symbol deltas that belong to the #3998 target list."""
    return sum(function_delta(row) for row in function_rows if row["counted_toward_target_rule"])


def about_180_met(reduction: int, rule: int = 180) -> bool:
    """Apply the original numerical rule without substituting a smaller threshold."""
    if rule != 180:
        raise ValueError("issue #3998 numerical rule is about 180")
    return reduction >= rule


def stop_rule_trips(
    failed_runs_of_same_check: int,
    command_seconds: float | None,
    *,
    attempt_limit: int = 2,
    command_limit_seconds: int = 600,
) -> str | None:
    """Return the first broken stop-rule step, or None when the step may continue."""
    if attempt_limit != 2 or command_limit_seconds != 600:
        raise ValueError("recorded stop rule limits are two failures and 600 seconds")
    if failed_runs_of_same_check >= attempt_limit:
        return "attempt limit"
    if command_seconds is not None and command_seconds > command_limit_seconds:
        return "command limit"
    if failed_runs_of_same_check < 0:
        raise ValueError("failed runs cannot be negative")
    return None


def _record() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def render_exact_head_gate(record: dict) -> str:
    """Render the evidence note from the machine-readable Gate record."""
    files = record["targets"]
    baseline_units = target_units(files, "baseline")
    chunk_units = target_units(files, "after_expanded_comparison_verdict")
    head_units = target_units(files, "exact_head")
    chunk_reduction = baseline_units - chunk_units
    round_reduction = baseline_units - head_units
    second_reduction = chunk_units - head_units
    counted = counted_reduction(record["function_deltas"])
    rule = record["numerical_rule_about_units"]
    met = about_180_met(round_reduction, rule)
    shortfall = 0 if met else rule - round_reduction
    baseline_blend = blended_coverage(record["baseline"]["totals"])
    chunk = record["chunks"][0]["green"]
    head = record["chunks"][1]["green"]
    chunk_blend = blended_coverage(chunk["totals"])
    head_blend = blended_coverage(head["totals"])
    lines = [
        "# Issue #4426 exact-head Gate results",
        "",
        f"Checked {record['checked_on']}. Machine-readable fields are in "
        "`exact-head-gate.json`.",
        record["numerical_rule_status"],
        f"Uncovered units are `{record['uncovered_unit']}`.",
        f"The Gate pytest command is `{record['gate_command']}`, recorded in "
        f"`{record['gate_command_source']}`.",
        record["accounting"],
        "",
        "## Baseline and commits",
        "",
        (
            f"Baseline Gate run {record['baseline']['run_id']} tested "
            f"`{record['baseline']['tested_sha']}` and displays "
            f"{baseline_blend['percent_covered_display']}% "
            f"({baseline_blend['covered_statements_and_branches']} / "
            f"{baseline_blend['statements_and_branches']}). "
            f"`coverage.json` SHA-256 `{record['baseline']['coverage_json_sha256']}`."
        ),
        (
            f"First green chunk head `{record['chunks'][0]['delivered_head']}`, "
            f"synthetic merge `{chunk['tested_sha']}`, displays "
            f"{chunk_blend['percent_covered_display']}% "
            f"({chunk_blend['covered_statements_and_branches']} / "
            f"{chunk_blend['statements_and_branches']})."
        ),
        (
            f"Exact head `{head['head_oid']}`, synthetic merge `{head['tested_sha']}` "
            f"(tree `{head['tested_tree']}`), displays "
            f"{head_blend['percent_covered_display']}% "
            f"({head_blend['covered_statements_and_branches']} / "
            f"{head_blend['statements_and_branches']}). "
            f"`coverage.json` SHA-256 `{head['coverage_json_sha256']}`."
        ),
        "",
        "## CI results",
        "",
        (
            f"Chunk `{record['chunks'][0]['name']}` red run "
            f"{record['chunks'][0]['prior_red']['run_id']} on "
            f"`{record['chunks'][0]['prior_red']['head_oid']}` failed: "
            f"{record['chunks'][0]['prior_red']['python_3_14_summary']}. "
            f"Named failure: {record['chunks'][0]['prior_red']['named_failure']}. "
            f"{record['chunks'][0]['prior_red']['coverage_json_reason']}"
        ),
        (
            f"Green run {chunk['run_id']} concluded {chunk['conclusion']}. "
            f"Python 3.14 junit: {chunk['pytest']['passed']} passed, "
            f"{chunk['pytest']['skipped']} skipped, {chunk['pytest']['xfailed']} xfailed, "
            f"{chunk['pytest']['failed']} failed. Controller elapsed "
            f"{chunk['controller_elapsed_seconds']} seconds."
        ),
        (
            f"Receipt commit `{record['receipt_commit_not_a_coverage_boundary']['head_oid']}` "
            f"Gate run {record['receipt_commit_not_a_coverage_boundary']['run_id']} "
            f"concluded {record['receipt_commit_not_a_coverage_boundary']['conclusion']}. "
            f"{record['receipt_commit_not_a_coverage_boundary']['reason']}"
        ),
        (
            f"Chunk `{record['chunks'][1]['name']}` red run "
            f"{record['chunks'][1]['prior_red']['run_id']} on "
            f"`{record['chunks'][1]['prior_red']['head_oid']}` failed: "
            f"{record['chunks'][1]['prior_red']['python_3_14_summary']}. "
            f"Named failure: {record['chunks'][1]['prior_red']['named_failure']}. "
            f"{record['chunks'][1]['prior_red']['coverage_json_reason']}"
        ),
        (
            f"Exact-head Gate run {head['run_id']} concluded {head['conclusion']} "
            f"on `{head['head_oid']}`. Python 3.14 junit: {head['pytest']['passed']} passed, "
            f"{head['pytest']['skipped']} skipped, {head['pytest']['xfailed']} xfailed, "
            f"{head['pytest']['failed']} failed. Controller elapsed "
            f"{head['controller_elapsed_seconds']} seconds. "
            f"Python 3.13 junit matches those pass counts, coverage.json is "
            f"{str(head['python_3_13']['coverage_json']).lower()}, and coverage status is "
            f"{head['python_3_13']['coverage_status']}."
        ),
        "",
        "## Measured reduction",
        "",
        (
            f"Baseline target units: {baseline_units}. After "
            f"`expanded_comparison_verdict`: {chunk_units} "
            f"(reduction {chunk_reduction}). Exact head: {head_units} "
            f"(further reduction {second_reduction}). "
            f"Round-wide target reduction: {round_reduction}."
        ),
        (
            f"Counted function reduction: {counted}. "
            + (
                f"The reduction of {round_reduction} meets the about-{rule} rule."
                if met
                else (
                    f"The reduction of {round_reduction} leaves the about-{rule} rule unmet. "
                    f"Shortfall: {shortfall} uncovered statements and branches."
                )
            )
        ),
        "No target is excluded. Inability to obtain a terminal receipt is not the reason "
        "any of these files remain open.",
        "",
        "| Target | Baseline units | After first chunk | Exact-head units | Reduction | Excluded |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    dispositions = {item["path"]: item for item in record["dispositions"]}
    for path in TARGET_ORDER:
        before = uncovered_units(files[path]["baseline"])
        middle = uncovered_units(files[path]["after_expanded_comparison_verdict"])
        after = uncovered_units(files[path]["exact_head"])
        excluded = dispositions[path]["exclusion"]
        lines.append(
            f"| `{path}` | {before} | {middle} | {after} | {before - after} | "
            f"{'yes' if excluded else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Symbol attribution",
            "",
            "| Symbol | Counted | Baseline units | Exact-head units | Reduction |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in record["function_deltas"]:
        before = uncovered_units(row["baseline"])
        after = uncovered_units(row["exact_head"])
        lines.append(
            f"| `{row['path']}:{row['symbol']}` | "
            f"{'yes' if row['counted_toward_target_rule'] else 'no'} | "
            f"{before} | {after} | {before - after} |"
        )
    lines.extend(["", "## Dispositions", ""])
    for path in TARGET_ORDER:
        item = dispositions[path]
        lines.append(f"`{path}`: {item['reason']}")
        lines.append("")
    non_target = next(
        row for row in record["function_deltas"] if not row["counted_toward_target_rule"]
    )
    lines.extend(
        [
            f"`{non_target['path']}:{non_target['symbol']}`: {non_target['disposition']}",
            "",
            "## Mutation receipts and stop rule",
            "",
            (
                "Deliberate-break receipts remain in "
                f"`{record['mutation_receipts']['record']}`. Production files still match "
                "the restored SHA-256 values. No mutation is left in the tree."
            ),
            record["stop_rule"]["decision"],
            (
                f"Stopping step: {record['stop_rule']['stopping_step']}. "
                f"Stop rule tripped: {str(record['stop_rule']['tripped']).lower()}."
            ),
            (
                "Cost since the preceding report: red Gate "
                f"{record['cost_since_preceding_report']['red_gate_run_id']} "
                f"({record['cost_since_preceding_report']['red_python_3_14_pytest_seconds']}s "
                "Python 3.14 pytest) and green Gate "
                f"{record['cost_since_preceding_report']['green_gate_run_id']} "
                f"({record['cost_since_preceding_report']['green_python_3_14_controller_seconds']}s "
                "Python 3.14 controller; "
                f"{record['cost_since_preceding_report']['green_python_3_13_controller_seconds']}s "
                "Python 3.13 controller). Local full pytest: "
                f"{record['cost_since_preceding_report']['local_full_pytest']}."
            ),
            "",
            "## Follow-ups",
            "",
        ]
    )
    for item in record["follow_ups"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def test_negative_counters_and_foreign_thresholds_are_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        uncovered_units({"missing_lines": -1, "missing_branches": 0})
    with pytest.raises(ValueError, match="positive"):
        blended_coverage(
            {
                "covered_lines": 0,
                "covered_branches": 0,
                "num_statements": 0,
                "num_branches": 0,
            }
        )
    with pytest.raises(ValueError, match="about 180"):
        about_180_met(200, rule=100)
    with pytest.raises(ValueError, match="600 seconds"):
        stop_rule_trips(1, None, command_limit_seconds=30)
    with pytest.raises(ValueError, match="unknown measurement point"):
        target_units(_record()["targets"], "local")


def test_exact_head_reduction_is_89_and_does_not_meet_about_180() -> None:
    record = _record()
    files = record["targets"]
    assert target_units(files, "baseline") == 327
    assert target_units(files, "after_expanded_comparison_verdict") == 254
    assert target_units(files, "exact_head") == 238
    assert counted_reduction(record["function_deltas"]) == 89
    assert about_180_met(89) is False
    assert about_180_met(180) is True
    incidental = [row for row in record["function_deltas"] if not row["counted_toward_target_rule"]]
    assert [row["path"] for row in incidental] == ["tools/llm_registry.py"]
    assert function_delta(incidental[0]) == 2
    assert all(item["exclusion"] is False for item in record["dispositions"])
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["numerical_rule"]["about_units"] == record["numerical_rule_about_units"] == 180


def test_blended_displays_match_the_downloaded_totals() -> None:
    record = _record()
    baseline = blended_coverage(record["baseline"]["totals"])
    chunk = blended_coverage(record["chunks"][0]["green"]["totals"])
    head = blended_coverage(record["chunks"][1]["green"]["totals"])
    assert baseline["percent_covered_display"] == "91.08"
    assert baseline["covered_statements_and_branches"] == 63216
    assert baseline["statements_and_branches"] == 69409
    assert chunk["percent_covered_display"] == "91.18"
    assert chunk["covered_statements_and_branches"] == 63289
    assert head["percent_covered_display"] == "91.21"
    assert head["covered_statements_and_branches"] == 63324
    assert head["statements_and_branches"] == 69426
    measurement = json.loads(MEASUREMENT_PATH.read_text(encoding="utf-8"))
    measured = measurement["current"]["targets_from_gate_coverage_json"]
    for path in TARGET_ORDER:
        row = measured[path]
        assert uncovered_units(row) == uncovered_units(record["targets"][path]["baseline"])
    assert measurement["current"]["gate"]["coverage_json_sha256"] == (
        record["baseline"]["coverage_json_sha256"]
    )


def test_exact_head_pytest_passed_and_the_stop_rule_did_not_trip() -> None:
    record = _record()
    head = record["chunks"][1]["green"]
    assert head["conclusion"] == "success"
    assert head["head_oid"] == "97fa3cdd6b198623db4adc86f16f0b3788320794"
    assert head["pytest"] == head["python_3_13"]["pytest"]
    assert head["pytest"]["failed"] == 0
    assert head["python_3_13"]["coverage_json"] is False
    assert record["stop_rule"]["tripped"] is False
    assert stop_rule_trips(1, None) is None
    assert stop_rule_trips(2, None) == "attempt limit"
    assert stop_rule_trips(0, head["controller_elapsed_seconds"]) == "command limit"
    assert record["stop_rule"]["local_full_suite_started"] is False
    for chunk in record["chunks"]:
        assert chunk["prior_red"]["coverage_json_in_this_record"] is False
        assert chunk["green"]["pytest"]["failed"] == 0


def test_restored_production_hashes_match_the_mutation_receipts() -> None:
    record = _record()
    for path, expected in record["mutation_receipts"]["sha256"].items():
        digest = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert digest == expected
    assert record["mutation_receipts"]["production_restored"] is True


def test_committed_prose_matches_the_renderer() -> None:
    record = _record()
    prose = render_exact_head_gate(record)
    assert PROSE_PATH.read_text(encoding="utf-8") == prose
    for phrase in (
        "about-180",
        "97fa3cdd6b198623db4adc86f16f0b3788320794",
        "e4e584ea61852751c55749ab9ed6539fa10c9a31",
        "91.21%",
        "Round-wide target reduction: 89",
        "Shortfall: 91",
        "Stop rule tripped: false",
        "tools/llm_registry.py",
        "49864 passed",
    ):
        assert phrase in prose
