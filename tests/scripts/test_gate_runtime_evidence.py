"""Focused checks for the hosted Gate before/after reader."""

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import gate_runtime_evidence as evidence
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
    root: Path,
    version: str,
    sha: str,
    *,
    cases: tuple[int, int, int],
    lost: bool,
    coverage_active: bool | None = None,
) -> None:
    if coverage_active is None:
        coverage_active = version == "3.14"
    directory = root / "runtimes" / version
    directory.mkdir(parents=True)
    collection = _collection(*cases)
    resources = _resources(sha, cpu="AMD EPYC 9V45" if version == "3.14" else "AMD EPYC 7763")
    if not coverage_active:
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
    if coverage_active:
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
    junit_rows = [
        f'<testcase classname="{path[:-3].replace("/", ".")}" '
        f'name="test_component[{index}]" time="{2.5 / sum(cases)}"/>'
        for path, count in zip(SCOPED_FILES, cases, strict=True)
        for index in range(count)
    ]
    (directory / "pytest-junit.xml").write_text(
        "<testsuite>"
        + "".join(junit_rows)
        + '<testcase classname="tests.other" name="test_other" time="9"/>'
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
    report = scoped_junit(path, _collection(0, 2, 0))
    suite = report["suites"]["tests.scripts.test_pr_verifier_prompt_coverage"]
    assert suite["cases"] == 2
    assert suite["worker_seconds"] is None
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
    assert report["configuration_identical"] is False
    assert report["timing_controlled"] is False
    assert "source identity not verified" in report["configuration_gaps"]
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


@pytest.fixture
def runtime_pair(tmp_path):
    """Provide two successful runtimes per arm with complete scheduled JUnit rows."""
    before, after = tmp_path / "before", tmp_path / "after"
    for root, sha in ((before, "a" * 40), (after, "b" * 40)):
        for version in ("3.13", "3.14"):
            _write_runtime(root, version, sha, cases=(2, 1, 1), lost=False)
    jobs = [
        _jobs(version, "2026-11-05T00:00:00Z", "2026-11-05T00:08:00Z")
        for version in ("3.13", "3.14")
    ]
    return {
        "before_root": before,
        "after_root": after,
        "before_jobs": jobs,
        "after_jobs": json.loads(json.dumps(jobs)),
        "before_run": {"id": "1", "head_sha": "a" * 40},
        "after_run": {"id": "2", "head_sha": "b" * 40},
    }


@pytest.mark.parametrize("arm", ["before_jobs", "after_jobs"])
@pytest.mark.parametrize("conclusion", [None, "failure", "cancelled", "skipped", "neutral", ""])
def test_gates_require_explicit_success(runtime_pair, arm, conclusion):
    runtime_pair[arm][0]["conclusion"] = conclusion
    report = build_report(**runtime_pair)
    assert report["gates_green"] is False


def test_complete_successful_gates_are_green(runtime_pair):
    assert build_report(**runtime_pair)["gates_green"] is True


@pytest.mark.parametrize(
    "versions,active",
    [
        (("3.12", "3.13"), ("3.12", "3.13")),
        (("3.12", "3.13"), ("3.13",)),
        (("3.12", "3.13"), ()),
        (("3.13", "3.14"), ("3.14",)),
    ],
)
def test_report_labels_observed_runtimes_and_coverage(tmp_path, versions, active):
    # Synthetic receipts exercise reporting; they are not interpreter execution evidence.
    before, after = tmp_path / "before", tmp_path / "after"
    for root, sha in ((before, "a" * 40), (after, "b" * 40)):
        for version in versions:
            _write_runtime(
                root,
                version,
                sha,
                cases=(2, 1, 1),
                lost=False,
                coverage_active=version in active,
            )
    jobs = [_jobs(version, "2026-11-05T00:00:00Z", "2026-11-05T00:08:00Z") for version in versions]
    report = build_report(before, after, jobs, jobs, before_run={}, after_run={})
    assert report["command"]["python_versions"] == list(versions)
    assert report["command"]["coverage_python_versions"] == {
        "before": list(active),
        "after": list(active),
    }
    text = render_markdown(report)
    assert f"- Python versions: {', '.join(versions)}" in text
    for arm in ("before", "after"):
        assert f"Coverage Python ({arm}, ACTIVE probe): {', '.join(active) or 'UNKNOWN'}" in text
    if "3.14" not in versions:
        assert "3.14" not in text
    assert report["verifier_branch_loss"] is (False if active else None)
    assert report["gates_green"] is True
    assert report["timing_controlled"] is False  # No verified source identity supplied.


def test_report_retains_unmatched_runtime_and_arm_specific_coverage(runtime_pair):
    import shutil

    shutil.rmtree(runtime_pair["before_root"] / "runtimes/3.14")
    report = build_report(**runtime_pair)
    assert report["command"]["python_versions"] == ["3.13", "3.14"]
    assert report["command"]["coverage_python_versions"] == {"before": [], "after": ["3.14"]}
    text = render_markdown(report)
    assert "Coverage Python (before, ACTIVE probe): UNKNOWN" in text
    assert "Coverage Python (after, ACTIVE probe): 3.14" in text
    assert any("python versions differ" in gap for gap in report["configuration_gaps"])
    assert report["gates_green"] is False
    assert report["timing_controlled"] is False
    assert report["ten_minute_target_status"] == "UNKNOWN"


@pytest.mark.parametrize("missing", ["started_at", "completed_at"])
def test_target_requires_walls_for_every_runtime(runtime_pair, missing):
    runtime_pair["after_jobs"][0].pop(missing)
    report = build_report(**runtime_pair)
    assert report["ten_minute_target_met"] is False
    assert report["ten_minute_target_status"] == "UNKNOWN"
    assert report["slowest_job_wall_seconds"] is None
    assert report["timing_controlled"] is False
    assert report["timing_gaps"] == ["3.13 after job wall UNKNOWN"]
    assert "job wall UNKNOWN" in render_markdown(report)


@pytest.mark.parametrize("seconds,met", [(599, True), (600, False), (601, False)])
def test_target_has_strict_ten_minute_boundary(runtime_pair, seconds, met):
    runtime_pair["after_jobs"][0][
        "completed_at"
    ] = f"2026-11-05T00:{seconds // 60:02}:{seconds % 60:02}Z"
    assert build_report(**runtime_pair)["ten_minute_target_met"] is met


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (None, "2026-11-05T00:00:01Z", None),
        ("bad", "2026-11-05T00:00:01Z", None),
        ("2026-11-05T00:00:02Z", "2026-11-05T00:00:01Z", None),
        ("2026-11-05T00:00:00", "2026-11-05T00:00:01Z", None),
        ("2026-11-05T00:00:00Z", "2026-11-05T00:00:00Z", 0.0),
    ],
)
def test_invalid_wall_intervals_are_unknown(start, end, expected):
    assert evidence.seconds_between(start, end) == expected


@pytest.mark.parametrize(
    "scheduled,observed,known",
    [(0, 0, True), (1, 0, False), (2, 1, False), (0, 1, False), (1, 1, True)],
)
def test_junit_accounts_for_scheduled_and_observed_cases(tmp_path, scheduled, observed, known):
    path = tmp_path / "junit.xml"
    path.write_text(
        "<testsuite>"
        + f'<testcase classname="{evidence.SCOPED_SUITES[0]}" time="0"/>' * observed
        + "</testsuite>"
    )
    report = scoped_junit(path, _collection(scheduled, 0, 0))
    suite = report["suites"][evidence.SCOPED_SUITES[0]]
    assert suite["cases"] == observed
    assert suite["scheduled_cases"] == scheduled
    assert report["timing_known"] is known
    assert report["timing_status"] == ("KNOWN" if known else "UNKNOWN")
    assert report["worker_seconds"] == (0.0 if known else None)


@pytest.mark.parametrize("duration", [None, "", "bad", "nan", "inf", "-1"])
def test_junit_rejects_invalid_case_durations(tmp_path, duration):
    path = tmp_path / "junit.xml"
    attribute = "" if duration is None else f'time="{duration}"'
    path.write_text(
        f'<testsuite><testcase classname="{evidence.SCOPED_SUITES[0]}" {attribute}/></testsuite>'
    )
    report = scoped_junit(path, _collection(1, 0, 0))
    assert report["timing_known"] is False
    assert report["worker_seconds"] is None


@pytest.mark.parametrize("collection", [None, {}, _collection(-1, 0, 0), _collection(True, 0, 0)])
def test_junit_cannot_assume_unscheduled_suites_are_empty(tmp_path, collection):
    path = tmp_path / "junit.xml"
    path.write_text("<testsuite/>")
    assert scoped_junit(path, collection)["worker_seconds"] is None


@pytest.mark.parametrize("contents", [None, "", "<broken>"])
def test_missing_and_unreadable_junit_are_unknown(tmp_path, contents):
    path = tmp_path / "junit.xml"
    if contents is not None:
        path.write_text(contents)
    report = scoped_junit(path, _collection(0, 0, 0))
    assert report["worker_seconds"] is None
    assert report["timing_status"] == "UNKNOWN"
    assert "UNKNOWN" in report["timing_error"]


def test_junit_aggregate_overflow_is_unknown(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text(
        "<testsuite>"
        + "".join(
            f'<testcase classname="{suite}" time="1e308"/>' for suite in evidence.SCOPED_SUITES[:2]
        )
        + "</testsuite>"
    )
    report = scoped_junit(path, _collection(1, 1, 0))
    assert report["timing_known"] is False
    assert report["worker_seconds"] is None


def test_absent_junit_path_is_unknown_even_for_empty_collection():
    report = scoped_junit(None, _collection(0, 0, 0))
    assert report["timing_status"] == "UNKNOWN"
    assert report["worker_seconds"] is None


def test_junit_rejected_by_safe_parser_is_unknown(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text('<!DOCTYPE foo [<!ENTITY value "blocked">]><testsuite>&value;</testsuite>')
    report = scoped_junit(path, _collection(0, 0, 0))
    assert report["timing_status"] == "UNKNOWN"
    assert "EntitiesForbidden" in report["timing_error"]


@pytest.mark.parametrize("arm", ["before", "after"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("executed_lines", None),
        ("executed_lines", "12"),
        ("executed_lines", [True]),
        ("executed_lines", ["1"]),
        ("executed_lines", [-1]),
        ("executed_lines", [0]),
        ("executed_branches", None),
        ("executed_branches", {}),
        ("executed_branches", [1]),
        ("executed_branches", [[1]]),
        ("executed_branches", [[1, 2, 3]]),
        ("executed_branches", [[1, True]]),
        ("executed_branches", [[1, "2"]]),
        ("executed_branches", [[1, 0]]),
    ],
)
def test_coverage_requires_valid_executed_lists(arm, field, value):
    reports = {
        side: {"files": {VERIFIER: {"executed_lines": [1], "executed_branches": [[1, -1]]}}}
        for side in ("before", "after")
    }
    reports[arm]["files"][VERIFIER][field] = value
    delta = coverage_delta(**reports)
    assert delta == {"available": False, "lost_lines": None, "lost_branches": None}


def test_coverage_empty_lists_and_negative_branch_exits_are_valid():
    before = {"files": {VERIFIER: {"executed_lines": [1], "executed_branches": [[1, -1]]}}}
    after = {"files": {VERIFIER: {"executed_lines": [], "executed_branches": []}}}
    assert coverage_delta(before, after)["lost_branches"] == [[1, -1]]
    del after["files"][VERIFIER]["executed_lines"]
    assert coverage_delta(before, after)["available"] is False


@pytest.mark.parametrize(
    "sha",
    [
        None,
        1,
        "",
        "HEAD",
        "--help",
        "a" * 39,
        "a" * 41,
        "a" * 63,
        "a" * 65,
        "A" * 40,
        "g" * 40,
        "a" * 40 + "\n",
        "a" * 40 + ":path",
    ],
)
def test_git_show_rejects_invalid_object_names_without_running_git(monkeypatch, tmp_path, sha):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid object name reached Git")

    monkeypatch.setattr(evidence.subprocess, "run", unexpected)
    assert evidence.git_show(tmp_path, sha, VERIFIER) is None


@pytest.mark.parametrize("length", [40, 64])
@pytest.mark.parametrize("returncode", [0, 1])
def test_git_show_accepts_full_lowercase_object_names(monkeypatch, tmp_path, length, returncode):
    sha = "0123456789abcdef" * (length // 16) + "01234567" * (length % 16 // 8)

    monkeypatch.setenv("GIT_DIR", "/unrelated/repository/.git")
    monkeypatch.setenv("RECEIPT_CONTROL", "preserved")

    def run(argv, **kwargs):
        assert argv == ["git", "-C", str(tmp_path), "show", f"{sha}:{VERIFIER}"]
        env = kwargs.pop("env")
        assert "GIT_DIR" not in env
        assert env["RECEIPT_CONTROL"] == "preserved"
        assert kwargs.pop("timeout") == 30
        assert kwargs == {"capture_output": True, "text": True, "check": False}
        return SimpleNamespace(returncode=returncode, stdout="source")

    monkeypatch.setattr(evidence.subprocess, "run", run)
    assert evidence.git_show(tmp_path, sha, VERIFIER) == ("source" if returncode == 0 else None)


@pytest.mark.parametrize("arm", ["a", "b"])
@pytest.mark.parametrize(
    "workflow",
    [
        "no markers",
        evidence.INVOCATION_START,
        evidence.INVOCATION_END,
        evidence.INVOCATION_END + evidence.INVOCATION_START,
    ],
)
def test_source_identity_handles_missing_or_reversed_markers(monkeypatch, tmp_path, arm, workflow):
    def show(repo, sha, path):
        if path == evidence.REUSABLE_WORKFLOW:
            return workflow if sha == arm * 40 else INVOCATION
        return path

    monkeypatch.setattr(evidence, "git_show", show)
    identity = evidence.source_identity(tmp_path, "a" * 40, "b" * 40)
    assert identity["identical"] is False
    assert identity["pytest_invocation"] == "missing"
    assert evidence.REUSABLE_WORKFLOW in identity["missing"]


@pytest.mark.parametrize("sha", [None, "c" * 40])
def test_build_report_requires_a_common_tested_sha_for_every_runtime(
    runtime_pair, tmp_path, monkeypatch, sha
):
    path = runtime_pair["after_root"] / "runtimes/3.13/pytest-resources.json"
    resources = json.loads(path.read_text())
    resources["context"]["tested_sha"] = sha
    path.write_text(json.dumps(resources))

    def unexpected(*args):
        pytest.fail("incomplete or inconsistent tested SHAs cannot establish source identity")

    monkeypatch.setattr(evidence, "source_identity", unexpected)
    report = build_report(**runtime_pair, repo=tmp_path)
    assert report["source_identity"] is None
    assert report["configuration_identical"] is False
    assert report["timing_controlled"] is False
    assert "source identity not verified" in report["configuration_gaps"]


@pytest.mark.parametrize("identity_mode", ["omitted", "matching", "mismatched"])
def test_main_verifies_source_identity_inside_report(
    runtime_pair, tmp_path, monkeypatch, identity_mode
):
    calls = []

    def show(repo, sha, path):
        calls.append((repo, sha, path))
        assert repo == tmp_path
        if path == evidence.REUSABLE_WORKFLOW:
            return INVOCATION
        if identity_mode == "mismatched" and path == "requirements.lock" and sha == "b" * 40:
            return "changed dependency lock"
        return path

    monkeypatch.setattr(evidence, "git_show", show)
    args = []
    for side in ("before", "after"):
        jobs_path = tmp_path / f"{side}-jobs.json"
        jobs_path.write_text(json.dumps(runtime_pair[f"{side}_jobs"]))
        args.extend(
            [
                f"--{side}-root",
                str(runtime_pair[f"{side}_root"]),
                f"--{side}-jobs",
                str(jobs_path),
                f"--{side}-run-id",
                runtime_pair[f"{side}_run"]["id"],
                f"--{side}-url",
                f"https://example.test/{side}",
                f"--{side}-head",
                runtime_pair[f"{side}_run"]["head_sha"],
            ]
        )
    if identity_mode != "omitted":
        args.extend(["--repo", str(tmp_path)])
    output = tmp_path / "json/missing/report.json"
    markdown = tmp_path / "markdown/missing/report.md"
    args.extend(["--json-output", str(output), "--markdown-output", str(markdown)])
    assert evidence.main(args) == 0
    report = json.loads(output.read_text())
    identical = identity_mode == "matching"
    assert report["configuration_identical"] is identical
    assert report["timing_controlled"] is identical
    assert markdown.is_file()
    if identity_mode == "omitted":
        assert not calls
        assert report["source_identity"] is None
        assert "source identity not verified" in report["configuration_gaps"]
    else:
        assert calls
        assert report["source_identity"]["identical"] is identical
        if not identical:
            assert any("tested-source" in gap for gap in report["configuration_gaps"])


@pytest.fixture
def controlled_pair(runtime_pair, tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "source_identity", lambda *args: {"identical": True})
    runtime_pair["repo"] = tmp_path
    assert build_report(**runtime_pair)["timing_controlled"] is True
    return runtime_pair


@pytest.mark.parametrize("arm", ["before", "after"])
@pytest.mark.parametrize("receipt", ["collection", "resources", "junit"])
def test_missing_phase_receipts_withhold_controlled_timing(controlled_pair, arm, receipt):
    directory = controlled_pair[f"{arm}_root"] / "runtimes/3.14"
    filename = {
        "collection": "pytest-collection.json",
        "resources": "pytest-resources.json",
        "junit": "pytest-junit.xml",
    }[receipt]
    (directory / filename).unlink()
    summary_path = directory / "summary.json"
    summary = json.loads(summary_path.read_text())
    if receipt == "collection":
        summary["test_growth"].pop("collection")
    elif receipt == "resources":
        summary.pop("worker_resources")
    summary_path.write_text(json.dumps(summary))
    report = build_report(**controlled_pair)
    assert report["timing_controlled"] is False
    assert any(f"3.14 {arm}" in gap and "UNKNOWN" in gap for gap in report["timing_gaps"])
    assert "Timing gap:" in render_markdown(report)


@pytest.mark.parametrize("arm", ["before_jobs", "after_jobs"])
@pytest.mark.parametrize("index", [0, 1, 2])
def test_missing_step_clocks_withhold_controlled_timing(controlled_pair, arm, index):
    controlled_pair[arm][1]["steps"][index].pop("completed_at")
    report = build_report(**controlled_pair)
    assert report["timing_controlled"] is False
    assert report["timing_gaps"]
    assert report["ten_minute_target_status"] == "MET"


@pytest.mark.parametrize("duration", [None, True, "1", -1, float("nan"), float("inf")])
@pytest.mark.parametrize("clock", ["collection", "controller", "worker"])
def test_invalid_execution_clocks_stay_unknown(clock, duration):
    resources, collection = _resources("a" * 40), _collection(1, 1, 1)
    if clock == "collection":
        collection["collection_seconds"] = duration
    elif clock == "controller":
        resources["controller"]["elapsed_seconds"] = duration
    else:
        resources["workers"][0]["elapsed_seconds"] = duration
    split = evidence.execution_split(resources, collection)
    field = {
        "collection": "collection_seconds",
        "controller": "controller_elapsed_seconds",
        "worker": "worker_elapsed_max_seconds",
    }[clock]
    assert split[field] is None
    assert split["in_pytest_reporting_seconds"] is None
    json.dumps(split, allow_nan=False)


def test_zero_execution_clocks_are_measured():
    resources, collection = _resources("a" * 40), _collection(0, 0, 0)
    collection["collection_seconds"] = 0
    for row in (resources["controller"], *resources["workers"]):
        row["elapsed_seconds"] = 0
    split = evidence.execution_split(resources, collection)
    assert split["worker_elapsed_max_seconds"] == 0
    assert split["in_pytest_reporting_seconds"] == 0


@pytest.mark.parametrize(
    "field,value", [("cpu_model", None), ("cpu_model", ""), ("cache", None), ("cache", {})]
)
def test_matching_missing_context_does_not_establish_controlled_timing(
    controlled_pair, field, value
):
    for arm in ("before", "after"):
        path = controlled_pair[f"{arm}_root"] / "runtimes/3.14/pytest-resources.json"
        resources = json.loads(path.read_text())
        resources["context"][field] = value
        path.write_text(json.dumps(resources))
    report = build_report(**controlled_pair)
    assert report["timing_controlled"] is False
    assert report["timing_gaps"]


@pytest.mark.parametrize("arm", ["before", "after"])
def test_missing_active_coverage_keeps_branch_loss_unknown(controlled_pair, arm):
    (controlled_pair[f"{arm}_root"] / "runtimes/3.14/coverage.json").unlink()
    report = build_report(**controlled_pair)
    assert report["verifier_branch_loss"] is None
    assert "Python 3.14 verifier branch comparison: UNKNOWN" in render_markdown(report)


def test_measured_branch_loss_survives_another_unknown_comparison(controlled_pair):
    for arm in ("before", "after"):
        path = controlled_pair[f"{arm}_root"] / "runtimes/3.13/pytest-resources.json"
        resources = json.loads(path.read_text())
        resources["controller"]["coverage"] = {"status": "ACTIVE", "branch": True}
        path.write_text(json.dumps(resources))
    path = controlled_pair["after_root"] / "runtimes/3.14/coverage.json"
    coverage = json.loads(path.read_text())
    coverage["files"][VERIFIER]["executed_branches"].pop()
    path.write_text(json.dumps(coverage))
    report = build_report(**controlled_pair)
    assert report["verifier_branch_loss"] is True
    assert report["runtimes"]["3.13"]["verifier_coverage"]["available"] is False


def test_complete_loss_free_branch_comparison_is_false(controlled_pair):
    assert build_report(**controlled_pair)["verifier_branch_loss"] is False


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        (True, None),
        (False, None),
        (-1, None),
        (1.0, None),
        ("1", None),
        (0, 0),
        (2, 2),
    ],
)
def test_scoped_suite_total_requires_exact_nonnegative_integer(value, expected):
    counts = evidence.scoped_counts({"total": value, "per_file": dict.fromkeys(SCOPED_FILES, 1)})
    assert counts["suite_total"] == expected
    assert counts["total"] == 3


def test_git_show_timeout_is_unavailable(monkeypatch, tmp_path):
    def timeout(argv, **kwargs):
        assert 0 < kwargs["timeout"] <= 60
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(evidence.subprocess, "run", timeout)
    assert evidence.git_show(tmp_path, "a" * 40, VERIFIER) is None


def test_git_show_isolates_real_repository_from_inherited_locations(monkeypatch, tmp_path):
    location_vars = (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_NAMESPACE",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    )
    clean_env = {key: value for key, value in os.environ.items() if key not in location_vars}
    repo = tmp_path / "requested"
    subprocess.run(["git", "init", "-q", str(repo)], env=clean_env, check=True)
    (repo / "receipt").write_text("requested repository source")
    subprocess.run(["git", "-C", str(repo), "add", "receipt"], env=clean_env, check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "receipt",
        ],
        env=clean_env,
        check=True,
    )
    sha = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], env=clean_env, text=True
    ).strip()
    for key in location_vars:
        monkeypatch.setenv(key, str(tmp_path / "wrong-location"))
    original = dict(os.environ)
    assert evidence.git_show(repo, sha, "receipt") == "requested repository source"
    assert dict(os.environ) == original
