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


def test_extract_coverage_percent_defaults() -> None:
    assert coverage_trend._extract_coverage_percent({}) == 0.0
    assert coverage_trend._extract_coverage_percent({"totals": {}}) == 0.0


def test_get_hotspots_handles_missing_fields() -> None:
    coverage_json = {
        "files": {
            "src/a.py": {"summary": {"percent_covered": 20.0, "missing_lines": 10}},
            "src/b.py": {"summary": {"percent_covered": 80.0, "missing_lines": 1}},
            "src/c.py": {"summary": {}},
        }
    }

    hotspots, low_coverage = coverage_trend._get_hotspots(
        coverage_json, limit=2, low_threshold=50.0
    )

    assert [spot["file"] for spot in hotspots] == ["src/c.py", "src/a.py"]
    assert [spot["file"] for spot in low_coverage] == ["src/c.py", "src/a.py"]


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

    hotspots, low_coverage = coverage_trend._get_hotspots(
        coverage_json, limit=2, low_threshold=50.0
    )

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
    assert trend["passes_minimum"] is True

    summary = summary_path.read_text(encoding="utf-8")
    assert "Coverage Trend" in summary
    assert "75.50%" in summary

    job_summary_text = job_summary.read_text(encoding="utf-8")
    assert "Before" in job_summary_text
    assert "Coverage Trend" in job_summary_text

    output_text = github_output.read_text(encoding="utf-8")
    assert "coverage=75.50" in output_text
    assert "baseline=70.00" in output_text
    assert "passes_minimum=true" in output_text


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
    assert trend["passes_minimum"] is False


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
    assert "Top Coverage Hotspots" in summary
    assert "Low Coverage Files" in summary

    trend = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert len(trend["hotspots"]) == 2
    assert len(trend["low_coverage_files"]) == 1

    output_text = github_output.read_text(encoding="utf-8")
    assert "hotspot_count=2" in output_text
    assert "low_coverage_count=1" in output_text
