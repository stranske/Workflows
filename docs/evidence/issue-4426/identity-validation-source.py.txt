"""Lock the #4426 pre-round and current Gate coverage measurements.

Blended accounting is coverage.py's branch percent: covered statements plus
covered branches, over statements plus branches. The #3998 90% exception is
applied to the recovered pre-round displays before any remainder is cancelled.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest
from coverage.results import Numbers

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4426"
MEASUREMENT_PATH = EVIDENCE / "coverage-measurement.json"
PYPROJECT = ROOT / "pyproject.toml"
TOTAL_LINE = re.compile(
    r"TOTAL\s+(?P<statements>\d+)\s+(?P<missed>\d+)\s+"
    r"(?P<branches>\d+)\s+(?P<partial>\d+)\s+(?P<display>\d+\.\d+)%"
)
REPORT_INPUTS_SHA256 = "edef0047a34517cdbd3543e0bc308e180865305bcc5f618ba3ea1619dc5e4a3c"
TARGETS = (
    "scripts/sync_test_dependencies.py",
    "scripts/langchain/issue_pr_context.py",
    "scripts/langchain/verifier_config.py",
    "tools/langchain_client.py",
    "scripts/langchain/task_validator.py",
    "scripts/langchain/pr_verifier.py",
)


def recover_missing_branches(summary: dict) -> int:
    """Recover a count only if exactly one integer renders the recorded percentage.

    This cannot identify branch arcs. Large denominators can admit multiple
    counts, so neither a nearest-integer estimate nor BrPart is a substitute.
    Use coverage.py's own rounding, including its handling near 0 and 100.
    """
    statements, missed, branches, partial = (
        summary[key]
        for key in ("num_statements", "missing_lines", "num_branches", "num_partial_branches")
    )
    if (
        any(type(value) is not int for value in (statements, missed, branches, partial))
        or not 0 <= missed <= statements <= 100_000
        or not 0 <= partial <= branches <= 100_000
        or statements + branches == 0
    ):
        raise ValueError("invalid or unbounded coverage counters")
    display = summary["percent_covered_display"]
    if not re.fullmatch(r"(?:\d{1,2}|100)\.\d{2}", display):
        raise ValueError("expected precision-two coverage display")
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
        raise ValueError(f"missing branch count is not unique: {len(candidates)} candidates")
    return candidates[0]


def recover_report_targets(lines: list[str]) -> dict:
    """Recover exactly the six selected targets from bounded recorded log excerpts."""
    if len(lines) > 16 or any(len(line) > 5000 for line in lines):
        raise ValueError("report excerpts exceed the bound")
    targets = {}
    for line in lines:
        for path in TARGETS:
            match = re.search(r"(?:^|\s)" + re.escape(path) + r"\s+(\d.*)", line)
            if match is None:
                continue
            if path in targets:
                raise ValueError("duplicate report target")
            row = parse_coverage_total("TOTAL " + match.group(1))
            row["missing_branches"] = recover_missing_branches(row)
            targets[path] = row
    if set(targets) != set(TARGETS):
        raise ValueError("report does not contain all six targets")
    return targets


def reconcile_gate_reports(inputs: dict) -> dict:
    """Bind log-derived counters to run, artifact, PR head, and merge identity."""
    # Pin identities independently: agreement among supplied fields alone would
    # accept another checkout if its metadata and log excerpts changed together.
    pre_round = inputs["pre_round"]
    if pre_round["run"] != {
        "id": 38980711116,
        "head_sha": "8abd5ec784c97572b2f8baf99e0157bf64728fbb",
        "conclusion": "success",
        "checkout_sha": "682c12c02f24e2b8ee8d69da0d54dae28a87977d",
    } or {version: runtime["job_id"] for version, runtime in pre_round["runtimes"].items()} != {
        "3.12": 117244209085,
        "3.13": 117244209133,
    }:
        raise ValueError("pre-round Gate identity mismatch")
    final = inputs["final_head"]
    run, artifact, checkout = final["run"], final["artifact"], final["checkout"]
    if (
        run
        != {
            "id": 42287174423,
            "head_sha": "97fa3cdd6b198623db4adc86f16f0b3788320794",
            "conclusion": "success",
            "checkout_sha": "e4e584ea61852751c55749ab9ed6539fa10c9a31",
        }
        or final["pr"] != {"number": 4481, "head_sha": run["head_sha"]}
        or artifact["id"] != 13537639987
        or artifact["name"] != "gate-coverage-3.14-1"
        or artifact["digest"]
        != "sha256:c754151adf08a07da718d76b40da09c814ef2ae09e69b982c0635cd9e608c839"
        or artifact["workflow_run"]["id"] != run["id"]
        or artifact["workflow_run"]["head_sha"] != run["head_sha"]
        or checkout
        != {
            "sha": run["checkout_sha"],
            "tree_sha": "c9e0d5158f0dd4bc8166c3667439219b7e943fd9",
            "parents": [
                "d216eaafb02c97ed5f1da16a10d46d9a967c616f",
                run["head_sha"],
            ],
        }
        or final["runtime"]["python"] != "3.14"
        or final["runtime"]["job_id"] != 128131232558
    ):
        raise ValueError("final Gate identity mismatch")
    for snapshot, runtimes, base_sha in (
        (
            pre_round,
            pre_round["runtimes"].values(),
            "e015a93aaa27bc613a979a0e10329a7d9f84b0ed",
        ),
        (final, [final["runtime"]], checkout["parents"][0]),
    ):
        for runtime in runtimes:
            expected = (
                f"{snapshot['run']['checkout_sha'][:7]} "
                f"Merge {snapshot['run']['head_sha']} into {base_sha}"
            )
            observed = [
                line.split(" HEAD is now at ", 1)[1]
                for line in runtime["lines"]
                if " HEAD is now at " in line
            ]
            if not observed or any(identity != expected for identity in observed):
                raise ValueError("log checkout identity mismatch")
    baseline = {
        version: recover_report_targets(runtime["lines"])
        for version, runtime in inputs["pre_round"]["runtimes"].items()
    }
    final_targets = recover_report_targets(final["runtime"]["lines"])

    def units(rows: dict) -> int:
        return sum(row["missing_lines"] + row["missing_branches"] for row in rows.values())

    return {
        "source": "gate-report-inputs.json",
        "source_sha256": REPORT_INPUTS_SHA256,
        "pre_round_targets_by_runtime": baseline,
        "final_head_targets": final_targets,
        "pre_round_missing_units_by_runtime": {v: units(rows) for v, rows in baseline.items()},
        "final_head_missing_units": units(final_targets),
        "unattributed_snapshot_difference_by_runtime": {
            version: units(rows) - units(final_targets) for version, rows in baseline.items()
        },
        "attributable_round_reduction": None,
        "branch_arcs_recovered": False,
        "comparable_execution_configuration": False,
    }


def _report_inputs() -> dict:
    path = EVIDENCE / "gate-report-inputs.json"
    assert path.stat().st_size < 30_000
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == REPORT_INPUTS_SHA256
    return json.loads(data)


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


def test_log_reconciliation_recovers_counts_without_claiming_attribution() -> None:
    inputs = _report_inputs()
    recovered = reconcile_gate_reports(inputs)
    assert recovered == _measurement()["term_report_reconciliation"]
    assert recovered["pre_round_missing_units_by_runtime"] == {"3.12": 402, "3.13": 402}
    assert recovered["final_head_missing_units"] == 238
    assert recovered["unattributed_snapshot_difference_by_runtime"] == {"3.12": 164, "3.13": 164}
    expected = dict(zip(TARGETS, [(1, 5), (13, 6), (1, 1), (3, 2), (3, 3), (107, 93)], strict=True))
    for path, pair in expected.items():
        row = recovered["final_head_targets"][path]
        assert (row["missing_lines"], row["missing_branches"]) == pair
    baseline_pairs = [(1, 5), (17, 13), (7, 9), (21, 8), (25, 13), (169, 114)]
    for rows in recovered["pre_round_targets_by_runtime"].values():
        for path, pair in zip(TARGETS, baseline_pairs, strict=True):
            assert (rows[path]["missing_lines"], rows[path]["missing_branches"]) == pair
    assert recovered["attributable_round_reduction"] is None
    assert recovered["branch_arcs_recovered"] is False
    assert recovered["comparable_execution_configuration"] is False
    # The prior downloaded Gate snapshot is kept, rather than overwritten by logs.
    assert _measurement()["current"]["gate"]["run_id"] == 42250720123
    final_record = json.loads((EVIDENCE / "final-head-gate.json").read_text())
    final = inputs["final_head"]
    assert final_record["head_sha"] == final["run"]["head_sha"]
    assert final_record["run_id"] == final["run"]["id"]
    assert final_record["checkout_sha"] == final["checkout"]["sha"]
    assert final_record["checkout_tree"] == final["checkout"]["tree_sha"]
    assert final_record["checkout_parents"] == final["checkout"]["parents"]
    assert final_record["artifact"]["id"] == final["artifact"]["id"]
    assert final_record["artifact"]["archive_digest"] == final["artifact"]["digest"]
    assert final_record["attributable_round_reduction"] is None
    reconciliation = _measurement()["final_head_reconciliation"]
    assert reconciliation["head_sha"] == final_record["head_sha"]
    assert reconciliation["run_id"] == final_record["run_id"]
    assert reconciliation["artifact_id"] == final_record["artifact"]["id"]
    assert reconciliation["log_derived_target_missing_units"] == 238
    assert reconciliation["unattributed_original_round_snapshot_difference"] == 164
    assert reconciliation["attributable_round_reduction"] is None


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("run", "id", 42250720123),
        ("run", "head_sha", "0" * 40),
        ("run", "conclusion", "failure"),
        ("artifact", "id", 1),
        ("checkout", "sha", "0" * 40),
        ("checkout", "parents", ["0" * 40, "1" * 40]),
    ],
)
def test_reconciliation_rejects_mismatched_final_identity(section, key, value) -> None:
    inputs = copy.deepcopy(_report_inputs())
    inputs["final_head"][section][key] = value
    with pytest.raises(ValueError, match="identity mismatch"):
        reconcile_gate_reports(inputs)


def test_reconciliation_rejects_artifact_or_log_from_another_run() -> None:
    for key, value in (("head_sha", "0" * 40), ("id", 1)):
        inputs = copy.deepcopy(_report_inputs())
        inputs["final_head"]["artifact"]["workflow_run"][key] = value
        with pytest.raises(ValueError, match="identity mismatch"):
            reconcile_gate_reports(inputs)
    inputs = copy.deepcopy(_report_inputs())
    inputs["final_head"]["runtime"]["lines"] = inputs["pre_round"]["runtimes"]["3.13"]["lines"]
    with pytest.raises(ValueError, match="log checkout identity mismatch"):
        reconcile_gate_reports(inputs)


@pytest.mark.parametrize("field", ["id", "head_sha", "conclusion", "checkout_sha", "job_id"])
def test_reconciliation_rejects_substituted_baseline(field) -> None:
    inputs = copy.deepcopy(_report_inputs())
    baseline = inputs["pre_round"]
    record = baseline["runtimes"]["3.12"] if field == "job_id" else baseline["run"]
    record[field] = 1 if field in {"id", "job_id"} else "0" * 40
    with pytest.raises(ValueError, match="pre-round Gate identity mismatch"):
        reconcile_gate_reports(inputs)


@pytest.mark.parametrize("version", ["3.12", "3.13"])
def test_reconciliation_requires_both_baseline_runtime_jobs(version) -> None:
    inputs = copy.deepcopy(_report_inputs())
    del inputs["pre_round"]["runtimes"][version]
    with pytest.raises(ValueError, match="pre-round Gate identity mismatch"):
        reconcile_gate_reports(inputs)


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("pr", "number", 4477),
        ("artifact", "name", "gate-coverage-3.13-1"),
        ("artifact", "digest", "sha256:" + "0" * 64),
        ("checkout", "tree_sha", "0" * 40),
        ("checkout", "parents", ["0" * 40, "97fa3cdd6b198623db4adc86f16f0b3788320794"]),
        ("runtime", "python", "3.13"),
        ("runtime", "job_id", 128005600052),
    ],
)
def test_reconciliation_rejects_substituted_final_provenance(section, key, value) -> None:
    inputs = copy.deepcopy(_report_inputs())
    inputs["final_head"][section][key] = value
    with pytest.raises(ValueError, match="final Gate identity mismatch"):
        reconcile_gate_reports(inputs)


@pytest.mark.parametrize("snapshot", ["pre_round", "final_head"])
def test_reconciliation_rejects_coordinated_head_and_log_substitution(snapshot) -> None:
    inputs = copy.deepcopy(_report_inputs())
    record = inputs[snapshot]
    original_head = record["run"]["head_sha"]
    replacement_head = "0" * 40
    record["run"]["head_sha"] = replacement_head
    if snapshot == "final_head":
        record["pr"]["head_sha"] = replacement_head
        record["artifact"]["workflow_run"]["head_sha"] = replacement_head
        record["checkout"]["parents"][1] = replacement_head
        runtimes = [record["runtime"]]
    else:
        runtimes = record["runtimes"].values()
    for runtime in runtimes:
        runtime["lines"] = [
            line.replace(original_head, replacement_head) for line in runtime["lines"]
        ]
    with pytest.raises(ValueError, match="Gate identity mismatch"):
        reconcile_gate_reports(inputs)


@pytest.mark.parametrize("snapshot", ["pre_round", "final_head"])
@pytest.mark.parametrize("mode", ["replace", "append", "remove", "suffix"])
def test_reconciliation_checks_every_log_merge_parent(snapshot, mode) -> None:
    inputs = copy.deepcopy(_report_inputs())
    record = inputs[snapshot]
    runtime = record["runtime"] if snapshot == "final_head" else record["runtimes"]["3.12"]
    index = next(i for i, line in enumerate(runtime["lines"]) if " HEAD is now at " in line)
    checkout_line = runtime["lines"][index]
    if mode == "replace":
        runtime["lines"][index] = checkout_line.rsplit(" into ", 1)[0] + " into " + "0" * 40
    elif mode == "append":
        runtime["lines"].append(checkout_line.rsplit(" into ", 1)[0] + " into " + "0" * 40)
    elif mode == "suffix":
        runtime["lines"][index] += " (different checkout)"
    else:
        runtime["lines"] = [line for line in runtime["lines"] if " HEAD is now at " not in line]
    with pytest.raises(ValueError, match="log checkout identity mismatch"):
        reconcile_gate_reports(inputs)


def test_report_recovery_rejects_incomplete_duplicate_or_unbounded_excerpts() -> None:
    lines = _report_inputs()["final_head"]["runtime"]["lines"]
    target_line = next(line for line in lines if "scripts/langchain/pr_verifier.py" in line)
    for invalid, message in (
        ([line for line in lines if line != target_line], "all six targets"),
        (lines + [target_line], "duplicate"),
        (lines * 3, "exceed the bound"),
        ([" " * 5001], "exceed the bound"),
    ):
        with pytest.raises(ValueError, match=message):
            recover_report_targets(invalid)


def test_branch_recovery_rejects_ambiguous_totals_and_impossible_counters() -> None:
    # Unlike the target reports, the repository TOTAL permits several counts.
    total = parse_coverage_total("TOTAL 49564 3657 19862 1833 91.21%")
    with pytest.raises(ValueError, match=r"not unique: [2-9] candidates"):
        recover_missing_branches(total)
    row = parse_coverage_total("TOTAL 144 1 70 1 99.07%")
    assert recover_missing_branches(row) == 1
    for changes, message in (
        ({"percent_covered_display": "50.00"}, "not unique: 0 candidates"),
        ({"num_partial_branches": 2}, "not unique: 0 candidates"),
        ({"num_branches": -1}, "invalid or unbounded"),
        ({"num_branches": 100_001}, "invalid or unbounded"),
        ({"missing_lines": True}, "invalid or unbounded"),
        ({"missing_lines": 145}, "invalid or unbounded"),
        ({"percent_covered_display": "99.1"}, "precision-two"),
    ):
        with pytest.raises(ValueError, match=message):
            recover_missing_branches(row | changes)
