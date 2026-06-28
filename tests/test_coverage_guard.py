import datetime as dt
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools import coverage_guard


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_baseline_applies_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "baseline.json"
    _write_json(
        config_path,
        {
            "line": 86.5,
            "warn_drop": 0.75,
            "recovery_days": "7",
        },
    )

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.baseline == pytest.approx(86.5)
    assert baseline.warn_drop == pytest.approx(0.75)
    assert baseline.recovery_days == 7


def test_load_baseline_enforces_minimum_recovery_days(tmp_path: Path) -> None:
    config_path = tmp_path / "baseline.json"
    _write_json(
        config_path,
        {
            "line": 85.0,
            "warn_drop": 1.0,
            "recovery_days": 0,
        },
    )

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.recovery_days == 3


def test_compute_top_files_prioritises_missing_lines() -> None:
    coverage = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 50.0,
                    "covered_lines": 5,
                    "missing_lines": 5,
                    "num_statements": 10,
                }
            },
            "src/b.py": {
                "summary": {
                    "percent_covered": 70.0,
                    "covered_lines": 7,
                    "missing_lines": 3,
                    "num_statements": 10,
                }
            },
            "src/c.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 10,
                    "missing_lines": 0,
                    "num_statements": 10,
                }
            },
        }
    }

    top = coverage_guard.compute_top_files(coverage, limit=2)

    assert [item.path for item in top] == ["src/a.py", "src/b.py"]
    assert all(item.missing > 0 for item in top)


def test_compute_top_files_falls_back_to_total_lines() -> None:
    coverage = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 40,
                    "missing_lines": 0,
                    "num_statements": 40,
                }
            },
            "src/b.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 10,
                    "missing_lines": 0,
                    "num_statements": 10,
                }
            },
        }
    }

    top = coverage_guard.compute_top_files(coverage, limit=2)

    assert [item.path for item in top] == ["src/a.py", "src/b.py"]


def test_build_update_comment_formats_metrics() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=82.3, baseline=85.0, delta=-2.7)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2024, 12, 31)
    files = [
        coverage_guard.FileCoverage(
            path="src/a.py",
            percent=60.0,
            covered=6,
            total=10,
            missing=4,
        ),
        coverage_guard.FileCoverage(
            path="src/b.py",
            percent=75.0,
            covered=15,
            total=20,
            missing=5,
        ),
    ]

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=True,
        date=today,
        run_url="https://example.invalid/run/1",
        recovery_progress=None,
        top_files=files,
    )

    assert "2024-12-31" in comment
    assert "Current coverage: 82.30%" in comment
    assert "Baseline coverage: 85.00%" in comment
    assert "Delta vs baseline: -2.70 pts" in comment
    assert "Top changed files" in comment
    assert "src/a.py" in comment


def test_build_update_comment_handles_missing_files() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=86.0, baseline=85.0, delta=1.0)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2025, 1, 1)

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=False,
        date=today,
        run_url="",
        recovery_progress="1/3 days above baseline",
        top_files=[],
    )

    assert "2025-01-01" in comment
    assert "Status: At or above baseline" in comment
    assert "Top changed files unavailable" in comment


def test_build_recovered_comment_announces_closure() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=86.0, baseline=85.0, delta=1.0)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=4)
    today = dt.date(2025, 1, 4)

    message = coverage_guard.build_recovered_comment(snapshot, config, today)

    assert "Coverage recovered above baseline" in message
    assert "4 consecutive days" in message
    assert "Closing this issue" in message


def test_find_or_create_issue_updates_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["gh", "issue", "list"]:
            stdout = json.dumps([{"number": 123, "title": "[coverage] baseline breach"}])
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
            stdout = json.dumps(
                [{"number": 123, "title": "[coverage] baseline breach", "state": "CLOSED"}]
            )
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
    create_call = next(call[0] for call in calls if call[0][:3] == ["gh", "issue", "create"])
    assert create_call.count("--label") == 2
    assert not any(call[0][:3] == ["gh", "issue", "edit"] for call in calls)


def test_find_or_create_issue_retries_without_missing_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:3] == ["gh", "issue", "create"] and "--label" in args:
            raise subprocess.CalledProcessError(1, args, stderr="could not resolve label")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    coverage_guard._find_or_create_issue(
        repo="octo/repo",
        title="[coverage] baseline breach",
        body="body",
        labels=["coverage", "automated"],
    )

    create_calls = [call[0] for call in calls if call[0][:3] == ["gh", "issue", "create"]]
    assert len(create_calls) == 2
    assert "--label" in create_calls[0]
    assert "--label" not in create_calls[1]


def test_find_existing_issue_requires_exact_title(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        stdout = json.dumps(
            [
                {"number": 123, "title": "coverage baseline breach", "state": "OPEN"},
                {"number": 456, "title": "[coverage] baseline breach details", "state": "OPEN"},
            ]
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    assert coverage_guard._find_existing_issue("octo/repo", "[coverage] baseline breach") is None
    assert all(args[args.index("--limit") + 1] == "200" for args in calls)


def test_find_existing_issue_falls_back_to_title_only_when_label_search_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "--label" in args:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        stdout = json.dumps([{"number": 123, "title": "[coverage] baseline breach"}])
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    issue = coverage_guard._find_existing_issue(
        "octo/repo",
        "[coverage] baseline breach",
        labels=["coverage", "automated"],
    )

    assert issue == {"number": 123, "title": "[coverage] baseline breach"}
    assert any("--label" in args for args in calls)
    assert any("--label" not in args for args in calls)


def test_find_existing_issue_returns_none_after_label_and_title_search_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    assert (
        coverage_guard._find_existing_issue(
            "octo/repo",
            "[coverage] baseline breach",
            labels=["coverage", "automated"],
        )
        is None
    )
    assert any("--label" in args for args in calls)
    assert any("--label" not in args for args in calls)


def test_find_existing_issue_retries_title_only_when_label_search_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "--label" in args:
            return SimpleNamespace(returncode=1, stdout="", stderr="could not resolve label")
        stdout = json.dumps([{"number": 123, "title": "[coverage] baseline breach"}])
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    issue = coverage_guard._find_existing_issue(
        "octo/repo",
        "[coverage] baseline breach",
        labels=["coverage"],
    )

    assert issue == {"number": 123, "title": "[coverage] baseline breach"}
    assert any("--label" in args for args in calls)
    assert any("--label" not in args for args in calls)


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
    assert calls[0][3] == ["coverage", "automated"]


def test_main_accepts_issue_label_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(trend_path, {"current": 64.0, "baseline": 70.0})
    _write_json(baseline_path, {"line": 70.0})

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
            "--issue-label",
            "coverage",
            "--issue-label",
            "ci",
        ]
    )

    assert exit_code == 0
    assert calls[0][3] == ["coverage", "ci"]


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
        lambda *args, **kwargs: close_calls.append((args, kwargs)),
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


def test_main_uses_embedded_history_when_history_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(
        trend_path,
        {
            "current": 72.0,
            "baseline": 70.0,
            "history": [{"current": 71.0}, {"current": 72.0}],
        },
    )
    _write_json(baseline_path, {"line": 70.0, "recovery_window": 2})

    close_calls = []
    monkeypatch.setattr(
        coverage_guard,
        "_close_existing_issue",
        lambda *args, **kwargs: close_calls.append((args, kwargs)),
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
    assert close_calls


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
        lambda *args, **kwargs: close_calls.append((args, kwargs)),
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


def test_recovery_window_counts_same_coverage_from_distinct_runs() -> None:
    trend_data = {"current": 72.0, "run_id": "run-2"}
    history_records = [{"current": 72.0, "run_id": "run-1"}]

    assert coverage_guard._recovery_window_satisfied(
        trend_data,
        baseline=70.0,
        recovery_window=2,
        history_records=history_records,
    )


def test_recovery_window_accepts_aggregate_history_records() -> None:
    trend_data = {"current": 72.0, "run_id": "run-3"}
    history_records = [
        {"avg_coverage": 74.0, "run_id": "run-1"},
        {"worst_job_coverage": 71.0, "run_id": "run-2"},
    ]

    assert coverage_guard._recovery_window_satisfied(
        trend_data,
        baseline=70.0,
        recovery_window=3,
        history_records=history_records,
    )


def test_recovery_window_uses_worst_job_before_average() -> None:
    trend_data = {"current": 72.0, "run_id": "run-2"}
    history_records = [{"avg_coverage": 80.0, "worst_job_coverage": 69.0, "run_id": "run-1"}]

    assert not coverage_guard._recovery_window_satisfied(
        trend_data,
        baseline=70.0,
        recovery_window=2,
        history_records=history_records,
    )


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


def test_main_skips_when_baseline_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trend_path = tmp_path / "trend.json"
    baseline_path = tmp_path / "missing-baseline.json"
    _write_json(trend_path, {"current": 60.0})

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
            "--baseline-path",
            str(baseline_path),
        ]
    )

    assert exit_code == 0
    assert not calls


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
        lambda repo, title, labels=None: {"number": 123, "state": "CLOSED"},
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    coverage_guard._close_existing_issue("octo/repo", "[coverage] baseline breach", "body")

    assert not calls


# Tests for _load_ndjson


def test_load_ndjson_handles_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ndjson"
    assert coverage_guard._load_ndjson(missing) == []


def test_load_ndjson_handles_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.ndjson"
    empty.write_text("", encoding="utf-8")
    assert coverage_guard._load_ndjson(empty) == []


def test_load_ndjson_handles_whitespace_only(tmp_path: Path) -> None:
    whitespace = tmp_path / "whitespace.ndjson"
    whitespace.write_text("  \n  \n", encoding="utf-8")
    assert coverage_guard._load_ndjson(whitespace) == []


def test_load_ndjson_parses_valid_records(tmp_path: Path) -> None:
    ndjson_file = tmp_path / "valid.ndjson"
    ndjson_file.write_text(
        '{"a": 1}\n{"b": 2}\n{"c": 3}',
        encoding="utf-8",
    )
    result = coverage_guard._load_ndjson(ndjson_file)
    assert len(result) == 3
    assert result[0] == {"a": 1}
    assert result[1] == {"b": 2}
    assert result[2] == {"c": 3}


def test_load_ndjson_skips_invalid_lines(tmp_path: Path) -> None:
    ndjson_file = tmp_path / "mixed.ndjson"
    ndjson_file.write_text(
        '{"a": 1}\n{invalid}\n{"b": 2}',
        encoding="utf-8",
    )
    result = coverage_guard._load_ndjson(ndjson_file)
    assert len(result) == 2
    assert result[0] == {"a": 1}
    assert result[1] == {"b": 2}


def test_load_ndjson_skips_non_dict_records(tmp_path: Path) -> None:
    ndjson_file = tmp_path / "non_dict.ndjson"
    ndjson_file.write_text(
        '[1, 2]\n"string"\n{"a": 1}',
        encoding="utf-8",
    )
    result = coverage_guard._load_ndjson(ndjson_file)
    assert len(result) == 1
    assert result[0] == {"a": 1}


# Tests for _parse_finite_float


def test_parse_finite_float_handles_valid_integers() -> None:
    assert coverage_guard._parse_finite_float(42) == 42.0
    assert coverage_guard._parse_finite_float(0) == 0.0
    assert coverage_guard._parse_finite_float(-10) == -10.0


def test_parse_finite_float_handles_valid_floats() -> None:
    assert coverage_guard._parse_finite_float(3.14) == 3.14
    assert coverage_guard._parse_finite_float(-2.5) == -2.5
    assert coverage_guard._parse_finite_float(0.0) == 0.0


def test_parse_finite_float_handles_valid_strings() -> None:
    assert coverage_guard._parse_finite_float("42.5") == 42.5
    assert coverage_guard._parse_finite_float("3.14") == 3.14
    assert coverage_guard._parse_finite_float("-10") == -10.0
    assert coverage_guard._parse_finite_float("0") == 0.0


def test_parse_finite_float_rejects_boolean() -> None:
    assert coverage_guard._parse_finite_float(True) is None
    assert coverage_guard._parse_finite_float(False) is None


def test_parse_finite_float_rejects_non_numeric_strings() -> None:
    assert coverage_guard._parse_finite_float("not a number") is None
    assert coverage_guard._parse_finite_float("") is None
    assert coverage_guard._parse_finite_float("3.14.15") is None


def test_parse_finite_float_rejects_non_finite_values() -> None:
    assert coverage_guard._parse_finite_float(float("inf")) is None
    assert coverage_guard._parse_finite_float(float("-inf")) is None
    assert coverage_guard._parse_finite_float(float("nan")) is None
    assert coverage_guard._parse_finite_float("inf") is None
    assert coverage_guard._parse_finite_float("nan") is None


def test_parse_finite_float_rejects_none() -> None:
    assert coverage_guard._parse_finite_float(None) is None


def test_parse_finite_float_rejects_unsupported_types() -> None:
    assert coverage_guard._parse_finite_float([]) is None
    assert coverage_guard._parse_finite_float({}) is None
    assert coverage_guard._parse_finite_float(object()) is None


# Tests for _to_float


def test_to_float_handles_valid_integers() -> None:
    assert coverage_guard._to_float(42) == 42.0
    assert coverage_guard._to_float(0) == 0.0


def test_to_float_handles_valid_floats() -> None:
    assert coverage_guard._to_float(3.14) == 3.14
    assert coverage_guard._to_float(0.0) == 0.0


def test_to_float_handles_valid_strings() -> None:
    assert coverage_guard._to_float("42.5") == 42.5
    assert coverage_guard._to_float("3.14") == 3.14


def test_to_float_uses_default_for_none() -> None:
    assert coverage_guard._to_float(None, default=12.0) == 12.0


def test_to_float_uses_default_for_invalid() -> None:
    assert coverage_guard._to_float("not a number", default=12.0) == 12.0
    assert coverage_guard._to_float([], default=12.0) == 12.0
    assert coverage_guard._to_float({}, default=12.0) == 12.0


def test_to_float_uses_default_for_boolean() -> None:
    assert coverage_guard._to_float(True, default=12.0) == 12.0
    assert coverage_guard._to_float(False, default=12.0) == 12.0


def test_to_float_uses_default_for_non_finite() -> None:
    assert coverage_guard._to_float(float("inf"), default=12.0) == 12.0
    assert coverage_guard._to_float(float("nan"), default=12.0) == 12.0


def test_to_float_default_is_zero() -> None:
    assert coverage_guard._to_float("invalid") == 0.0
    assert coverage_guard._to_float(None) == 0.0


# Tests for _to_int


def test_to_int_handles_valid_integers() -> None:
    assert coverage_guard._to_int(42) == 42
    assert coverage_guard._to_int(0) == 0
    assert coverage_guard._to_int(-10) == -10


def test_to_int_handles_valid_floats() -> None:
    assert coverage_guard._to_int(3.14) == 3
    assert coverage_guard._to_int(3.99) == 3
    assert coverage_guard._to_int(-2.5) == -2
    assert coverage_guard._to_int(0.0) == 0


def test_to_int_handles_valid_strings() -> None:
    assert coverage_guard._to_int("42") == 42
    assert coverage_guard._to_int("3.14") == 3
    assert coverage_guard._to_int("3.99") == 3
    assert coverage_guard._to_int("-10") == -10


def test_to_int_uses_default_for_none() -> None:
    assert coverage_guard._to_int(None, default=7) == 7


def test_to_int_uses_default_for_invalid() -> None:
    assert coverage_guard._to_int("not a number", default=7) == 7
    assert coverage_guard._to_int([], default=7) == 7
    assert coverage_guard._to_int({}, default=7) == 7


def test_to_int_uses_default_for_boolean() -> None:
    assert coverage_guard._to_int(True, default=7) == 7
    assert coverage_guard._to_int(False, default=7) == 7


def test_to_int_uses_default_for_non_finite() -> None:
    assert coverage_guard._to_int(float("inf"), default=7) == 7
    assert coverage_guard._to_int(float("-inf"), default=7) == 7
    assert coverage_guard._to_int(float("nan"), default=7) == 7
    assert coverage_guard._to_int("inf", default=7) == 7
    assert coverage_guard._to_int("nan", default=7) == 7


def test_to_int_default_is_zero() -> None:
    assert coverage_guard._to_int("invalid") == 0
    assert coverage_guard._to_int(None) == 0


# Tests for load_baseline with defaults


def test_load_baseline_uses_all_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "empty.json"
    _write_json(config_path, {})

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.baseline == pytest.approx(80.0)
    assert baseline.warn_drop == pytest.approx(1.0)
    assert baseline.recovery_days == 3


def test_load_baseline_uses_coverage_key(tmp_path: Path) -> None:
    config_path = tmp_path / "coverage_key.json"
    _write_json(config_path, {"coverage": 85.0})

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.baseline == pytest.approx(85.0)


def test_load_baseline_uses_recovery_window_key(tmp_path: Path) -> None:
    config_path = tmp_path / "recovery_window.json"
    _write_json(config_path, {"line": 85.0, "recovery_window": 5})

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.recovery_days == 5


def test_load_baseline_uses_recovery_runs_key(tmp_path: Path) -> None:
    config_path = tmp_path / "recovery_runs.json"
    _write_json(config_path, {"line": 85.0, "recovery_runs": 4})

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.recovery_days == 4


def test_load_baseline_handles_string_values(tmp_path: Path) -> None:
    config_path = tmp_path / "string_values.json"
    _write_json(
        config_path,
        {
            "line": "85.5",
            "warn_drop": "0.5",
            "recovery_days": "5",
        },
    )

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.baseline == pytest.approx(85.5)
    assert baseline.warn_drop == pytest.approx(0.5)
    assert baseline.recovery_days == 5


def test_load_baseline_handles_missing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "missing.json"

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.baseline == pytest.approx(80.0)
    assert baseline.warn_drop == pytest.approx(1.0)
    assert baseline.recovery_days == 3


def test_load_baseline_string_recovery_days(tmp_path: Path) -> None:
    config_path = tmp_path / "string_recovery.json"
    _write_json(config_path, {"line": 85.0, "recovery_days": "7"})

    baseline = coverage_guard.load_baseline(config_path)

    assert baseline.recovery_days == 7


# Tests for compute_top_files


def test_compute_top_files_returns_empty_for_invalid_files() -> None:
    assert coverage_guard.compute_top_files({"files": "not a dict"}) == []
    assert coverage_guard.compute_top_files({"files": []}) == []
    assert coverage_guard.compute_top_files({}) == []


def test_compute_top_files_returns_empty_for_zero_limit() -> None:
    coverage = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 50.0,
                    "covered_lines": 5,
                    "missing_lines": 5,
                    "num_statements": 10,
                }
            },
        }
    }
    assert coverage_guard.compute_top_files(coverage, limit=0) == []
    assert coverage_guard.compute_top_files(coverage, limit=-1) == []


def test_compute_top_files_skips_invalid_file_entries() -> None:
    coverage = {
        "files": {
            "valid.py": {
                "summary": {
                    "percent_covered": 50.0,
                    "covered_lines": 5,
                    "missing_lines": 5,
                    "num_statements": 10,
                }
            },
            "invalid_path": {"bad": "data"},
            "invalid_summary": {"summary": "not a dict"},
            "missing_percent": {"summary": {"covered_lines": 5, "missing_lines": 5}},
            "none_percent": {"summary": {"percent_covered": None}},
        }
    }
    result = coverage_guard.compute_top_files(coverage)
    assert len(result) == 1
    assert result[0].path == "valid.py"


def test_compute_top_files_fallback_sorting_by_total_when_no_missing() -> None:
    coverage = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 5,
                    "missing_lines": 0,
                    "num_statements": 5,
                }
            },
            "src/b.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 10,
                    "missing_lines": 0,
                    "num_statements": 10,
                }
            },
            "src/c.py": {
                "summary": {
                    "percent_covered": 100.0,
                    "covered_lines": 8,
                    "missing_lines": 0,
                    "num_statements": 8,
                }
            },
        }
    }
    result = coverage_guard.compute_top_files(coverage, limit=3)
    assert [item.path for item in result] == ["src/b.py", "src/c.py", "src/a.py"]


def test_compute_top_files_uses_covered_plus_missing_when_total_missing() -> None:
    coverage = {
        "files": {
            "src/a.py": {
                "summary": {
                    "percent_covered": 50.0,
                    "covered_lines": 5,
                    "missing_lines": 5,
                }
            },
        }
    }
    result = coverage_guard.compute_top_files(coverage)
    assert len(result) == 1
    assert result[0].total == 10


def test_compute_top_files_respects_limit() -> None:
    coverage = {
        "files": {
            f"file{i}.py": {
                "summary": {
                    "percent_covered": 50.0,
                    "covered_lines": 5,
                    "missing_lines": 5,
                    "num_statements": 10,
                }
            }
            for i in range(20)
        }
    }
    result = coverage_guard.compute_top_files(coverage, limit=5)
    assert len(result) == 5


# Tests for build_update_comment


def test_build_update_comment_with_recovery_progress_and_top_files() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=82.3, baseline=85.0, delta=-2.7)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2024, 12, 31)
    files = [
        coverage_guard.FileCoverage(
            path="src/a.py",
            percent=60.0,
            covered=6,
            total=10,
            missing=4,
        ),
    ]

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=True,
        date=today,
        run_url="https://example.invalid/run/1",
        recovery_progress="1/3 days above baseline",
        top_files=files,
    )

    assert "Recovery progress: 1/3 days above baseline" in comment
    assert "src/a.py" in comment
    assert "Below baseline" in comment


def test_build_update_comment_without_recovery_progress() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=82.3, baseline=85.0, delta=-2.7)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2024, 12, 31)

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=True,
        date=today,
        run_url="https://example.invalid/run/1",
        recovery_progress=None,
        top_files=[],
    )

    assert "Recovery progress" not in comment
    assert "Top changed files unavailable" in comment


def test_build_update_comment_without_run_url() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=82.3, baseline=85.0, delta=-2.7)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2024, 12, 31)

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=True,
        date=today,
        run_url="",
        recovery_progress=None,
        top_files=[],
    )

    assert "Run:" not in comment


def test_build_update_comment_above_baseline() -> None:
    snapshot = coverage_guard.CoverageSnapshot(current=86.0, baseline=85.0, delta=1.0)
    config = coverage_guard.BaselineConfig(baseline=85.0, warn_drop=1.0, recovery_days=3)
    today = dt.date(2025, 1, 1)

    comment = coverage_guard.build_update_comment(
        snapshot,
        config,
        below_baseline=False,
        date=today,
        run_url="https://example.invalid/run/1",
        recovery_progress=None,
        top_files=[],
    )

    assert "Status: At or above baseline" in comment
