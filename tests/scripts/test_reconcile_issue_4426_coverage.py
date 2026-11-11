"""Exercise offline artifact ingestion with explicitly synthetic ZIP bytes.

The real archive remains inaccessible. ZIP fixtures must never be recorded as
downloaded evidence. Report-mode tests use the actual pinned historical logs.
"""

from __future__ import annotations

import hashlib
import json
import re
import warnings
import zipfile
from copy import deepcopy

import pytest
from scripts import compare_gate_coverage as compare
from scripts import reconcile_issue_4426_coverage as reconcile


def _archive(tmp_path, coverage, *, names=(reconcile.COVERAGE_MEMBER,)):
    path = tmp_path / "synthetic.zip"
    data = json.dumps(coverage).encode()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                archive.writestr(name, data)
    return path, "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def synthetic_gate(tmp_path, monkeypatch):
    inputs = json.loads((reconcile.EVIDENCE / "gate-report-inputs.json").read_bytes())
    lines = inputs["final_head"]["runtime"]["lines"]

    def summary(name):
        line = (
            reconcile.FINAL_TOTAL_LINE
            if name == "TOTAL"
            else next(line for line in lines if re.search(r"\s" + re.escape(name) + r"\s", line))
        )
        fields = line.split(name, 1)[1].split()
        return dict(
            zip(
                ("num_statements", "missing_lines", "num_branches", "num_partial_branches"),
                map(int, fields[:4]),
                strict=True,
            ),
            percent_covered_display=fields[4].rstrip("%"),
        )

    files = {}
    # Counts match the term reports; inventory positions are deliberately synthetic.
    for path, missing_branches in zip(reconcile.TARGETS, (5, 6, 1, 2, 3, 93), strict=True):
        counters = summary(path) | {"missing_branches": missing_branches}
        counters["covered_lines"] = counters["num_statements"] - counters["missing_lines"]
        counters["covered_branches"] = counters["num_branches"] - missing_branches
        files[path] = {
            "summary": counters,
            "missing_lines": list(range(1, counters["missing_lines"] + 1)),
            "missing_branches": [[i + 1, -1] for i in range(missing_branches)],
        }
    coverage = {
        "meta": {"branch_coverage": True, "version": "7.17.2", "synthetic_fixture": True},
        "totals": summary("TOTAL") | {"missing_branches": 2445},
        "files": files,
    }
    totals = coverage["totals"]
    totals["covered_lines"] = totals["num_statements"] - totals["missing_lines"]
    totals["covered_branches"] = totals["num_branches"] - totals["missing_branches"]
    evidence = tmp_path / "evidence"
    evidence.mkdir()

    def write_fixture():
        archive, digest = _archive(tmp_path, coverage)
        inputs["final_head"]["artifact"]["digest"] = digest
        data = json.dumps(inputs).encode()
        (evidence / "gate-report-inputs.json").write_bytes(data)
        monkeypatch.setattr(reconcile, "REPORT_INPUTS_SHA256", hashlib.sha256(data).hexdigest())
        return archive

    return coverage, evidence, write_fixture


def test_reconcile_exports_exact_inventories_and_merge_identity_without_credit(synthetic_gate):
    coverage, evidence, write = synthetic_gate
    archive = write()
    historical = (evidence / "gate-report-inputs.json").read_bytes()
    report = reconcile.reconcile_archive(archive, evidence)

    assert report["run_id"] == 42287174423
    assert report["artifact_id"] == 13537639987
    assert report["head_sha"] == "97fa3cdd6b198623db4adc86f16f0b3788320794"
    assert report["tested_checkout"]["sha"] == "e4e584ea61852751c55749ab9ed6539fa10c9a31"
    assert report["tested_checkout"]["parents"][-1] == report["head_sha"]
    assert report["python"] == "3.14"
    assert report["job_id"] == 128131232558
    assert report["target_missing_units"] == 238
    assert list(report["targets"]) == list(reconcile.TARGETS)
    for path, target in report["targets"].items():
        assert target["summary"] == coverage["files"][path]["summary"]
        assert target["missing_lines"] == coverage["files"][path]["missing_lines"]
        assert target["missing_branches"] == coverage["files"][path]["missing_branches"]
    assert report["totals"] == coverage["totals"]
    assert (
        report["coverage_json_sha256"] == hashlib.sha256(json.dumps(coverage).encode()).hexdigest()
    )
    assert report["archive_digest"] == "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    assert report["original_round_comparable_baseline"] is None
    assert report["attributable_round_reduction"] is None
    assert (evidence / "gate-report-inputs.json").read_bytes() == historical
    assert sorted(path.name for path in evidence.iterdir()) == ["gate-report-inputs.json"]


def test_reconcile_rejects_unpinned_identity_metadata(synthetic_gate):
    _coverage, evidence, write = synthetic_gate
    archive = write()
    path = evidence / "gate-report-inputs.json"
    inputs = json.loads(path.read_bytes())
    inputs["final_head"]["checkout"]["sha"] = "0" * 40
    path.write_text(json.dumps(inputs))
    with pytest.raises(ValueError, match="metadata digest mismatch"):
        reconcile.reconcile_archive(archive, evidence)


@pytest.mark.parametrize("scope", ["target", "TOTAL"])
@pytest.mark.parametrize("field", ["missing_lines", "percent_covered_display"])
def test_reconcile_rejects_counters_or_percentage_disagreeing_with_log(
    synthetic_gate, scope, field
):
    coverage, evidence, write = synthetic_gate
    summary = (
        coverage["totals"]
        if scope == "TOTAL"
        else coverage["files"][reconcile.TARGETS[0]]["summary"]
    )
    summary[field] = "0.00" if field == "percent_covered_display" else 0
    with pytest.raises(ValueError, match="disagree.*Gate log"):
        reconcile.reconcile_archive(write(), evidence)


@pytest.mark.parametrize("field", ["missing_lines", "missing_branches"])
def test_reconcile_rejects_incomplete_unit_inventory(synthetic_gate, field):
    coverage, evidence, write = synthetic_gate
    coverage["files"][reconcile.TARGETS[0]][field].pop()
    with pytest.raises(ValueError, match="inventory disagrees"):
        reconcile.reconcile_archive(write(), evidence)


@pytest.mark.parametrize("scope", ["target", "TOTAL"])
def test_reconcile_rejects_branch_counts_that_contradict_percentage(synthetic_gate, scope):
    coverage, evidence, write = synthetic_gate
    row = coverage["files"][reconcile.TARGETS[0]]
    summary = coverage["totals"] if scope == "TOTAL" else row["summary"]
    # Preserve covered+missing identities and target inventory lengths. Only the
    # recomputed precision-two percentage exposes this otherwise plausible input.
    change = 20 if scope == "TOTAL" else 1
    summary["missing_branches"] += change
    summary["covered_branches"] -= change
    if scope == "target":
        row["missing_branches"].append([9000, -1])
    with pytest.raises(ValueError, match="branch counters disagree with coverage percentage"):
        reconcile.reconcile_archive(write(), evidence)


@pytest.mark.parametrize("scope", ["target", "TOTAL"])
@pytest.mark.parametrize("field", ["covered_lines", "covered_branches"])
def test_reconcile_rejects_inconsistent_covered_counters(synthetic_gate, scope, field):
    coverage, evidence, write = synthetic_gate
    summary = (
        coverage["totals"]
        if scope == "TOTAL"
        else coverage["files"][reconcile.TARGETS[0]]["summary"]
    )
    summary[field] += 1
    with pytest.raises(ValueError, match="inconsistent covered counters"):
        reconcile.reconcile_archive(write(), evidence)


@pytest.mark.parametrize(("target", "value"), [(2, True), (0, 5.0)])
def test_reconcile_rejects_invalid_missing_branch_counters(synthetic_gate, target, value):
    coverage, evidence, write = synthetic_gate
    # Both values compare equal to the real count; arithmetic, percentage and
    # inventory length checks alone cannot expose the invalid JSON counter type.
    coverage["files"][reconcile.TARGETS[target]]["summary"]["missing_branches"] = value
    with pytest.raises(ValueError, match="invalid coverage counters"):
        reconcile.reconcile_archive(write(), evidence)


@pytest.mark.parametrize("field", ["missing_lines", "missing_branches"])
def test_reconcile_rejects_duplicate_missing_units(synthetic_gate, field):
    coverage, evidence, write = synthetic_gate
    inventory = coverage["files"][reconcile.TARGETS[-1]][field]
    inventory[-1] = inventory[0]
    expected = "missing-line" if field == "missing_lines" else "missing-branch"
    with pytest.raises(ValueError, match=f"invalid {expected} inventory"):
        reconcile.reconcile_archive(write(), evidence)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("missing_lines", 0),
        ("missing_lines", -1),
        ("missing_lines", True),
        ("missing_lines", "1"),
        ("missing_branches", [0, 1]),
        ("missing_branches", [-1, 1]),
        ("missing_branches", [1, 0]),
        ("missing_branches", [1, False]),
        ("missing_branches", [1]),
        ("missing_branches", [1, 2, 3]),
        ("missing_branches", "1->2"),
    ],
)
def test_reconcile_rejects_malformed_missing_unit_positions(synthetic_gate, field, value):
    coverage, evidence, write = synthetic_gate
    coverage["files"][reconcile.TARGETS[-1]][field][0] = value
    expected = "missing-line" if field == "missing_lines" else "missing-branch"
    with pytest.raises(ValueError, match=f"invalid {expected} inventory"):
        reconcile.reconcile_archive(write(), evidence)


def test_archive_digest_rejects_different_bytes_before_zip_parsing(tmp_path):
    path = tmp_path / "wrong.zip"
    path.write_bytes(b"not even a zip")
    with pytest.raises(ValueError, match="archive digest mismatch"):
        reconcile.read_coverage_archive(path, "sha256:" + "0" * 64)


@pytest.mark.parametrize(
    "names",
    [(), ("coverage.json",), ("runtimes/3.13/coverage.json",), (reconcile.COVERAGE_MEMBER,) * 2],
)
def test_archive_requires_one_recorded_runtime_coverage_file(tmp_path, names):
    path, digest = _archive(tmp_path, {}, names=names)
    with pytest.raises(ValueError, match="exactly one runtimes/3.14/coverage.json"):
        reconcile.read_coverage_archive(path, digest)


def test_archive_selects_recorded_runtime_among_other_coverage_files(tmp_path):
    path = tmp_path / "multiple-runtimes.zip"
    expected = {"meta": {"branch_coverage": True}, "chosen_runtime": "3.14"}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("coverage.json", "{}")
        archive.writestr("runtimes/3.13/coverage.json", "{}")
        archive.writestr("runtimes/3.14/coverage.json", json.dumps(expected))
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    coverage, _digest = reconcile.read_coverage_archive(path, digest)
    assert coverage == expected


@pytest.mark.parametrize("lines", [[], ["TOTAL 1 0 0 0 100.00%"] * 2])
def test_report_match_requires_exactly_one_row(lines):
    with pytest.raises(ValueError, match="expected one pinned term report"):
        reconcile._match_report({}, lines, "TOTAL")


def test_total_report_is_preserved_in_final_head_evidence():
    record = json.loads((reconcile.EVIDENCE / "final-head-gate.json").read_bytes())
    assert record["job_id"] == 128131232558
    assert any(
        " ".join(line.split()).endswith(reconcile.FINAL_TOTAL_LINE)
        for line in record["log_excerpts"]
    )


def test_archive_checks_branch_mode(tmp_path):
    path, digest = _archive(tmp_path, {"meta": {"branch_coverage": False}})
    with pytest.raises(ValueError, match="branch coverage is required"):
        reconcile.read_coverage_archive(path, digest)


@pytest.mark.parametrize("oversized", ["archive", "coverage"])
def test_archive_limits_compressed_and_expanded_input(tmp_path, monkeypatch, oversized):
    path, digest = _archive(tmp_path, {"meta": {"branch_coverage": True}, "padding": "a" * 10_000})
    limit = path.stat().st_size - 1 if oversized == "archive" else 1000
    monkeypatch.setattr(reconcile, "MAX_BYTES", limit)
    expected = "archive" if oversized == "archive" else "coverage.json"
    with pytest.raises(ValueError, match=expected + " exceeds byte limit"):
        reconcile.read_coverage_archive(path, digest)


def test_cli_prints_report_and_returns_failure_without_partial_json(
    synthetic_gate, monkeypatch, capsys
):
    _coverage, evidence, write = synthetic_gate
    archive = write()
    implementation = reconcile.reconcile_archive
    monkeypatch.setattr(reconcile, "reconcile_archive", lambda path: implementation(path, evidence))
    assert reconcile.main([str(archive)]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["target_missing_units"] == 238
    assert output.err == ""

    archive.write_bytes(b"truncated archive")
    assert reconcile.main([str(archive)]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "archive digest mismatch" in output.err


def test_report_mode_reproduces_real_target_accounting_without_artifact_credit():
    report = reconcile.reconcile_reports()
    assert report["head_sha"] == "97fa3cdd6b198623db4adc86f16f0b3788320794"
    assert report["tested_checkout"]["sha"] == "e4e584ea61852751c55749ab9ed6539fa10c9a31"
    assert report["tested_checkout"]["parents"][-1] == report["head_sha"]
    assert report["baseline_run_id"] == 38980711116
    assert report["final_run_id"] == 42287174423
    assert report["final_artifact_id"] == 13537639987
    assert report["source_sha256"] == reconcile.REPORT_INPUTS_SHA256
    assert [row["path"] for row in report["targets"]] == list(reconcile.TARGETS)
    for filename in ("coverage-measurement.json", "ranking.json"):
        evidence = json.loads((reconcile.EVIDENCE / filename).read_bytes())
        assert report["targets"] == evidence["target_snapshot_comparison"]["targets"]
    assert sum(row["final_missing_units"] for row in report["targets"]) == 238
    for version in ("3.12", "3.13"):
        assert (
            sum(row["baseline_missing_units_by_runtime"][version] for row in report["targets"])
            == 402
        )
        assert (
            sum(row["unattributed_difference_by_runtime"][version] for row in report["targets"])
            == 164
        )
    for row in report["targets"]:
        assert row["attributable_round_reduction"] is None
        assert row["target_exclusion"] is None
        assert row["disposition"] == "requires_comparable_execution"
    # A zero snapshot difference is still unknown improvement, not measured zero.
    assert report["targets"][0]["unattributed_difference_by_runtime"] == {"3.12": 0, "3.13": 0}
    assert report["attributable_round_reduction"] is None
    assert report["comparable_execution_configuration"] is False
    assert report["branch_arcs_recovered"] is False
    assert report["archive_bytes_verified"] is False


def test_report_mode_rejects_changed_pinned_baseline(tmp_path):
    inputs = json.loads((reconcile.EVIDENCE / "gate-report-inputs.json").read_bytes())
    inputs["pre_round"]["run"]["head_sha"] = "0" * 40
    (tmp_path / "gate-report-inputs.json").write_text(json.dumps(inputs))
    with pytest.raises(ValueError, match="metadata digest mismatch"):
        reconcile.reconcile_reports(tmp_path)


@pytest.mark.parametrize(
    "row",
    [
        "100000 0 100000 0 99.99%",  # Multiple missing counts render identically.
        "1 0 2 0 50.00%",  # No integer missing count can render this percentage.
        "1 2 2 0 50.00%",  # Missing statements exceed the denominator.
        "100001 0 2 0 100.00%",  # Bound the work spent on branch recovery.
        "1 0 2 3 100.00%",  # Partial branches exceed total branches.
    ],
)
def test_report_mode_rejects_ambiguous_impossible_or_unbounded_counters(row):
    with pytest.raises(ValueError, match="not unique|invalid or unbounded"):
        reconcile._recover_report_targets([reconcile.TARGETS[0] + " " + row])


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "too_many", "too_long"])
def test_report_mode_rejects_incomplete_duplicate_or_oversized_logs(mutation):
    inputs = json.loads((reconcile.EVIDENCE / "gate-report-inputs.json").read_bytes())
    lines = inputs["final_head"]["runtime"]["lines"]
    if mutation == "missing":
        lines = [line for line in lines if reconcile.TARGETS[0] not in line]
    elif mutation == "duplicate":
        lines.append(next(line for line in lines if reconcile.TARGETS[0] in line))
    elif mutation == "too_many":
        lines += ["unrelated"] * 17
    else:
        lines.append("x" * 5001)
    with pytest.raises(ValueError, match="expected one|exceed the bound"):
        reconcile._recover_report_targets(lines)


@pytest.mark.parametrize("argv", [[], ["unread.zip", "--reports-only"]])
def test_cli_requires_exactly_one_reconciliation_mode(argv, capsys):
    with pytest.raises(SystemExit) as error:
        reconcile.main(argv)
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "provide either an archive or --reports-only" in output.err


def test_cli_reports_real_counters_without_opening_archive(monkeypatch, capsys):
    def unexpected_archive(*args):
        pytest.fail("report mode attempted to open an archive")

    monkeypatch.setattr(reconcile, "read_coverage_archive", unexpected_archive)
    assert reconcile.main(["--reports-only"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == reconcile.reconcile_reports()
    assert output.err == ""

    def unavailable():
        raise ValueError("pinned Gate metadata digest mismatch")

    monkeypatch.setattr(reconcile, "reconcile_reports", unavailable)
    assert reconcile.main(["--reports-only"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "pinned Gate metadata digest mismatch" in output.err


def test_execution_reconciliation_records_policy_drift_without_rewriting_history():
    inputs = json.loads((reconcile.EVIDENCE / "gate-execution-inputs.json").read_bytes())
    for name, blob_sha in (
        ("pre_round", "be00769e20f7366d2ff16ce51507fbbdc2d28d50"),
        ("final_head", "df271c04ded9fcadf41873b5f1d08fa78729d3de"),
    ):
        project = inputs[name]["pyproject"]
        content = project["content"].encode()
        git_object = b"blob " + str(len(content)).encode() + b"\0" + content
        assert hashlib.sha1(git_object).hexdigest() == project["git_blob_sha"] == blob_sha
    report = reconcile.reconcile_reports()
    comparison = report["execution_configuration_comparison"]
    recorded = json.loads(
        (reconcile.EVIDENCE / "execution-configuration-comparison.json").read_bytes()
    )
    assert comparison == recorded
    assert comparison["baseline_checkout"] == "682c12c02f24e2b8ee8d69da0d54dae28a87977d"
    assert comparison["final_checkout"] == report["tested_checkout"]["sha"]
    final = comparison["final_settings"]
    assert final["python"] == "3.14.10"
    assert final["entrypoint"] == "pytest -p ci_test_growth"
    assert final["extra_args"] == ["-n", "auto", "--dist", "load"]
    for version, python in (("3.12", "3.12.15"), ("3.13", "3.13.16")):
        baseline = comparison["baselines_by_runtime"][version]
        assert baseline["settings"]["coverage"]["run"] == final["coverage"]["run"]
        assert baseline["settings"]["workers_observed"] == final["workers_observed"] == 4
        assert baseline["settings"]["marker"] == final["marker"] == "not quarantine and not slow"
        assert baseline["differences_from_final"]["python"] == {
            "baseline": python,
            "final": "3.14.10",
        }
        assert baseline["differences_from_final"]["coverage.report.exclude_also"] == {
            "baseline": None,
            "final": ["if __name__ == .__main__.:"],
        }
        assert baseline["differences_from_final"]["coverage_version"] == {
            "baseline": "7.16.2",
            "final": "7.17.2",
        }
        assert baseline["settings_equal"] is False
    assert comparison["attributable_round_reduction"] is None
    assert report["targets"][0]["unattributed_difference_by_runtime"] == {"3.12": 0, "3.13": 0}
    for name in ("coverage-measurement.json", "ranking.json"):
        record = json.loads((reconcile.EVIDENCE / name).read_bytes())
        assert record["final_head_reconciliation"]["execution_configuration_record"] == (
            "execution-configuration-comparison.json"
        )


def test_execution_difference_keeps_removed_exclusions_and_changed_source_selection():
    before = {"coverage": {"run": {"source": ["scripts"]}, "report": {"exclude_also": ["guard"]}}}
    after = {"coverage": {"run": {"source": ["tools"]}, "report": {}}}
    assert reconcile._configuration_differences(before, after) == {
        "coverage.run.source": {"baseline": ["scripts"], "final": ["tools"]},
        "coverage.report.exclude_also": {"baseline": ["guard"], "final": None},
    }


def test_matching_execution_settings_do_not_establish_attribution(monkeypatch):
    settings = reconcile.reconcile_execution_configurations()["final_settings"]
    monkeypatch.setattr(reconcile, "_execution_settings", lambda *args: deepcopy(settings))
    comparison = reconcile.reconcile_execution_configurations()
    for baseline in comparison["baselines_by_runtime"].values():
        assert baseline["settings_equal"] is True
        assert baseline["differences_from_final"] == {}
    assert comparison["comparable_execution_configuration"] is False
    assert comparison["source_and_test_equivalence_verified"] is False
    assert comparison["attributable_round_reduction"] is None


def test_execution_reconciliation_rejects_substituted_record(tmp_path):
    original = (reconcile.EVIDENCE / "gate-execution-inputs.json").read_bytes()
    replaced = original.replace(b"not quarantine and not slow", b"not slow")
    assert replaced != original
    (tmp_path / "gate-execution-inputs.json").write_bytes(replaced)
    (tmp_path / "gate-report-inputs.json").write_bytes(
        (reconcile.EVIDENCE / "gate-report-inputs.json").read_bytes()
    )
    with pytest.raises(ValueError, match="pinned Gate execution digest mismatch"):
        reconcile.reconcile_execution_configurations(tmp_path)


@pytest.mark.parametrize("missing", [False, True], ids=["duplicate", "missing"])
def test_execution_settings_require_unambiguous_observed_runtime(missing):
    inputs = json.loads((reconcile.EVIDENCE / "gate-execution-inputs.json").read_bytes())
    final = inputs["final_head"]
    lines = final["runtime"]["log_excerpts"]
    platform = next(line for line in lines if "platform linux -- Python" in line)
    if missing:
        lines.remove(platform)
    else:
        lines.append(platform)
    with pytest.raises(ValueError, match="expected one execution setting"):
        reconcile._execution_settings(final["pyproject"], final["runtime"])


def test_current_archive_stays_separate_from_historical_evidence(monkeypatch, tmp_path):
    record = json.loads((reconcile.EVIDENCE / "current-gate-reconciled.json").read_bytes())
    coverage = {
        "meta": record["coverage_meta"],
        "totals": record["totals"],
        "files": record["targets"],
    }
    monkeypatch.setattr(
        reconcile, "read_coverage_archive", lambda *args: (coverage, record["coverage_json_sha256"])
    )
    result = reconcile.reconcile_current_archive(tmp_path / "unused.zip")
    assert result == record
    assert result["attributable_round_reduction"] is None
    assert result["tested_checkout"] != result["head_sha"]


@pytest.mark.parametrize("corruption", ["head", "digest", "merge_log", "checkout_log"])
def test_current_archive_rejects_unbound_provenance(tmp_path, corruption):
    inputs = json.loads((reconcile.EVIDENCE / "current-gate-inputs.json").read_bytes())
    if corruption == "head":
        inputs["artifact"]["workflow_run"]["head_sha"] = "0" * 40
    elif corruption == "digest":
        inputs["artifact"]["digest"] = "sha256:" + "0" * 64
    elif corruption == "merge_log":
        inputs["checkout_lines"] = [inputs["tested_checkout"]]
    else:
        inputs["checkout_lines"] = ["Merge " + inputs["run"]["head_sha"] + " into base"]
    (tmp_path / "current-gate-inputs.json").write_text(json.dumps(inputs))
    with pytest.raises(ValueError, match="current Gate"):
        reconcile.reconcile_current_archive(tmp_path / "unused.zip", tmp_path)


def test_verified_archives_bind_unique_inventory_comparison():
    import gzip

    evidence = reconcile.EVIDENCE
    comparison = json.loads((evidence / "verified-inventory-comparison.json").read_bytes())
    coverages = []
    for label, record_name in [
        ("historical", "historical-archive-reconciled"),
        ("current", "current-gate-reconciled"),
    ]:
        data = gzip.decompress((evidence / f"{label}-gate.coverage.json.gz").read_bytes())
        record = json.loads((evidence / f"{record_name}.json").read_bytes())
        assert hashlib.sha256(data).hexdigest() == record["coverage_json_sha256"]
        coverages.append(json.loads(data))
    total = 0
    for path, row in comparison["targets"].items():
        b, a = (coverage["files"][path] for coverage in coverages)
        assert row["same_target_source_ast"]
        assert row["same_executable_units_and_exclusions"]
        removed = len(set(b["missing_lines"]) - set(a["missing_lines"])) + len(
            set(map(tuple, b["missing_branches"])) - set(map(tuple, a["missing_branches"]))
        )
        assert row["unique_observed_units_removed"] == removed
        assert row["attributable_round_reduction"] is None
        total += removed
    assert comparison["unique_observed_units_removed"] == total == 33
    assert comparison["attributable_round_reduction"] is None


def _inventory(*, missing_lines=(), executed_lines=(), missing_branches=(), executed_branches=()):
    return {
        "summary": {
            "num_statements": len(missing_lines) + len(executed_lines),
            "covered_lines": len(executed_lines),
            "missing_lines": len(missing_lines),
            "num_branches": len(missing_branches) + len(executed_branches),
            "covered_branches": len(executed_branches),
            "missing_branches": len(missing_branches),
        },
        "missing_lines": list(missing_lines),
        "executed_lines": list(executed_lines),
        "missing_branches": [list(arc) for arc in missing_branches],
        "executed_branches": [list(arc) for arc in executed_branches],
    }


def test_source_mapping_tracks_shifted_lines_and_negative_function_exits():
    before = _inventory(
        missing_lines=[3], executed_lines=[1, 2], missing_branches=[(2, 3), (2, -1)]
    )
    after = _inventory(executed_lines=[2, 3, 4], executed_branches=[(3, 4), (3, -2)])
    result = compare.compare_target(
        before,
        after,
        "def f():\n    if ready:\n        return 1\n",
        "# inserted\ndef f():\n    if ready:\n        return 1\n",
    )
    assert result["lines"]["mapped"] == [[1, 2], [2, 3], [3, 4]]
    assert result["arcs"]["mapped"] == [[(2, -1), (3, -2)], [(2, 3), (3, 4)]]
    assert result["observed_newly_covered_units"] == 3
    assert result["changed_baseline_lines"] == []
    assert result["changed_final_lines"] == [1]
    assert result["attributable_round_reduction"] is None


def test_source_mapping_does_not_credit_changed_removed_or_excluded_units():
    source = "if ready:\n    run()\nfinish()\n"
    before = _inventory(missing_lines=[2, 3], missing_branches=[(1, 2), (1, 3)])
    after = _inventory(executed_lines=[2], executed_branches=[(1, 2)])
    result = compare.compare_target(before, after, source, source.replace("run()", "stop()"))
    assert result["observed_newly_covered_units"] == 0
    assert result["lines"]["unmatched_baseline_missing"] == [2, 3]
    assert result["lines"]["unmatched_final"] == [2]
    assert result["arcs"]["unmatched_baseline_missing"] == [(1, 2), (1, 3)]
    assert result["arcs"]["unmatched_final"] == [(1, 2)]
    assert result["changed_baseline_lines"] == result["changed_final_lines"] == [2]


def test_source_mapping_keeps_regressions_separate_from_gains():
    before = _inventory(
        missing_lines=[2],
        executed_lines=[1],
        missing_branches=[(1, 2)],
        executed_branches=[(1, -1)],
    )
    after = _inventory(
        executed_lines=[2],
        missing_lines=[1],
        executed_branches=[(1, 2)],
        missing_branches=[(1, -1)],
    )
    result = compare.compare_target(
        before, after, "if ready:\n    run()\n", "if ready:\n    run()\n"
    )
    assert result["observed_newly_covered_units"] == result["observed_newly_missing_units"] == 2
    assert result["lines"]["newly_missing"] == [[1, 1]]
    assert result["arcs"]["newly_missing"] == [[(1, -1), (1, -1)]]


@pytest.mark.parametrize("side", ["baseline", "final"])
@pytest.mark.parametrize(
    "field",
    [
        "num_statements",
        "covered_lines",
        "missing_lines",
        "num_branches",
        "covered_branches",
        "missing_branches",
    ],
)
@pytest.mark.parametrize("corruption", ["omitted_unit", "boolean", "float"])
def test_source_mapping_rejects_incomplete_or_mistyped_summary(side, field, corruption):
    before = _inventory(
        missing_lines=[1],
        executed_lines=[2],
        missing_branches=[(1, 2)],
        executed_branches=[(1, -1)],
    )
    after = deepcopy(before)
    summary = (before if side == "baseline" else after)["summary"]
    if corruption == "omitted_unit":
        summary[field] += 1
    elif corruption == "boolean":
        summary[field] = bool(summary[field])
    else:
        summary[field] = float(summary[field])
    with pytest.raises(ValueError, match=f"inventory disagrees with summary: {field}"):
        compare.compare_target(before, after, "if ready:\n    run()\n", "if ready:\n    run()\n")


def test_source_mapping_accounts_for_missing_units_without_crediting_removed_code():
    before_source = "if ready:\n    run()\nfinish()\ncleanup()\n"
    after_source = "if ready:\n    run()\nfinish()\nstop()\n"
    before = _inventory(
        missing_lines=[2, 4],
        executed_lines=[1, 3],
        missing_branches=[(1, 2), (1, 4)],
        executed_branches=[(1, 3)],
    )
    after = _inventory(
        missing_lines=[3],
        executed_lines=[1, 2, 4],
        missing_branches=[(1, 3)],
        executed_branches=[(1, 2), (1, 4)],
    )
    result = compare.compare_target(before, after, before_source, after_source)
    assert result["missing_unit_accounting"] == {
        "baseline_missing_units": 4,
        "final_missing_units": 2,
        "newly_covered": 2,
        "newly_missing": 2,
        "unmatched_baseline_missing": 2,
        "unmatched_final_missing": 0,
        "mapped_net_reduction": 0,
        "unmatched_net_difference": 2,
        "snapshot_difference": 2,
    }
    assert result["attributable_round_reduction"] is None

    reverse = compare.compare_target(after, before, after_source, before_source)
    counts = reverse["missing_unit_accounting"]
    assert counts["unmatched_final_missing"] == 2
    assert counts["snapshot_difference"] == -2
    assert counts["snapshot_difference"] == (
        counts["mapped_net_reduction"] + counts["unmatched_net_difference"]
    )


def test_source_mapping_accepts_complete_retained_gate_inventories():
    import gzip

    for label in ("historical", "current"):
        coverage = json.loads(
            gzip.decompress((reconcile.EVIDENCE / f"{label}-gate.coverage.json.gz").read_bytes())
        )
        for path in reconcile.TARGETS:
            lines, arcs, missing_lines, missing_arcs = compare._units(coverage["files"][path])
            summary = coverage["files"][path]["summary"]
            assert len(lines) + len(arcs) == summary["num_statements"] + summary["num_branches"]
            assert len(missing_lines) + len(missing_arcs) == (
                summary["missing_lines"] + summary["missing_branches"]
            )


@pytest.mark.parametrize("side", ["baseline", "final"])
@pytest.mark.parametrize(
    "corruption", ["duplicate", "boolean", "overlap", "out_of_bounds", "exit_out_of_bounds"]
)
def test_source_mapping_rejects_invalid_units(side, corruption):
    before, after = _inventory(), _inventory()
    row = before if side == "baseline" else after
    if corruption == "duplicate":
        row["executed_branches"] = [[1, -1], [1, -1]]
    elif corruption == "boolean":
        row["executed_lines"] = [True]
    elif corruption == "overlap":
        row["missing_lines"] = row["executed_lines"] = [1]
    elif corruption == "out_of_bounds":
        row.update(_inventory(missing_lines=[2]))
    else:
        row.update(_inventory(missing_branches=[(1, -2)]))
    with pytest.raises(ValueError, match="invalid|overlap|source length"):
        compare.compare_target(before, after, "run()\n", "run()\n")


def test_six_target_comparison_binds_digests_but_does_not_claim_tested_checkout(
    tmp_path, monkeypatch, capsys
):
    import gzip
    from types import SimpleNamespace

    baseline, final = "a" * 40, "b" * 40
    ranking = tmp_path / "ranking.json"
    ranking.write_text(json.dumps({"historical_issue_order": list(reversed(reconcile.TARGETS))}))
    coverages = []
    for name, row in (
        ("before", _inventory(missing_lines=[1])),
        ("after", _inventory(executed_lines=[2])),
    ):
        data = json.dumps(
            {"meta": {"branch_coverage": True}, "files": dict.fromkeys(reconcile.TARGETS, row)}
        ).encode()
        path = tmp_path / name
        path.write_bytes(data if name == "before" else gzip.compress(data))
        coverages.append((path, hashlib.sha256(data).hexdigest()))

    def git(command, **kwargs):
        assert command[:3] == ["git", "-C", str(tmp_path)]
        assert kwargs == {"check": True, "capture_output": True}
        if command[3] == "rev-parse":
            return SimpleNamespace(stdout=(command[-1].removesuffix("^{commit}") + "\n").encode())
        assert command[3] == "show"
        revision, path = command[-1].split(":")
        assert path in reconcile.TARGETS
        return SimpleNamespace(
            stdout=b"run()\n" if revision == baseline else b"# inserted\nrun()\n"
        )

    monkeypatch.setattr(compare.subprocess, "run", git)
    argv = [
        str(coverages[0][0]),
        str(coverages[1][0]),
        "--baseline-checkout",
        baseline,
        "--final-checkout",
        final,
        "--repository",
        str(tmp_path),
        "--ranking",
        str(ranking),
    ]
    assert compare.main(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert list(result["targets"]) == list(reversed(reconcile.TARGETS))
    assert result["source_checkouts"] == {"baseline": baseline, "final": final}
    assert result["coverage_json_sha256"] == {"baseline": coverages[0][1], "final": coverages[1][1]}
    assert all(row["observed_newly_covered_units"] == 1 for row in result["targets"].values())
    assert result["tested_checkout_binding_verified"] is False
    assert result["execution_configuration_verified"] is False
    assert result["attributable_round_reduction"] is None

    unbranched = json.loads(coverages[0][0].read_text())
    unbranched["meta"]["branch_coverage"] = False
    coverages[0][0].write_text(json.dumps(unbranched))
    with pytest.raises(SystemExit) as error:
        compare.main(argv)
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "branch coverage is required" in output.err

    ranking.write_text(json.dumps({"historical_issue_order": list(reconcile.TARGETS[:-1])}))
    with pytest.raises(SystemExit) as error:
        compare.main(argv)
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "exactly the six selected targets" in output.err


@pytest.mark.parametrize("compressed", [False, True])
def test_source_comparison_bounds_plain_and_expanded_coverage(tmp_path, monkeypatch, compressed):
    import gzip
    from types import SimpleNamespace

    data = b" " * 1001
    coverage = tmp_path / "coverage.json"
    coverage.write_bytes(gzip.compress(data) if compressed else data)
    monkeypatch.setattr(compare, "MAX_BYTES", 1000)
    monkeypatch.setattr(
        compare.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=b"a" * 40)
    )
    with pytest.raises(ValueError, match="coverage.json exceeds byte limit"):
        compare.compare_checkouts(
            tmp_path, "HEAD", "HEAD", coverage, coverage, reconcile.EVIDENCE / "ranking.json"
        )
