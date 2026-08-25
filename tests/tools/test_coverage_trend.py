import json
from pathlib import Path

from tools import coverage_trend


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_json_returns_empty_on_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert coverage_trend._load_json(missing) == {}

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json}", encoding="utf-8")
    assert coverage_trend._load_json(invalid) == {}


def test_load_json_returns_empty_for_non_dict(tmp_path: Path) -> None:
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

    assert coverage_trend._load_json(path) == {}


def test_load_json_returns_dict_payload(tmp_path: Path) -> None:
    path = tmp_path / "payload.json"
    payload = {"coverage": 91.25, "metadata": {"source": "unit-test"}}
    _write_json(path, payload)

    assert coverage_trend._load_json(path) == payload


def test_extract_coverage_percent_defaults() -> None:
    assert coverage_trend._extract_coverage_percent({}) == 0.0
    assert coverage_trend._extract_coverage_percent({"totals": {}}) == 0.0


def test_extract_coverage_percent_reads_coverage_total() -> None:
    assert (
        coverage_trend._extract_coverage_percent({"totals": {"percent_covered": "87.654"}})
        == 87.654
    )


def test_get_hotspots_handles_missing_fields() -> None:
    coverage_json = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 20.0,
                    "missing_lines": 10,
                    "covered_lines": 3,
                }
            },
            "src/b.py": {"summary": {"percent_covered": 80.0, "missing_lines": 1}},
            "src/c.py": {"summary": {}},
        }
    }

    hotspots, low_coverage, foreign = coverage_trend._get_hotspots(
        coverage_json, limit=2, low_threshold=50.0
    )

    assert foreign == []
    assert [spot["file"] for spot in hotspots] == ["src/c.py", "src/a.py"]
    assert [spot["file"] for spot in low_coverage] == ["src/c.py", "src/a.py"]
    assert hotspots[0]["covered_lines"] == 0
    assert hotspots[1]["covered_lines"] == 3


def test_format_hotspot_table_handles_empty() -> None:
    assert coverage_trend._format_hotspot_table([], "Empty") == ""


def test_format_hotspot_table_formats_rows() -> None:
    table = coverage_trend._format_hotspot_table(
        [{"file": "src/app.py", "coverage": 12.345, "missing_lines": 7}], "Hotspots"
    )

    assert "### Hotspots" in table
    assert "| `src/app.py` | 12.3% | 7 |" in table


def test_get_hotspots_applies_limits_and_threshold() -> None:
    coverage_json = {
        "files": {
            "src/low.py": {"summary": {"percent_covered": 10.0, "missing_lines": 9}},
            "src/mid.py": {"summary": {"percent_covered": 55.0, "missing_lines": 4}},
            "src/high.py": {"summary": {"percent_covered": 90.0, "missing_lines": 1}},
        }
    }

    hotspots, low_coverage, foreign = coverage_trend._get_hotspots(
        coverage_json, limit=2, low_threshold=50.0
    )

    assert foreign == []
    assert [spot["file"] for spot in hotspots] == ["src/low.py", "src/mid.py"]
    assert [spot["file"] for spot in low_coverage] == ["src/low.py"]


def test_main_handles_missing_coverage_json(tmp_path: Path) -> None:
    missing_coverage = tmp_path / "missing.json"
    baseline_json = tmp_path / "baseline.json"
    summary_path = tmp_path / "summary.md"
    github_output = tmp_path / "github_output.txt"

    _write_json(baseline_json, {"coverage": 12.0})

    exit_code = coverage_trend.main(
        [
            "--coverage-json",
            str(missing_coverage),
            "--baseline",
            str(baseline_json),
            "--summary-path",
            str(summary_path),
            "--github-output",
            str(github_output),
            "--minimum",
            "70",
        ]
    )

    assert exit_code == 1
    summary = summary_path.read_text(encoding="utf-8")
    assert "0.00%" in summary
    output_text = github_output.read_text(encoding="utf-8")
    assert "coverage=0.00" in output_text


def test_main_handles_missing_baseline_and_empty_hotspots(tmp_path: Path) -> None:
    """An ABSENT baseline must read as absent, not as the number zero.

    This test previously asserted `Baseline | 0.00%` and `baseline=0.00`, which is why the defect
    survived: the behaviour was not merely unnoticed, it was PINNED as correct. A missing file and
    a real baseline of zero rendered identically, so a repo with no `config/coverage-baseline.json`
    -- ten of the thirteen lane repos, as of 2026-08-24 -- got a delta measured against nothing,
    printed as a large improvement, on every single run.
    """
    coverage_json = tmp_path / "coverage.json"
    baseline_json = tmp_path / "baseline.json"
    summary_path = tmp_path / "summary.md"
    github_output = tmp_path / "github_output.txt"

    _write_json(coverage_json, {"totals": {"percent_covered": 72.0}})

    exit_code = coverage_trend.main(
        [
            "--coverage-json",
            str(coverage_json),
            "--baseline",
            str(baseline_json),
            "--summary-path",
            str(summary_path),
            "--github-output",
            str(github_output),
            "--minimum",
            "70",
        ]
    )

    assert exit_code == 0
    summary = summary_path.read_text(encoding="utf-8")
    assert "not configured (absent)" in summary
    assert "Baseline | 0.00%" not in summary
    assert "n/a — nothing to compare against" in summary
    assert "Top Coverage Hotspots" not in summary
    assert "Low Coverage Files" not in summary

    output_text = github_output.read_text(encoding="utf-8")
    # Empty, so a reader testing `-n "$baseline"` can tell "no baseline" from a measured 0.00.
    assert "baseline=\n" in output_text
    assert "baseline_status=absent\n" in output_text
    assert "delta=\n" in output_text
    assert "hotspot_count=0" in output_text
    assert "low_coverage_count=0" in output_text


def test_main_writes_outputs_and_passes(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    baseline_json = tmp_path / "baseline.json"
    summary_path = tmp_path / "summary.md"
    job_summary = tmp_path / "job_summary.md"
    artifact_path = tmp_path / "trend.json"
    github_output = tmp_path / "github_output.txt"

    _write_json(coverage_json, {"totals": {"percent_covered": 75.5}})
    _write_json(baseline_json, {"coverage": 70.0})
    job_summary.write_text("Before\n", encoding="utf-8")

    exit_code = coverage_trend.main(
        [
            "--coverage-json",
            str(coverage_json),
            "--baseline",
            str(baseline_json),
            "--summary-path",
            str(summary_path),
            "--job-summary",
            str(job_summary),
            "--artifact-path",
            str(artifact_path),
            "--github-output",
            str(github_output),
            "--minimum",
            "70",
        ]
    )

    assert exit_code == 0
    trend = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert trend["current"] == 75.5
    assert trend["baseline"] == 70.0
    assert trend["delta"] == 5.5
    assert trend["minimum"] == 70.0
    assert trend["passes_minimum"] is True
    assert trend["hotspots"] == []
    assert trend["low_coverage_files"] == []

    summary = summary_path.read_text(encoding="utf-8")
    assert "Coverage Trend" in summary
    assert "| Current | 75.50% |" in summary
    assert "| Delta | +5.50% |" in summary
    assert "| Status |" in summary
    assert "Pass |" in summary

    job_summary_text = job_summary.read_text(encoding="utf-8")
    assert job_summary_text.startswith("Before\n")
    assert "## Coverage Trend" in job_summary_text

    output_text = github_output.read_text(encoding="utf-8")
    assert "coverage=75.50" in output_text
    assert "baseline=70.00" in output_text
    assert "delta=5.50" in output_text
    assert "passes_minimum=true" in output_text
    assert "hotspot_count=0" in output_text
    assert "low_coverage_count=0" in output_text


def test_main_fails_below_minimum(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    artifact_path = tmp_path / "trend.json"

    _write_json(coverage_json, {"totals": {"percent_covered": 60.0}})

    exit_code = coverage_trend.main(
        [
            "--coverage-json",
            str(coverage_json),
            "--artifact-path",
            str(artifact_path),
            "--minimum",
            "65",
        ]
    )

    assert exit_code == 1
    trend = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert trend["current"] == 60.0
    assert trend["minimum"] == 65.0
    assert trend["passes_minimum"] is False


def test_main_respects_hotspot_limit(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    artifact_path = tmp_path / "trend.json"

    _write_json(
        coverage_json,
        {
            "totals": {"percent_covered": 72.0},
            "files": {
                "src/low.py": {"summary": {"percent_covered": 10.0, "missing_lines": 9}},
                "src/mid.py": {"summary": {"percent_covered": 20.0, "missing_lines": 5}},
                "src/high.py": {"summary": {"percent_covered": 30.0, "missing_lines": 3}},
            },
        },
    )

    exit_code = coverage_trend.main(
        [
            "--coverage-json",
            str(coverage_json),
            "--artifact-path",
            str(artifact_path),
            "--hotspot-limit",
            "1",
            "--low-threshold",
            "50",
            "--minimum",
            "0",
        ]
    )

    assert exit_code == 0
    trend = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert trend["hotspot_count"] == 1
    assert trend["low_coverage_count"] == 1
    assert trend["hotspots"][0]["file"] == "src/low.py"


def test_main_soft_mode_reports_without_failing(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    artifact_path = tmp_path / "trend.json"

    _write_json(
        coverage_json,
        {
            "totals": {"percent_covered": 40.0},
            "files": {"src/app.py": {"summary": {"percent_covered": 40.0, "missing_lines": 5}}},
        },
    )

    exit_code = coverage_trend.main(
        [
            "--coverage-json",
            str(coverage_json),
            "--artifact-path",
            str(artifact_path),
            "--minimum",
            "65",
            "--soft",
        ]
    )

    assert exit_code == 0
    trend = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert trend["passes_minimum"] is False
    assert trend["hotspot_count"] == 1
    assert trend["low_coverage_count"] == 1


def test_main_handles_invalid_coverage_json(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    summary_path = tmp_path / "summary.md"
    job_summary = tmp_path / "job_summary.md"

    coverage_json.write_text("{not-json}", encoding="utf-8")

    exit_code = coverage_trend.main(
        [
            "--coverage-json",
            str(coverage_json),
            "--summary-path",
            str(summary_path),
            "--job-summary",
            str(job_summary),
            "--minimum",
            "70",
        ]
    )

    assert exit_code == 1
    summary = summary_path.read_text(encoding="utf-8")
    assert "Top Coverage Hotspots" not in summary
    assert "Low Coverage Files" not in summary
    assert not job_summary.exists()


def test_main_includes_hotspot_tables_and_counts(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    baseline_json = tmp_path / "baseline.json"
    summary_path = tmp_path / "summary.md"
    artifact_path = tmp_path / "trend.json"
    github_output = tmp_path / "github_output.txt"

    _write_json(
        coverage_json,
        {
            "totals": {"percent_covered": 88.0},
            "files": {
                "src/low.py": {"summary": {"percent_covered": 10.0, "missing_lines": 9}},
                "src/high.py": {"summary": {"percent_covered": 95.0, "missing_lines": 1}},
            },
        },
    )
    _write_json(baseline_json, {"coverage": 85.0})

    exit_code = coverage_trend.main(
        [
            "--coverage-json",
            str(coverage_json),
            "--baseline",
            str(baseline_json),
            "--summary-path",
            str(summary_path),
            "--artifact-path",
            str(artifact_path),
            "--github-output",
            str(github_output),
            "--minimum",
            "70",
            "--low-threshold",
            "50",
        ]
    )

    assert exit_code == 0
    summary = summary_path.read_text(encoding="utf-8")
    assert "| Current | 88.00% |" in summary
    assert "| Baseline | 85.00% |" in summary
    assert "| Delta | +3.00% |" in summary
    assert "Top Coverage Hotspots" in summary
    assert "Low Coverage Files" in summary
    assert "| `src/low.py` | 10.0% | 9 |" in summary

    trend = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert trend["current"] == 88.0
    assert trend["baseline"] == 85.0
    assert trend["delta"] == 3.0
    assert trend["minimum"] == 70.0
    assert trend["passes_minimum"] is True
    assert len(trend["hotspots"]) == 2
    assert len(trend["low_coverage_files"]) == 1
    assert trend["hotspots"][0] == {
        "file": "src/low.py",
        "coverage": 10.0,
        "missing_lines": 9,
        "covered_lines": 0,
    }

    output_text = github_output.read_text(encoding="utf-8")
    assert "coverage=88.00" in output_text
    assert "baseline=85.00" in output_text
    assert "delta=3.00" in output_text
    assert "passes_minimum=true" in output_text
    assert "hotspot_count=2" in output_text
    assert "low_coverage_count=1" in output_text


# ---------------------------------------------------------------------------------------------
# Baseline resolution. The live defect these cover, measured 2026-08-24: stranske/Trend_Model_Project
# ships `config/coverage-baseline.json` = {"line": 85.0} and its Gate reported
# `Baseline 0.00% | Delta +83.32% | Status ✅ Pass` on a real coverage of 83.32% -- which against
# the configured 85.0 is a BREACH. `tools/coverage_guard.py`, reading the same file, has always
# accepted both keys; this script accepted only "coverage", and the two never disagreed out loud.
# ---------------------------------------------------------------------------------------------


def test_resolve_baseline_accepts_both_key_spellings(tmp_path: Path) -> None:
    line_keyed = tmp_path / "line.json"
    _write_json(line_keyed, {"line": 85.0, "warn_drop": 1.0})
    assert coverage_trend._resolve_baseline(line_keyed) == (85.0, "ok")

    coverage_keyed = tmp_path / "coverage.json"
    _write_json(coverage_keyed, {"coverage": 80.0})
    assert coverage_trend._resolve_baseline(coverage_keyed) == (80.0, "ok")


def test_resolve_baseline_prefers_line_when_both_present(tmp_path: Path) -> None:
    """`line` wins, matching coverage_guard's `payload.get("line", payload.get("coverage"))`.

    Two scripts reading one config must agree about precedence, or the guard and the trend can
    report different baselines from the same file and both look right.
    """
    path = tmp_path / "both.json"
    _write_json(path, {"line": 85.0, "coverage": 70.0})
    assert coverage_trend._resolve_baseline(path) == (85.0, "ok")


def test_resolve_baseline_distinguishes_its_four_not_configured_causes(tmp_path: Path) -> None:
    """Never one sentinel for two meanings — each cause names a DIFFERENT fix.

    `absent` means write the file; `no_recognised_key` means the file is there and this script
    cannot read it; `unreadable` means it is corrupt. Collapsing them to 0.0 turned every one of
    them into "the baseline is zero", which is the only reading that is good news.
    """
    assert coverage_trend._resolve_baseline(None) == (None, "unset")
    assert coverage_trend._resolve_baseline(tmp_path / "nope.json") == (None, "absent")

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not-json}", encoding="utf-8")
    assert coverage_trend._resolve_baseline(corrupt) == (None, "unreadable")

    wrong_key = tmp_path / "wrong.json"
    _write_json(wrong_key, {"threshold": 85.0})
    assert coverage_trend._resolve_baseline(wrong_key) == (None, "no_recognised_key")

    non_numeric = tmp_path / "non_numeric.json"
    _write_json(non_numeric, {"line": "eighty-five"})
    assert coverage_trend._resolve_baseline(non_numeric) == (None, "unreadable")


def test_line_keyed_baseline_reaches_the_record_and_can_report_a_breach(tmp_path: Path) -> None:
    """The Trend_Model_Project case end to end: 83.32% against a `line` baseline of 85.0."""
    coverage_json = tmp_path / "coverage.json"
    baseline_json = tmp_path / "baseline.json"
    artifact_path = tmp_path / "trend.json"
    summary_path = tmp_path / "summary.md"

    _write_json(coverage_json, {"totals": {"percent_covered": 83.32}})
    _write_json(baseline_json, {"line": 85.0, "warn_drop": 1.0, "recovery_days": 3})

    coverage_trend.main(
        [
            "--coverage-json",
            str(coverage_json),
            "--baseline",
            str(baseline_json),
            "--artifact-path",
            str(artifact_path),
            "--summary-path",
            str(summary_path),
            "--minimum",
            "80",
            "--soft",
        ]
    )

    record = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert record["baseline"] == 85.0
    assert record["baseline_status"] == "ok"
    assert record["delta"] < 0, "83.32 against a baseline of 85.0 is a regression, not +83.32"
    assert "Baseline | 85.00%" in summary_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Contamination. Also measured on Trend_Model_Project 2026-08-24: 13 of the 15 reported worst
# files were `/tmp/pytest-of-runner/.../test_autofix_pipeline_repairs_0/workspace/src/...`, a copy
# of the tree made by a test fixture. Those modules are counted twice and the hotspot table -- the
# only actionable output -- pointed at paths that do not exist in the repository.
# ---------------------------------------------------------------------------------------------


def _contaminated_coverage() -> dict:
    return {
        "files": {
            "src/real.py": {
                "summary": {"percent_covered": 90.0, "missing_lines": 1, "covered_lines": 9}
            },
            "/tmp/pytest-of-runner/pytest-0/ws/src/real.py": {
                "summary": {"percent_covered": 10.0, "missing_lines": 9, "covered_lines": 1}
            },
        }
    }


def test_foreign_rows_are_excluded_from_hotspots_and_reported(tmp_path: Path) -> None:
    hotspots, low_coverage, foreign = coverage_trend._get_hotspots(
        _contaminated_coverage(), limit=15, low_threshold=50.0, project_root=tmp_path
    )

    assert [spot["file"] for spot in hotspots] == ["src/real.py"]
    assert low_coverage == []
    assert foreign == ["/tmp/pytest-of-runner/pytest-0/ws/src/real.py"]


def test_foreign_rows_are_kept_when_no_project_root_is_given() -> None:
    """Default stays permissive: filtering is opt-in, so no existing caller changes behaviour."""
    hotspots, _low, foreign = coverage_trend._get_hotspots(_contaminated_coverage(), limit=15)

    assert foreign == []
    assert len(hotspots) == 2


def test_contamination_is_named_in_the_summary_with_a_project_only_number(tmp_path: Path) -> None:
    """Reported, never silently corrected: `current` still agrees with coverage.xml.

    Quietly recomputing the headline number would make this artifact disagree with the delta job
    and with coverage.xml for reasons no reader could see. The project-only figure sits beside it
    and the gap between the two IS the size of the problem.
    """
    coverage_json = tmp_path / "coverage.json"
    artifact_path = tmp_path / "trend.json"
    summary_path = tmp_path / "summary.md"
    payload = _contaminated_coverage()
    payload["totals"] = {"percent_covered": 50.0}
    _write_json(coverage_json, payload)

    coverage_trend.main(
        [
            "--coverage-json",
            str(coverage_json),
            "--artifact-path",
            str(artifact_path),
            "--summary-path",
            str(summary_path),
            "--project-root",
            str(tmp_path),
            "--soft",
        ]
    )

    record = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert (
        record["current"] == 50.0
    ), "the headline number is left exactly as coverage.py computed it"
    assert record["foreign_file_count"] == 1
    assert record["foreign_files"] == ["/tmp/pytest-of-runner/pytest-0/ws/src/real.py"]
    assert record["current_project_only"] == 90.0

    summary = summary_path.read_text(encoding="utf-8")
    assert "measured OUTSIDE the project root" in summary
    assert "90.00%" in summary
    assert "omit" in summary, "the message must name the fix, not just the symptom"


def test_every_row_foreign_is_reported_as_a_wrong_root_not_as_contamination(
    tmp_path: Path,
) -> None:
    """Two causes, two messages: a real fixture copy leaves the genuine rows behind.

    If EVERY row is foreign, the reporter is looking at the wrong directory — telling the reader
    to add an `omit` entry would send them to fix a file that is not the problem.
    """
    coverage_json = tmp_path / "coverage.json"
    summary_path = tmp_path / "summary.md"
    _write_json(
        coverage_json,
        {
            "totals": {"percent_covered": 50.0},
            "files": {
                "/elsewhere/a.py": {
                    "summary": {"percent_covered": 10.0, "missing_lines": 9, "covered_lines": 1}
                }
            },
        },
    )

    coverage_trend.main(
        [
            "--coverage-json",
            str(coverage_json),
            "--summary-path",
            str(summary_path),
            "--project-root",
            str(tmp_path / "project"),
            "--soft",
        ]
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert "wrong `--project-root`" in summary
    assert "omit" not in summary, "must not send the reader to fix coverage config"
