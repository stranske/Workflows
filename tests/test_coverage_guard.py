import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import coverage_guard


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_find_or_create_issue_updates_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["gh", "issue", "list"]:
            stdout = json.dumps([{"number": 123, "title": "coverage breach"}])
            return SimpleNamespace(stdout=stdout)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("subprocess.run", fake_run)

    coverage_guard._find_or_create_issue(
        repo="octo/repo",
        title="[coverage] baseline breach",
        body="body",
        labels=["coverage", "automated"],
    )

    assert any(call[0][:3] == ["gh", "issue", "list"] for call in calls)
    assert any(call[0][:3] == ["gh", "issue", "edit"] for call in calls)
    assert not any(call[0][:3] == ["gh", "issue", "create"] for call in calls)


def test_find_or_create_issue_creates_new(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(stdout="")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("subprocess.run", fake_run)

    coverage_guard._find_or_create_issue(
        repo="octo/repo",
        title="[coverage] baseline breach",
        body="body",
        labels=["coverage", "automated"],
    )

    assert any(call[0][:3] == ["gh", "issue", "list"] for call in calls)
    assert any(call[0][:3] == ["gh", "issue", "create"] for call in calls)
    assert not any(call[0][:3] == ["gh", "issue", "edit"] for call in calls)


def test_main_invokes_issue_management_when_below_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    coverage_path = tmp_path / "coverage.json"
    _write_json(trend_path, {"current": 64.0, "baseline": 70.0})
    _write_json(baseline_path, {"coverage": 70.0})
    _write_json(
        coverage_path,
        {"files": {"src/app.py": {"summary": {"percent_covered": 64.0, "missing_lines": 3}}}},
    )

    calls = []

    def fake_issue(repo, title, body, labels):
        calls.append((repo, title, body, labels))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--coverage-path",
            str(coverage_path),
            "--baseline-path",
            str(baseline_path),
            "--run-url",
            "https://example/run",
        ]
    )

    assert exit_code == 0
    assert calls
    assert calls[0][0] == "octo/repo"


def test_main_skips_issue_management_when_at_or_above_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(trend_path, {"current": 72.0, "baseline": 70.0})
    _write_json(baseline_path, {"coverage": 70.0})

    calls = []

    def fake_issue(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
        ]
    )

    assert exit_code == 0
    assert not calls


def test_main_uses_trend_baseline_when_baseline_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    coverage_path = tmp_path / "coverage.json"
    _write_json(trend_path, {"current": 60.0, "baseline": 65.0})
    _write_json(
        coverage_path,
        {"files": {"src/app.py": {"summary": {"percent_covered": 60.0, "missing_lines": 4}}}},
    )

    calls = []

    def fake_issue(repo, title, body, labels):
        calls.append((repo, title, body, labels))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--coverage-path",
            str(coverage_path),
        ]
    )

    assert exit_code == 0
    assert calls


def test_main_dry_run_prints_issue_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(trend_path, {"current": 60.0, "baseline": 70.0})
    _write_json(baseline_path, {"coverage": 70.0})

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--run-url",
            "https://example/run",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Coverage Baseline Breach Report" in captured.out


def test_load_json_handles_missing_and_invalid(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json}", encoding="utf-8")

    assert coverage_guard._load_json(missing) == {}
    assert coverage_guard._load_json(invalid) == {}


def test_get_hotspots_sorts_and_limits() -> None:
    coverage_data = {
        "files": {
            "src/high.py": {"summary": {"percent_covered": 90.0, "missing_lines": 1}},
            "src/low.py": {"summary": {"percent_covered": 10.0, "missing_lines": 9}},
            "src/mid.py": {"summary": {"percent_covered": 50.0, "missing_lines": 4}},
        }
    }

    hotspots = coverage_guard._get_hotspots(coverage_data, limit=2)

    assert [spot["file"] for spot in hotspots] == ["src/low.py", "src/mid.py"]
    assert hotspots[0]["missing_lines"] == 9


def test_format_issue_body_includes_hotspots() -> None:
    body = coverage_guard._format_issue_body(
        current=60.0,
        baseline=70.0,
        delta=-10.0,
        hotspots=[{"file": "src/app.py", "coverage": 60.0, "missing_lines": 4}],
        run_url="https://example/run",
    )

    assert "Coverage Baseline Breach Report" in body
    assert "| `src/app.py` | 60.0% | 4 |" in body
    assert "Gate Workflow Run" in body


def test_format_issue_body_handles_no_hotspots() -> None:
    body = coverage_guard._format_issue_body(
        current=72.0,
        baseline=70.0,
        delta=2.0,
        hotspots=[],
        run_url="https://example/run",
    )

    assert "| _(no files with low coverage)_ | - | - |" in body
