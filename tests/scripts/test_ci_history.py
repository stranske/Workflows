import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import ci_history


@pytest.mark.parametrize(
    "reintroduce_redefinition", [False, True], ids=["shipped-source", "duplicate-record"]
)
@pytest.mark.parametrize("regular_package", [False, True], ids=["namespace", "regular"])
@pytest.mark.parametrize(
    "mypy_target", ["scripts", "scripts/ci_history.py"], ids=["package-target", "file-target"]
)
def test_ci_history_typechecks_in_consumer_layout(
    tmp_path: Path, reintroduce_redefinition: bool, regular_package: bool, mypy_target: str
) -> None:
    """Package and file targets accept the fix and reject the duplicate annotation."""
    package = tmp_path / "scripts"
    package.mkdir()
    # Sync ships these modules without __init__.py; consumers may supply their own.
    if regular_package:
        (package / "__init__.py").write_text("", encoding="utf-8")
    source_dir = Path(ci_history.__file__).parent
    for name in ("ci_history.py", "ci_metrics.py"):
        shutil.copyfile(source_dir / name, package / name)

    if reintroduce_redefinition:
        script = package / "ci_history.py"
        source = script.read_text(encoding="utf-8")
        assert "failure_record: dict[str, Any]" in source
        script.write_text(source.replace("failure_record", "record"), encoding="utf-8")

    config = tmp_path / "pyproject.toml"
    config.write_text(
        "[tool.mypy]\nexplicit_package_bases = true\nnamespace_packages = true\n",
        encoding="utf-8",
    )
    # Resolve scripts.* from the consumer checkout, not the Workflows checkout.
    # A subprocess also keeps mypy's global state out of the rest of the test suite.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(config),
            "--cache-dir",
            str(tmp_path / "mypy-cache"),
            "--no-incremental",
            mypy_target,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if reintroduce_redefinition:
        assert result.returncode == 1, result.stdout + result.stderr
        assert 'Name "record" already defined' in result.stdout
        assert "[no-redef]" in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Success: no issues found" in result.stdout


def test_truthy_accepts_common_values() -> None:
    assert ci_history._truthy("1") is True
    assert ci_history._truthy("true") is True
    assert ci_history._truthy("YES") is True
    assert ci_history._truthy("on") is True
    assert ci_history._truthy("0") is False
    assert ci_history._truthy(None) is False


def test_load_metrics_prefers_existing_file(tmp_path: Path) -> None:
    junit_path = tmp_path / "pytest-junit.xml"
    junit_path.write_text("<testsuite />", encoding="utf-8")
    metrics_path = tmp_path / "ci-metrics.json"
    payload = {"summary": {"tests": 1}}
    metrics_path.write_text(json.dumps(payload), encoding="utf-8")

    metrics, from_file = ci_history._load_metrics(junit_path, metrics_path)

    assert metrics == payload
    assert from_file is True


def test_load_metrics_falls_back_to_builder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    junit_path = tmp_path / "pytest-junit.xml"
    junit_path.write_text("<testsuite />", encoding="utf-8")
    metrics_path = tmp_path / "ci-metrics.json"
    metrics_path.write_text("not-json", encoding="utf-8")

    expected = {"summary": {"tests": 2}}

    def fake_build_metrics(path: Path) -> dict:
        assert path == junit_path
        return expected

    monkeypatch.setattr(ci_history.ci_metrics, "build_metrics", fake_build_metrics)

    metrics, from_file = ci_history._load_metrics(junit_path, metrics_path)

    assert metrics == expected
    assert from_file is False


def test_load_metrics_rebuilds_when_summary_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    junit_path = tmp_path / "pytest-junit.xml"
    junit_path.write_text("<testsuite />", encoding="utf-8")
    metrics_path = tmp_path / "ci-metrics.json"
    metrics_path.write_text(json.dumps({"note": "no summary"}), encoding="utf-8")

    expected = {"summary": {"tests": 4}}

    def fake_build_metrics(path: Path) -> dict:
        assert path == junit_path
        return expected

    monkeypatch.setattr(ci_history.ci_metrics, "build_metrics", fake_build_metrics)

    metrics, from_file = ci_history._load_metrics(junit_path, metrics_path)

    assert metrics == expected
    assert from_file is False


def _write_junit(path: Path) -> None:
    path.write_text(
        """<testsuite tests="1" failures="1" errors="0" skipped="0">
  <testcase classname="tests.sample" name="test_failure" time="1.2">
    <failure message="boom" type="AssertionError">details</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )


def test_main_builds_metrics_from_junit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    junit_path = tmp_path / "pytest-junit.xml"
    _write_junit(junit_path)
    metrics_path = tmp_path / "ci-metrics.json"
    history_path = tmp_path / "metrics-history.ndjson"
    classification_path = tmp_path / "classification.json"

    monkeypatch.setenv("JUNIT_PATH", str(junit_path))
    monkeypatch.setenv("METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("ENABLE_CLASSIFICATION", "1")
    monkeypatch.setenv("CLASSIFICATION_OUT", str(classification_path))

    exit_code = ci_history.main()

    assert exit_code == 0
    history_lines = history_path.read_text(encoding="utf-8").splitlines()
    assert len(history_lines) == 1
    record = json.loads(history_lines[0])
    assert record["summary"]["tests"] == 1
    assert record["failures"][0]["status"] == "failure"
    assert "metrics_path" not in record

    payload = json.loads(classification_path.read_text(encoding="utf-8"))
    assert payload["total"] == 1
    assert payload["counts"]["failure"] == 1


def test_main_clears_classification_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    junit_path = tmp_path / "pytest-junit.xml"
    _write_junit(junit_path)
    metrics_path = tmp_path / "ci-metrics.json"
    metrics_path.write_text(json.dumps({"summary": {"tests": 1}}), encoding="utf-8")
    history_path = tmp_path / "metrics-history.ndjson"
    classification_path = tmp_path / "classification.json"
    classification_path.write_text("stale", encoding="utf-8")

    monkeypatch.setenv("JUNIT_PATH", str(junit_path))
    monkeypatch.setenv("METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("CLASSIFICATION_OUT", str(classification_path))

    exit_code = ci_history.main()

    assert exit_code == 0
    assert not classification_path.exists()
    record = json.loads(history_path.read_text(encoding="utf-8").strip())
    assert record["metrics_path"] == str(metrics_path)


def test_build_history_record_includes_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metrics = {"summary": {"tests": 3}, "failures": [{"nodeid": "x"}], "slow_tests": {}}
    junit_path = tmp_path / "pytest-junit.xml"
    metrics_path = tmp_path / "ci-metrics.json"

    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", "abc")

    record = ci_history._build_history_record(
        metrics,
        junit_path=junit_path,
        metrics_path=metrics_path,
        metrics_from_file=True,
    )

    assert record["summary"] == metrics["summary"]
    assert record["failures"] == metrics["failures"]
    assert record["junit_path"] == str(junit_path)
    assert record["metrics_path"] == str(metrics_path)
    assert record["timestamp"].endswith("Z")
    assert record["github"]["github_run_id"] == "123"
    assert record["github"]["github_sha"] == "abc"


def test_build_classification_payload_counts_statuses() -> None:
    metrics = {
        "failures": [
            {"status": "failure", "nodeid": "a"},
            {"status": "error", "nodeid": "b"},
            {"status": "failure", "nodeid": "c"},
        ]
    }

    payload = ci_history._build_classification_payload(metrics)

    assert payload["total"] == 3
    assert payload["counts"] == {"failure": 2, "error": 1}
    assert payload["timestamp"].endswith("Z")
    assert payload["entries"][0]["nodeid"] == "a"


@pytest.mark.parametrize(
    "reintroduce_redefinition",
    [False, True],
    ids=["fixed-source", "reintroduced-redefinition"],
)
def test_ci_history_type_checks_under_consumer_mypy(
    tmp_path: Path, reintroduce_redefinition: bool
) -> None:
    """Consumers type-check this synced script; Workflows' own mypy covers only src/.

    2026-11-07: a second ``record: dict[str, Any]`` annotation in main() raised mypy
    ``no-redef`` and turned trip-planner's typecheck-mypy red on its sync canary.

    Acceptance: the fixed source passes; reintroducing the duplicate annotation
    reproduces the original diagnostic and fails this named gate.
    """
    # This named acceptance gate must fail, rather than skip, when mypy is missing.
    # mypy is a required development dependency and runs through the test interpreter.
    script = Path(__file__).resolve().parents[2] / "scripts" / "ci_history.py"
    target = script
    if reintroduce_redefinition:
        # Mutate a disposable copy so parallel suites never see a broken checkout.
        target = tmp_path / "ci_history.py"
        source = script.read_text(encoding="utf-8")
        assert "failure_record: dict[str, Any]" in source
        target.write_text(source.replace("failure_record", "record"), encoding="utf-8")

    # Consumers run mypy with their own (near-default) config; Workflows' pyproject relaxes
    # checks that consumers enforce, so use an empty config rather than this repo's.
    config = tmp_path / "mypy.ini"
    config.write_text("[mypy]\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(config),
            "--no-incremental",
            "--ignore-missing-imports",
            "--follow-imports=silent",
            "--no-error-summary",
            "--cache-dir",
            str(tmp_path / ".mypy_cache"),
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if reintroduce_redefinition:
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'Name "record" already defined' in result.stdout
        assert "[no-redef]" in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr


# Verbatim finding sync-core quoted on trip-planner#1957 (round 20261107T014654Z).
_SYNC_CORE_NO_REDEF_FINDING = (
    'scripts/ci_history.py:152: error: Name "record" already defined on line 119  [no-redef]'
)
_SYNC_CORE_EVIDENCE_DIR = (
    Path(__file__).resolve().parents[2] / "evidence" / "issue-4508" / "sync-core-clearance"
)


def _sync_core_still_reports_no_redef(log_text: str) -> bool:
    """Return True when a consumer mypy log still carries the #4508 fingerprint.

    Sync-core classifies shipment-caused findings from check logs. A later round
    clears this issue only when the verbatim no-redef line is absent.
    """
    return _SYNC_CORE_NO_REDEF_FINDING in log_text


@pytest.mark.parametrize(
    ("log_text", "expect_reported"),
    [
        (
            'scripts/ci_history.py:152: error: Name "record" already defined on line 119  '
            "[no-redef]\n##[error]Process completed with exit code 1.\n",
            True,
        ),
        ("Success: no issues found in 1 source file\n", False),
        (
            'scripts/other.py:10: error: Name "record" already defined on line 1  [no-redef]\n',
            False,
        ),
    ],
    ids=["original-evidence", "clean-success", "unrelated-no-redef"],
)
def test_sync_core_no_redef_finding_classifier(log_text: str, expect_reported: bool) -> None:
    """Agent-verifiable half of sync-core clearance: fingerprint match only."""
    assert _sync_core_still_reports_no_redef(log_text) is expect_reported


@pytest.mark.parametrize(
    ("fixture_name", "expect_reported"),
    [
        ("typecheck-mypy-red.log", True),
        ("typecheck-mypy-green.log", False),
    ],
    ids=["pinned-red-evidence", "pinned-green-regenerated-head"],
)
def test_sync_core_classifier_on_pinned_trip_planner_logs(
    fixture_name: str, expect_reported: bool
) -> None:
    """Classify real trip-planner#1957 typecheck-mypy excerpts for sync-core clearance.

    Red: original Evidence job 128260180158 (head 041bd22f043a) still reports the
    verbatim fingerprint. Green: regenerated head 948406465cf7 job 128267659502
    succeeds without that finding — the agent-verifiable half of the remaining #4508
    acceptance criterion before the live sync-core round.
    """
    log_path = _SYNC_CORE_EVIDENCE_DIR / fixture_name
    log_text = log_path.read_text(encoding="utf-8")
    assert log_text.strip(), f"empty evidence fixture: {log_path}"
    assert _sync_core_still_reports_no_redef(log_text) is expect_reported
    if expect_reported:
        assert _SYNC_CORE_NO_REDEF_FINDING in log_text
    else:
        assert "ci_history.py" not in log_text
        assert "[no-redef]" not in log_text
        assert "Success: no issues found" in log_text


@pytest.mark.parametrize(
    "reintroduce_redefinition",
    [False, True],
    ids=["cleared-for-sync-core", "emits-sync-core-finding"],
)
def test_ci_history_clears_sync_core_no_redef_finding(
    tmp_path: Path, reintroduce_redefinition: bool
) -> None:
    """Local proxy for the live sync-core clearance acceptance criterion (#4508).

    Mirror reusable-10-ci-python's consumer gate (trip-planner mypy knobs + ``.``
    target with ``--exclude .workflows-lib``). Fixed source must not emit the
    verbatim sync-core fingerprint; reintroducing the duplicate annotation must.
    """
    package = tmp_path / "scripts"
    package.mkdir()
    source_dir = Path(ci_history.__file__).parent
    for name in ("ci_history.py", "ci_metrics.py"):
        shutil.copyfile(source_dir / name, package / name)

    if reintroduce_redefinition:
        script = package / "ci_history.py"
        source = script.read_text(encoding="utf-8")
        assert "failure_record: dict[str, Any]" in source
        script.write_text(source.replace("failure_record", "record"), encoding="utf-8")

    (tmp_path / "pyproject.toml").write_text(
        "[tool.mypy]\nexplicit_package_bases = true\nnamespace_packages = true\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            "pyproject.toml",
            "--exclude",
            ".workflows-lib",
            "--cache-dir",
            str(tmp_path / "mypy-cache"),
            "--no-incremental",
            ".",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined = result.stdout + result.stderr

    if reintroduce_redefinition:
        assert result.returncode != 0, combined
        assert _sync_core_still_reports_no_redef(combined), combined
    else:
        assert result.returncode == 0, combined
        assert not _sync_core_still_reports_no_redef(combined), combined
        assert "[no-redef]" not in combined
        assert 'Name "record" already defined' not in combined
