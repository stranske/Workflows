"""Exercise the recovered Gate extractor and replay the complete retained reports."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXTRACTOR = ROOT / "docs/evidence/issue-4001/extract_target_coverage.py"
EVIDENCE = ROOT / "docs/evidence/issue-4502"
spec = importlib.util.spec_from_file_location("target_coverage", EXTRACTOR)
assert spec is not None and spec.loader is not None
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


@pytest.fixture
def reports(tmp_path):
    files = {
        target: {"summary": {"missing_lines": 1, "missing_branches": 2, "percent_covered": 25}}
        for target in extractor.TARGETS
    }
    classes = [
        f'<class filename="{target}"><lines><line number="1" hits="1" />'
        '<line number="2" hits="0" branch="true" '
        'condition-coverage="0% (0/2)" /></lines></class>'
        for target in extractor.TARGETS
    ]
    json_path = tmp_path / "coverage.json"
    json_path.write_text(json.dumps({"files": files}), encoding="utf-8")
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text("<coverage>" + "".join(classes) + "</coverage>", encoding="utf-8")
    return json_path, xml_path


def cli(*args):
    return subprocess.run(
        [sys.executable, str(EXTRACTOR), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("compress_json", [False, True])
@pytest.mark.parametrize("compress_xml", [False, True])
def test_cli_reproduces_counts_from_plain_or_compressed_reports(
    reports, compress_json, compress_xml
):
    paths = []
    for path, compress in zip(reports, (compress_json, compress_xml), strict=True):
        if compress:
            compressed = path.with_suffix(path.suffix + ".gz")
            compressed.write_bytes(gzip.compress(path.read_bytes()))
            path = compressed
        paths.append(path)
    result = cli(paths[0], "--xml", paths[1])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        target: {"missing_lines": 1, "missing_branches": 2, "percent_covered": 25.0}
        for target in extractor.TARGETS
    }
    assert result.stderr == "combined_missing_units=9\n"


def test_original_json_only_cli_remains_supported(reports):
    result = cli(reports[0])
    assert result.returncode == 0
    assert result.stderr == "combined_missing_units=9\n"
    assert set(json.loads(result.stdout)) == set(extractor.TARGETS)


@pytest.mark.parametrize("limit,expected_status", [(0, 1), (8, 1), (9, 0), (10, 0)])
def test_cli_enforces_inclusive_missing_unit_budget(reports, limit, expected_status):
    json_path, xml_path = reports
    result = cli(json_path, "--xml", xml_path, "--max-missing", limit)
    assert result.returncode == expected_status, result.stderr
    assert json.loads(result.stdout) == {
        target: {"missing_lines": 1, "missing_branches": 2, "percent_covered": 25.0}
        for target in extractor.TARGETS
    }
    expected_error = "combined_missing_units=9\n"
    if expected_status:
        expected_error += f"coverage budget exceeded: 9 > {limit}\n"
    assert result.stderr == expected_error


@pytest.mark.parametrize("limit", ["-1", "1.5", "unbounded"])
def test_cli_rejects_invalid_missing_unit_budget(reports, limit):
    result = cli(reports[0], "--max-missing", limit)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "--max-missing" in result.stderr
    assert "combined_missing_units" not in result.stderr


def test_budget_does_not_accept_inconsistent_report_pair(reports):
    json_path, xml_path = reports
    xml_path.write_text(xml_path.read_text().replace("(0/2)", "(1/2)"))
    result = cli(json_path, "--xml", xml_path, "--max-missing", 46)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "XML missing counts (1, 1) differ from JSON (1, 2)" in result.stderr
    assert "combined_missing_units" not in result.stderr


@pytest.mark.parametrize("limit", [0, 46])
def test_retained_gate_replay_meets_missing_unit_budget(limit):
    phase = EVIDENCE / "replay-after"
    result = cli(
        phase / "coverage.json.gz",
        "--xml",
        phase / "coverage.xml.gz",
        "--max-missing",
        limit,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        target: {"missing_lines": 0, "missing_branches": 0, "percent_covered": 100.0}
        for target in extractor.TARGETS
    }
    assert result.stderr == "combined_missing_units=0\n"


@pytest.mark.parametrize("prefix", ["", "/checkout/", "C:\\checkout\\"])
def test_json_target_resolution_accepts_platform_paths(reports, prefix):
    path, _ = reports
    data = json.loads(path.read_text())
    data["files"] = {prefix + key: value for key, value in data["files"].items()}
    path.write_text(json.dumps(data))
    assert extractor.load_file_stats(path)[extractor.TARGETS[0]]["missing_branches"] == 2


@pytest.mark.parametrize("count", ["missing_lines", "missing_branches"])
@pytest.mark.parametrize("value", [None, True, -1, 1.5, "2"])
def test_json_rejects_missing_or_invalid_counts(reports, count, value):
    path, _ = reports
    data = json.loads(path.read_text())
    data["files"][extractor.TARGETS[0]]["summary"][count] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=f"{count} must be a nonnegative integer"):
        extractor.load_file_stats(path)


@pytest.mark.parametrize("value", [None, True, -1, 101, float("nan"), float("inf")])
def test_json_rejects_invalid_percentages(reports, value):
    path, _ = reports
    data = json.loads(path.read_text())
    data["files"][extractor.TARGETS[0]]["summary"]["percent_covered"] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="percent_covered must be between 0 and 100"):
        extractor.load_file_stats(path)


@pytest.mark.parametrize("payload", [[], {"files": []}, {"files": {}}])
def test_cli_rejects_incomplete_json_without_publishing_a_total(reports, payload):
    path, _ = reports
    path.write_text(json.dumps(payload))
    result = cli(path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("invalid coverage: ")
    assert "combined_missing_units" not in result.stderr


@pytest.mark.parametrize("duplicate", [False, True])
def test_json_rejects_absent_or_duplicate_targets(reports, duplicate):
    path, _ = reports
    data = json.loads(path.read_text())
    target = extractor.TARGETS[0]
    if duplicate:
        data["files"]["/other/" + target] = data["files"][target]
    else:
        del data["files"][target]
    path.write_text(json.dumps(data))
    with pytest.raises(
        ValueError, match=f"expected exactly one target, found {2 if duplicate else 0}"
    ):
        extractor.load_file_stats(path)


@pytest.mark.parametrize("replacement", ['hits="1"', 'hits="0"'])
def test_cli_rejects_json_xml_disagreement(reports, replacement):
    json_path, xml_path = reports
    xml_path.write_text(
        xml_path.read_text().replace('hits="0"', replacement).replace("(0/2)", "(1/2)")
    )
    result = cli(json_path, "--xml", xml_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "XML missing counts" in result.stderr
    assert "differ from JSON (1, 2)" in result.stderr


@pytest.mark.parametrize(
    ("original", "replacement", "diagnostic"),
    [
        ('hits="1"', 'hits="-1"', "invalid XML hits"),
        ('hits="1"', 'hits="bad"', "invalid XML hits"),
        ('condition-coverage="0% (0/2)"', "", "invalid XML condition-coverage"),
        ("0% (0/2)", "(0/2)", "invalid XML condition-coverage"),
        ("0% (0/2)", "150% (3/2)", "invalid XML branch counts"),
        ("0% (0/2)", "0% (0/0)", "invalid XML branch counts"),
    ],
)
def test_xml_rejects_invalid_counters(reports, original, replacement, diagnostic):
    json_path, xml_path = reports
    xml_path.write_text(xml_path.read_text().replace(original, replacement))
    with pytest.raises(ValueError, match=diagnostic):
        extractor.check_xml_counts(xml_path, extractor.load_file_stats(json_path))


@pytest.mark.parametrize("classes", ["", '<class filename="aggregate_agent_metrics.py"/>'])
def test_xml_rejects_missing_targets_or_statements(reports, classes):
    json_path, xml_path = reports
    xml_path.write_text(f"<coverage>{classes}</coverage>")
    with pytest.raises(
        ValueError, match="expected exactly one XML target|XML target has no statements"
    ):
        extractor.check_xml_counts(xml_path, extractor.load_file_stats(json_path))


@pytest.mark.parametrize(
    "corrupt", [b"<coverage>", b'<!DOCTYPE x [<!ENTITY e "x">]><coverage>&e;</coverage>']
)
def test_cli_rejects_malformed_or_unsafe_xml(reports, corrupt):
    json_path, xml_path = reports
    xml_path.write_bytes(corrupt)
    result = cli(json_path, "--xml", xml_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("invalid coverage: ")


@pytest.mark.parametrize(
    "phase,expected_total",
    [("target-before", 21), ("target-after", 0), ("gate-before", 2), ("gate-after", 0)],
)
def test_retained_complete_reports_reproduce_both_measurements(phase, expected_total):
    result = cli(
        EVIDENCE / phase / "coverage.json.gz", "--xml", EVIDENCE / phase / "coverage.xml.gz"
    )
    assert result.returncode == 0, result.stderr
    stats = json.loads(result.stdout)
    inventory = json.loads((EVIDENCE / phase / "inventory.json").read_text())
    assert stats == {
        target: {key: inventory[target]["summary"][key] for key in stats[target]}
        for target in extractor.TARGETS
    }
    assert result.stderr == f"combined_missing_units={expected_total}\n"


def test_retained_reports_match_compressed_and_complete_file_digests():
    manifest = json.loads((EVIDENCE / "artifact-manifest.json").read_text())
    reports = [
        entry
        for entry in manifest["artifacts"]
        if entry["path"].endswith(("coverage.json.gz", "coverage.xml.gz"))
    ]
    assert len(reports) == 8
    for entry in reports:
        compressed = (EVIDENCE / entry["path"]).read_bytes()
        complete = gzip.decompress(compressed)
        assert hashlib.sha256(compressed).hexdigest() == entry["gzip_sha256"]
        assert hashlib.sha256(complete).hexdigest() == entry["sha256"]
        assert len(complete) == entry["uncompressed_bytes"]
