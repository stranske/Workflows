"""Focused checks for the hosted Gate before/after reader."""

import json
from pathlib import Path

import pytest
from scripts.gate_runtime_evidence import (
    SCOPED_FILES,
    VERIFIER,
    build_report,
    configuration_differences,
    coverage_delta,
    pytest_invocation,
    render_markdown,
    scoped_junit,
)

INVOCATION = 'args=("--junitxml=pytest-junit.xml")\npytest -p ci_test_growth "${args[@]}"'


def _resources(
    sha: str, *, workers: int = 4, cpu: str = "AMD EPYC", cache_hit: bool = True
) -> dict:
    worker = {
        "worker_id": "gw0",
        "elapsed_seconds": 100.0,
        "python": "3.14.9",
        "coverage": {"status": "ACTIVE", "core": "SysMonitor", "branch": True},
    }
    return {
        "status": "COMPLETE",
        "controller": {
            "elapsed_seconds": 130.0,
            "python": "3.14.9",
            "coverage": {"status": "ACTIVE", "core": "SysMonitor", "branch": True},
        },
        "workers": [dict(worker, worker_id=f"gw{index}") for index in range(workers)],
        "expected_workers": workers,
        "missing_workers": [],
        "context": {
            "tested_sha": sha,
            "cpu_model": cpu,
            "cache": {
                "uv": cache_hit,
                "pytest": cache_hit,
                "ci_artifact_cache_hit": cache_hit,
                "ci_artifact_found": cache_hit,
            },
        },
    }


def _collection(destination: int, prompt: int, body: int) -> dict:
    return {
        "total": destination + prompt + body,
        "collection_seconds": 2.5,
        "per_file": {
            SCOPED_FILES[0]: destination,
            SCOPED_FILES[1]: prompt,
            SCOPED_FILES[2]: body,
        },
        "largest_functions": [[f"{SCOPED_FILES[0]}::test_component", destination]],
    }


def _write_runtime(
    root: Path, version: str, sha: str, *, cases: tuple[int, int, int], lost: bool
) -> None:
    directory = root / "runtimes" / version
    directory.mkdir(parents=True)
    collection = _collection(*cases)
    resources = _resources(sha, cpu="AMD EPYC 9V45" if version == "3.14" else "AMD EPYC 7763")
    if version != "3.14":
        for row in (resources["controller"], *resources["workers"]):
            row["coverage"] = {"status": "UNKNOWN", "core": None, "branch": None}
    summary = {
        "checks": {"tests": {"outcome": "success"}},
        "coverage": {"percent": 90.0 if not lost else 89.0, "source": "coverage.json"},
        "test_growth": {
            "collection": collection,
            "reported": {
                "timing_status": "KNOWN",
                "dominant_functions_worker_seconds": [
                    ["tests.scripts.test_pr_verifier_delivery_destinations::test_component", 12.5]
                ],
                "dominant_suites_worker_seconds": [
                    ["tests.scripts.test_pr_verifier_delivery_destinations", 40.0]
                ],
            },
        },
        "worker_resources": resources,
    }
    (directory / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (directory / "pytest-collection.json").write_text(json.dumps(collection), encoding="utf-8")
    (directory / "pytest-resources.json").write_text(json.dumps(resources), encoding="utf-8")
    branches = [[1, 2], [1, 3]] if not lost else [[1, 2]]
    if version == "3.14":
        coverage = {
            "files": {
                VERIFIER: {
                    "executed_lines": [1, 2] if not lost else [1],
                    "executed_branches": branches,
                    "summary": {"covered_lines": len(branches)},
                }
            }
        }
        (directory / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")
    classname = SCOPED_FILES[0][:-3].replace("/", ".")
    (directory / "pytest-junit.xml").write_text(
        "<testsuite>"
        f'<testcase classname="{classname}" name="test_component" time="1.25"/>'
        f'<testcase classname="{classname}" name="test_component" time="1.25"/>'
        '<testcase classname="tests.other" name="test_other" time="9"/>'
        "</testsuite>",
        encoding="utf-8",
    )


def _jobs(version: str, wall_start: str, wall_end: str) -> dict:
    return {
        "name": f"python ci / python {version}",
        "conclusion": "success",
        "started_at": wall_start,
        "completed_at": wall_end,
        "runner_name": "GitHub Actions 1",
        "steps": [
            {
                "name": "Install dependencies",
                "started_at": wall_start,
                "completed_at": "2026-11-05T00:00:05Z",
            },
            {
                "name": "Pytest (unit tests with coverage)",
                "started_at": "2026-11-05T00:00:05Z",
                "completed_at": "2026-11-05T00:02:05Z",
            },
            {
                "name": "Record CI summary",
                "started_at": "2026-11-05T00:02:05Z",
                "completed_at": "2026-11-05T00:02:06Z",
            },
        ],
    }


def test_pytest_invocation_stops_before_the_summary_recorder():
    text = "preamble\n" + INVOCATION + "\nsummary recorder\n"
    assert pytest_invocation(text) == 'args=("--junitxml=pytest-junit.xml")\n'
    with pytest.raises(ValueError, match="out of order"):
        pytest_invocation('pytest -p ci_test_growth "${args[@]}"\n' + INVOCATION)


def test_coverage_delta_lists_lost_lines_and_branches():
    before = {
        "files": {VERIFIER: {"executed_lines": [1, 2], "executed_branches": [[1, 2], [1, 3]]}}
    }
    after = {"files": {VERIFIER: {"executed_lines": [1], "executed_branches": [[1, 2]]}}}
    delta = coverage_delta(before, after)
    assert delta["lost_lines"] == [2]
    assert delta["lost_branches"] == [[1, 3]]
    assert coverage_delta(None, after)["available"] is False


def test_scoped_junit_ignores_other_suites(tmp_path: Path):
    path = tmp_path / "pytest-junit.xml"
    path.write_text(
        "<testsuite>"
        '<testcase classname="tests.scripts.test_pr_verifier_prompt_coverage" name="t" time="2.5"/>'
        '<testcase classname="tests.scripts.test_pr_verifier_prompt_coverage" name="u" time="bad"/>'
        "</testsuite>",
        encoding="utf-8",
    )
    report = scoped_junit(path)
    suite = report["suites"]["tests.scripts.test_pr_verifier_prompt_coverage"]
    assert suite["cases"] == 2
    assert suite["worker_seconds"] == 2.5
    assert report["timing_known"] is False
    assert report["worker_seconds"] is None


def test_report_keeps_branch_loss_and_refuses_the_ten_minute_claim(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_runtime(before, "3.14", "a" * 40, cases=(10, 3, 2), lost=False)
    _write_runtime(before, "3.13", "a" * 40, cases=(10, 3, 2), lost=False)
    _write_runtime(after, "3.14", "b" * 40, cases=(4, 3, 2), lost=True)
    _write_runtime(after, "3.13", "b" * 40, cases=(4, 3, 2), lost=True)
    jobs = [
        _jobs("3.14", "2026-11-05T00:00:00Z", "2026-11-05T00:12:00Z"),
        _jobs("3.13", "2026-11-05T00:00:00Z", "2026-11-05T00:08:00Z"),
    ]
    report = build_report(
        before,
        after,
        jobs,
        jobs,
        before_run={"id": "1", "url": "https://example.test/1", "head_sha": "before-head"},
        after_run={"id": "2", "url": "https://example.test/2", "head_sha": "after-head"},
    )
    assert report["runtimes"]["3.14"]["counts"]["before"]["total"] == 15
    assert report["runtimes"]["3.14"]["counts"]["after"]["total"] == 9
    assert report["runtimes"]["3.14"]["verifier_coverage"]["lost_branches"] == [[1, 3]]
    assert report["verifier_branch_loss"] is True
    assert report["runtimes"]["3.13"]["verifier_coverage"]["available"] is False
    assert report["ten_minute_target_met"] is False
    assert report["slowest_job_wall_seconds"] == 720
    assert report["runtimes"]["3.14"]["job"]["before"]["startup_seconds"] == 5
    assert report["runtimes"]["3.14"]["job"]["before"]["pytest_step_seconds"] == 120
    assert report["runtimes"]["3.14"]["job"]["before"]["record_summary_seconds"] == 1
    assert report["runtimes"]["3.14"]["junit"]["before"]["worker_seconds"] == 2.5
    assert report["configuration_identical"] is True
    assert report["timing_controlled"] is True
    text = render_markdown(report)
    assert "## Commands" in text
    assert "## Branch coverage" in text
    assert "Unresolved lost branches" in text
    assert "Target met (<600s job wall): `False`" in text
    assert "does not claim the target is met" in text
    assert "https://example.test/1" in text


def test_ten_minute_target_uses_the_after_jobs_only(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_runtime(before, "3.14", "c" * 40, cases=(10, 3, 2), lost=False)
    _write_runtime(after, "3.14", "d" * 40, cases=(4, 3, 2), lost=False)
    before_jobs = [_jobs("3.14", "2026-11-05T00:00:00Z", "2026-11-05T00:12:00Z")]
    after_jobs = [_jobs("3.14", "2026-11-05T00:00:00Z", "2026-11-05T00:08:20Z")]
    report = build_report(
        before,
        after,
        before_jobs,
        after_jobs,
        before_run={"id": "1", "url": "https://example.test/1", "head_sha": "before-head"},
        after_run={"id": "2", "url": "https://example.test/2", "head_sha": "after-head"},
    )
    assert report["slowest_job_wall_seconds"] == 500
    assert report["ten_minute_target_met"] is True


def test_worker_and_cpu_differences_are_not_called_controlled():
    compared = {
        "3.14": {
            "before": {
                "expected_workers": 4,
                "worker_count": 4,
                "coverage": {"status": "ACTIVE", "branch": True},
                "resource_status": "COMPLETE",
                "missing_workers": [],
                "cpu_model": "AMD EPYC 9V45",
                "cache": {"uv": True},
            },
            "after": {
                "expected_workers": 2,
                "worker_count": 2,
                "coverage": {"status": "ACTIVE", "branch": True},
                "resource_status": "COMPLETE",
                "missing_workers": [],
                "cpu_model": "AMD EPYC 7763",
                "cache": {"uv": False},
            },
        }
    }
    assert configuration_differences(compared) == ["3.14 worker configuration differs"]
    from scripts.gate_runtime_evidence import timing_confounders

    confounders = timing_confounders(compared)
    assert any("CPU model" in item for item in confounders)
    assert any("cache state" in item for item in confounders)
