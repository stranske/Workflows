from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".github" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import health_summarize as summarize  # noqa: E402


def test_read_bool_variants() -> None:
    assert summarize._read_bool(None) is False
    assert summarize._read_bool("true") is True
    assert summarize._read_bool(" YES ") is True
    assert summarize._read_bool("no") is False


def test_load_json_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert summarize._load_json(missing) is None


def test_load_json_reads_content(tmp_path: Path) -> None:
    payload = {"hello": "world"}
    target = tmp_path / "data.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    assert summarize._load_json(target) == payload


def test_escape_table_replaces_pipe() -> None:
    assert summarize._escape_table("foo|bar") == "foo&#124;bar"


def test_doc_url_without_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_SERVER_URL", raising=False)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)

    url = summarize._doc_url()
    assert url.startswith("https://github.com/stranske/Trend_Model_Project")


def test_doc_url_for_pull_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://example.com")
    monkeypatch.setenv("GITHUB_REF_NAME", "feature-branch")
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")

    url = summarize._doc_url()
    assert url == (
        "https://example.com/owner/repo/blob/main/"
        "docs/ci/WORKFLOWS.md#ci-signature-guard-fixtures"
    )


def _write_signature_fixture(tmp_path: Path, jobs: list[dict[str, str]]) -> tuple[Path, Path]:
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    expected_path = tmp_path / "expected.txt"
    expected_path.write_text(
        summarize.build_signature_hash(jobs),
        encoding="utf-8",
    )
    return jobs_path, expected_path


def test_signature_row_success(tmp_path: Path) -> None:
    jobs = [{"name": "Tests", "step": "pytest", "stack": "boom"}]
    jobs_path, expected_path = _write_signature_fixture(tmp_path, jobs)

    row = summarize._signature_row(jobs_path, expected_path)
    assert row["check"] == "Health 43 CI Signature Guard"
    assert row["conclusion"] == "success"
    assert "✅" in row["status"]


def test_signature_row_mismatch_reports_hash(tmp_path: Path) -> None:
    jobs = [{"name": "Lint", "step": "ruff", "stack": "value"}]
    jobs_path, expected_path = _write_signature_fixture(tmp_path, jobs)
    expected_path.write_text("different", encoding="utf-8")

    row = summarize._signature_row(jobs_path, expected_path)
    assert row["conclusion"] == "failure"
    assert "Hash drift" in row["status"]
    assert "Computed" in row["details"]
    assert "docs" in row["details"].lower()


def test_signature_row_handles_invalid_fixture(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(json.dumps({"invalid": True}), encoding="utf-8")
    expected_path = tmp_path / "expected.txt"
    expected_path.write_text("ignored", encoding="utf-8")

    row = summarize._signature_row(jobs_path, expected_path)
    assert row["conclusion"] == "failure"
    assert "Fixture unreadable" in row["status"]


@pytest.mark.parametrize(
    "section, expected",
    [
        ("foo", ["foo"]),
        (["a", "", "b"], ["a", "b"]),
        ({"contexts": ["x", "y"]}, ["x", "y"]),
        ({}, []),
        (None, []),
    ],
)
def test_extract_contexts(section: object, expected: list[str]) -> None:
    assert summarize._extract_contexts(section) == expected


def test_format_require_up_to_date_handles_match() -> None:
    snapshot = {
        "current": {"strict": True},
        "after": {"strict": True},
    }
    assert summarize._format_require_up_to_date(snapshot) == "✅ True"


def test_format_require_up_to_date_handles_transition() -> None:
    snapshot = {
        "current": {"strict": True},
        "desired": {"strict": False},
    }
    assert summarize._format_require_up_to_date(snapshot) == "✅ True → ❌ False"


def test_format_require_up_to_date_handles_non_mapping_current() -> None:
    snapshot = {"current": "invalid"}
    assert summarize._format_require_up_to_date(snapshot) == "⚠️ Unknown"


def test_format_require_up_to_date_handles_unknown_target() -> None:
    snapshot = {
        "current": {"strict": None},
        "desired": {"strict": None},
    }
    assert summarize._format_require_up_to_date(snapshot) == "⚠️ Unknown"


def test_format_require_up_to_date_handles_arbitrary_value() -> None:
    snapshot = {
        "current": {"strict": "maybe"},
        "desired": {"strict": "later"},
    }
    assert summarize._format_require_up_to_date(snapshot) == "maybe → later"


def test_select_previous_section_prefers_after() -> None:
    snapshot = {
        "after": {"value": 1},
        "desired": {"value": 2},
        "current": {"value": 3},
    }
    assert summarize._select_previous_section(snapshot) == {"value": 1}


def test_select_previous_section_falls_back_to_current() -> None:
    snapshot = {"current": {"value": 2}}
    assert summarize._select_previous_section(snapshot) == {"value": 2}


def test_select_previous_section_handles_missing() -> None:
    assert summarize._select_previous_section({}) is None


def test_format_delta_handles_missing_previous() -> None:
    assert summarize._format_delta({}, None) == "No previous snapshot"


def test_format_delta_handles_non_mapping_current() -> None:
    assert summarize._format_delta("invalid", {}) == "–"


def test_format_delta_handles_missing_previous_section() -> None:
    current = {"current": {"contexts": []}}
    previous = {"current": "invalid"}
    assert summarize._format_delta(current, previous) == "–"


def test_format_delta_handles_non_mapping_current_section() -> None:
    current = {"current": "invalid"}
    previous = {"current": {"contexts": []}}
    assert summarize._format_delta(current, previous) == "–"


def test_format_delta_reports_changes() -> None:
    current = {
        "current": {"contexts": ["lint", "docs"], "strict": True},
    }
    previous = {
        "after": {"contexts": ["lint"], "strict": False},
    }
    delta = summarize._format_delta(current, previous)
    assert "+docs" in delta
    assert "Require up to date" in delta


def test_format_delta_reports_unknown_transition() -> None:
    current = {"current": {"contexts": [], "strict": None}}
    previous = {"current": {"contexts": [], "strict": True}}
    delta = summarize._format_delta(current, previous)
    assert "⚠️ Unknown" in delta
    assert "✅ True" in delta


def test_format_delta_reports_custom_values() -> None:
    current = {"current": {"contexts": [], "strict": "maybe"}}
    previous = {"current": {"contexts": [], "strict": "later"}}
    delta = summarize._format_delta(current, previous)
    assert "maybe" in delta
    assert "later" in delta


def test_snapshot_detail_missing_with_token() -> None:
    detail, severity = summarize._snapshot_detail(
        "Verification",
        None,
        None,
        has_token=True,
    )
    assert "Snapshot missing" in detail
    assert severity == "warning"


def test_snapshot_detail_missing_without_token() -> None:
    detail, severity = summarize._snapshot_detail(
        "Enforcement",
        None,
        None,
        has_token=False,
    )
    assert "observer mode" in detail.lower()
    assert severity == "info"


def test_snapshot_detail_with_error() -> None:
    detail, severity = summarize._snapshot_detail(
        "Enforcement",
        {"error": "failure"},
        None,
        has_token=True,
    )
    assert "❌" in detail
    assert severity == "failure"


def test_snapshot_detail_marks_cleanup_disabled() -> None:
    snapshot = {
        "changes_required": False,
        "current": {"contexts": []},
        "after": {"contexts": []},
        "no_clean": True,
    }
    detail, severity = summarize._snapshot_detail(
        "Verification",
        snapshot,
        None,
        has_token=True,
    )
    assert "Cleanup disabled" in detail
    assert severity == "success"


def test_snapshot_detail_reports_status(monkeypatch: pytest.MonkeyPatch) -> None:
    current = {
        "changes_required": True,
        "changes_applied": True,
        "strict_unknown": True,
        "require_strict": True,
        "current": {"contexts": ["lint"], "strict": False},
        "after": {"contexts": ["lint", "tests"], "strict": True},
    }
    previous = {
        "desired": {"contexts": ["lint"], "strict": False},
    }
    detail, severity = summarize._snapshot_detail(
        "Enforcement",
        current,
        previous,
        has_token=True,
    )
    assert "⚠️" in detail
    assert "Changes applied" in detail
    assert "Δ" in detail
    assert severity == "warning"


def _write_snapshot(tmp_path: Path, name: str, payload: object) -> None:
    target = tmp_path / name
    target.write_text(json.dumps(payload), encoding="utf-8")


def test_branch_row_with_token(tmp_path: Path) -> None:
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()
    _write_snapshot(
        snap_dir,
        "enforcement.json",
        {
            "changes_required": False,
            "current": {"contexts": ["lint"], "strict": True},
        },
    )
    _write_snapshot(
        snap_dir,
        "verification.json",
        {
            "changes_required": True,
            "current": {"contexts": ["lint"], "strict": True},
            "desired": {"contexts": ["lint", "tests"], "strict": False},
        },
    )
    previous = snap_dir / "previous"
    previous.mkdir()
    _write_snapshot(
        previous,
        "verification.json",
        {
            "current": {"contexts": ["lint", "tests"], "strict": False},
        },
    )

    row = summarize._branch_row(snap_dir, has_token=True)
    assert row["check"] == "Health 44 Gate Branch Protection"
    assert row["conclusion"] in {"warning", "failure", "success"}
    assert "Branch protection" in row["status"]


def test_branch_row_without_snapshots(tmp_path: Path) -> None:
    snap_dir = tmp_path / "empty"
    snap_dir.mkdir()

    row = summarize._branch_row(snap_dir, has_token=False)
    assert "Observer mode" in row["details"]
    assert row["conclusion"] == "warning"


def test_branch_row_success_status(tmp_path: Path) -> None:
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()
    _write_snapshot(
        snap_dir,
        "enforcement.json",
        {
            "changes_required": False,
            "current": {"contexts": ["lint"], "strict": True},
        },
    )
    _write_snapshot(
        snap_dir,
        "verification.json",
        {
            "changes_required": False,
            "current": {"contexts": ["lint"], "strict": True},
        },
    )

    row = summarize._branch_row(snap_dir, has_token=True)
    assert row["conclusion"] == "success"
    assert "in sync" in row["status"].lower()


def test_branch_row_handles_empty_pairs(tmp_path: Path) -> None:
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()
    row = summarize._branch_row(snap_dir, has_token=True, pairs=[])
    assert row["conclusion"] == "warning"
    assert "No branch protection snapshots" in row["details"]


def test_branch_row_with_failure(tmp_path: Path) -> None:
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()
    _write_snapshot(snap_dir, "enforcement.json", {"error": "failure"})
    _write_snapshot(
        snap_dir,
        "verification.json",
        {
            "changes_required": True,
            "current": {"contexts": ["lint"], "strict": True},
            "after": {"contexts": ["lint"], "strict": True},
        },
    )

    row = summarize._branch_row(snap_dir, has_token=True)
    assert row["conclusion"] == "failure"
    assert "error" in row["status"].lower()


def test_write_json_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "output" / "summary.json"
    summarize._write_json(target, [{"check": "X", "status": "Y"}])
    content = json.loads(target.read_text(encoding="utf-8"))
    assert content == [{"check": "X", "status": "Y"}]


def test_write_summary_appends_table(tmp_path: Path) -> None:
    target = tmp_path / "summary.md"
    rows = [
        {"check": "C", "status": "S", "details": "D"},
        {"check": "X", "status": "Y", "details": ""},
    ]
    summarize._write_summary(target, rows)

    text = target.read_text(encoding="utf-8")
    assert "Health guardrail" in text
    assert "| C |" in text
    assert "| X | Y | – |" in text


def test_main_executes_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    jobs = [{"name": "Tests", "step": "pytest", "stack": "trace"}]
    jobs_path, expected_path = _write_signature_fixture(tmp_path, jobs)

    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    _write_snapshot(
        snapshot_dir,
        "enforcement.json",
        {
            "changes_required": False,
            "current": {"contexts": ["lint"], "strict": True},
        },
    )
    json_output = tmp_path / "summary" / "rows.json"
    markdown_output = tmp_path / "summary.md"

    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")

    code = summarize.main(
        [
            "--signature-jobs",
            str(jobs_path),
            "--signature-expected",
            str(expected_path),
            "--snapshot-dir",
            str(snapshot_dir),
            "--has-enforce-token",
            "true",
            "--write-json",
            str(json_output),
            "--write-summary",
            str(markdown_output),
        ]
    )

    assert code == 0
    assert json_output.exists()
    assert markdown_output.exists()


def test_main_handles_empty_inputs(tmp_path: Path) -> None:
    code = summarize.main(
        [
            "--write-json",
            str(tmp_path / "rows.json"),
            "--write-summary",
            str(tmp_path / "summary.md"),
        ]
    )
    assert code == 0
    rows_json = tmp_path / "rows.json"
    assert rows_json.exists()
    assert json.loads(rows_json.read_text(encoding="utf-8")) == []
    assert not (tmp_path / "summary.md").exists()


def test_main_skips_outputs_when_not_requested(tmp_path: Path) -> None:
    code = summarize.main([])
    assert code == 0
    assert list(tmp_path.iterdir()) == []


def test_entrypoint_invokes_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    json_path = tmp_path / "rows.json"
    summary_path = tmp_path / "summary.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "health_summarize.py",
            "--write-json",
            str(json_path),
            "--write-summary",
            str(summary_path),
        ],
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("health_summarize", run_name="__main__", alter_sys=True)
    assert excinfo.value.code == 0
    assert json_path.exists()
    assert not summary_path.exists()
