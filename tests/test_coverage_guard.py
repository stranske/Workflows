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
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

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


def test_find_or_create_issue_reopens_closed_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["gh", "issue", "list"]:
            stdout = json.dumps([{"number": 123, "title": "coverage breach", "state": "CLOSED"}])
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    coverage_guard._find_or_create_issue(
        repo="octo/repo",
        title="[coverage] baseline breach",
        body="body",
        labels=["coverage", "automated"],
    )

    assert any(call[0][:3] == ["gh", "issue", "reopen"] for call in calls)
    assert any(call[0][:3] == ["gh", "issue", "edit"] for call in calls)


def test_find_or_create_issue_creates_new(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

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
    _write_json(baseline_path, {"line": 70.0})
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
    _write_json(baseline_path, {"line": 70.0})

    create_calls = []
    close_calls = []

    def fake_issue(*args, **kwargs):
        create_calls.append((args, kwargs))

    def fake_close(*args, **kwargs):
        close_calls.append((args, kwargs))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)
    monkeypatch.setattr(coverage_guard, "_close_existing_issue", fake_close)

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
    assert not create_calls
    assert close_calls


def test_main_leaves_issue_open_until_recovery_window_satisfied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(
        trend_path,
        {
            "current": 72.0,
            "baseline": 70.0,
            "history": [{"current": 68.0}, {"current": 72.0}],
        },
    )
    _write_json(baseline_path, {"line": 70.0, "recovery_window": 2})

    close_calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args: close_calls.append(args),
    )

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
    assert not close_calls


def test_main_uses_history_file_for_recovery_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    history_path = tmp_path / "coverage-trend-history.ndjson"
    _write_json(trend_path, {"current": 72.0, "baseline": 70.0})
    _write_json(baseline_path, {"line": 70.0, "recovery_days": 2})
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"current": 71.0}),
                json.dumps({"current": 72.0}),
            ]
        ),
        encoding="utf-8",
    )

    close_calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args: close_calls.append(args),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
            "--baseline-path",
            str(baseline_path),
            "--history-path",
            str(history_path),
        ]
    )

    assert exit_code == 0
    assert close_calls


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


def test_main_accepts_legacy_coverage_baseline_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(trend_path, {"current": 72.0, "baseline": 65.0})
    _write_json(baseline_path, {"coverage": 75.0})

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
            "--baseline-path",
            str(baseline_path),
        ]
    )

    assert exit_code == 0
    assert calls
    assert "baseline: 75.00%" in calls[0][2]


def test_main_dry_run_prints_issue_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(trend_path, {"current": 60.0, "baseline": 70.0})
    _write_json(baseline_path, {"line": 70.0})

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
    non_dict = tmp_path / "list.json"
    invalid.write_text("{not-json}", encoding="utf-8")
    non_dict.write_text("[]", encoding="utf-8")

    assert coverage_guard._load_json(missing) == {}
    assert coverage_guard._load_json(invalid) == {}
    assert coverage_guard._load_json(non_dict) == {}


def test_numeric_coercion_rejects_non_finite_values() -> None:
    assert coverage_guard._to_float("nan", 12.0) == 12.0
    assert coverage_guard._to_float(float("inf"), 12.0) == 12.0
    assert coverage_guard._to_int("inf", 7) == 7
    assert coverage_guard._to_int(float("-inf"), 7) == 7


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


def test_get_hotspots_handles_unexpected_payloads() -> None:
    assert coverage_guard._get_hotspots({"files": []}) == []
    assert coverage_guard._get_hotspots({"files": {"bad.py": []}}) == []
    assert (
        coverage_guard._get_hotspots({"files": {"bad.py": {"summary": {"percent_covered": "nan"}}}})
        == []
    )


def test_main_skips_when_trend_payload_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def fake_issue(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(coverage_guard, "_find_or_create_issue", fake_issue)
    monkeypatch.setattr(coverage_guard, "_close_existing_issue", fake_issue)

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--coverage-path",
            str(tmp_path / "coverage.json"),
        ]
    )

    assert exit_code == 0
    assert not calls


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


def test_format_issue_body_handles_missing_run_url() -> None:
    body = coverage_guard._format_issue_body(
        current=60.0,
        baseline=70.0,
        delta=-10.0,
        hotspots=[],
        run_url="",
    )

    assert "Run URL unavailable." in body
    assert "Gate Workflow Run]()" not in body


def test_main_skips_when_current_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    _write_json(trend_path, {"current": "nan", "baseline": 70.0})

    calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_find_or_create_issue",
        lambda *args, **kwargs: calls.append(args),
    )
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: calls.append(args),
    )

    exit_code = coverage_guard.main(
        [
            "--repo",
            "octo/repo",
            "--trend-path",
            str(trend_path),
        ]
    )

    assert exit_code == 0
    assert not calls


def test_close_existing_issue_skips_already_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_find_existing_issue",
        lambda repo, title: {"number": 123, "state": "CLOSED"},
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    coverage_guard._close_existing_issue("octo/repo", "[coverage] baseline breach", "body")

    assert not calls
