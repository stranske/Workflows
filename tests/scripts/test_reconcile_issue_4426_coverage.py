"""Exercise offline artifact ingestion with explicitly synthetic ZIP bytes.

The real artifact remains inaccessible. These fixtures test the reconciler;
they must never be recorded as downloaded Gate evidence or attribution.
"""

from __future__ import annotations

import hashlib
import json
import re
import warnings
import zipfile

import pytest
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
