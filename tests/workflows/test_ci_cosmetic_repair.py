from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime as dt_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

ci_cosmetic_repair = pytest.importorskip("scripts.ci_cosmetic_repair")

pytestmark = pytest.mark.filterwarnings(
    "ignore:Testing an element's truth value will always return True in future versions.:DeprecationWarning"
)


def _read_summary(repo_root: Path) -> dict[str, object]:
    summary_path = repo_root / ci_cosmetic_repair.SUMMARY_FILE
    assert summary_path.exists(), "summary file should be created"
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _write_junit(tmp_path: Path, message: str) -> Path:
    junit = """
        <testsuite tests=\"1\" failures=\"1\">
          <testcase classname=\"tests.test_sample\" name=\"test_cosmetic\">
            <properties>
              <property name=\"markers\" value=\"cosmetic\" />
            </properties>
            <failure message=\"{message}\">
              <details>expected 1.23 got 1.22</details>
            </failure>
          </testcase>
        </testsuite>
    """.strip().format(
        message=escape(message, {'"': "&quot;"})
    )
    path = tmp_path / "report.xml"
    path.write_text(junit, encoding="utf-8")
    return path


def test_cosmetic_repair_updates_guarded_value(tmp_path: Path) -> None:
    repo_root = tmp_path
    target = repo_root / "tests" / "fixtures" / "baseline.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "EXPECTED_ALPHA = 1.23450  # cosmetic-repair: float EXPECTED_ALPHA\n",
        encoding="utf-8",
    )
    message = "COSMETIC_TOLERANCE " + json.dumps(
        {
            "path": "tests/fixtures/baseline.py",
            "guard": "float",
            "key": "EXPECTED_ALPHA",
            "actual": 1.23456,
            "digits": 5,
        }
    )
    report = _write_junit(repo_root, message)

    exit_code = ci_cosmetic_repair.main(
        [
            "--apply",
            "--report",
            str(report),
            "--root",
            str(repo_root),
            "--skip-pr",
        ]
    )

    assert exit_code == 0
    updated = target.read_text(encoding="utf-8")
    assert "1.23456" in updated
    assert updated.endswith("\n")
    summary = _read_summary(repo_root)
    assert summary["status"] == "applied-no-pr"
    assert summary["mode"] == "apply"
    assert summary.get("changed_files") == ["tests/fixtures/baseline.py"]
    instructions = summary.get("instructions")
    assert isinstance(instructions, list) and instructions


def test_cosmetic_repair_refuses_without_guard(tmp_path: Path) -> None:
    repo_root = tmp_path
    target = repo_root / "tests" / "fixtures" / "baseline.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("EXPECTED_ALPHA = 1.23\n", encoding="utf-8")
    message = "COSMETIC_TOLERANCE " + json.dumps(
        {
            "path": "tests/fixtures/baseline.py",
            "guard": "float",
            "key": "EXPECTED_ALPHA",
            "actual": 1.23456,
            "digits": 5,
        }
    )
    report = _write_junit(repo_root, message)

    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError):
        ci_cosmetic_repair.main(
            [
                "--apply",
                "--report",
                str(report),
                "--root",
                str(repo_root),
                "--skip-pr",
            ]
        )


def test_second_run_detects_no_changes(tmp_path: Path) -> None:
    repo_root = tmp_path
    target = repo_root / "tests" / "fixtures" / "baseline.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "EXPECTED_ALPHA = 1.23450  # cosmetic-repair: float EXPECTED_ALPHA\n",
        encoding="utf-8",
    )
    message = "COSMETIC_TOLERANCE " + json.dumps(
        {
            "path": "tests/fixtures/baseline.py",
            "guard": "float",
            "key": "EXPECTED_ALPHA",
            "actual": 1.23456,
            "digits": 5,
        }
    )
    report = _write_junit(repo_root, message)

    first_exit = ci_cosmetic_repair.main(
        [
            "--apply",
            "--report",
            str(report),
            "--root",
            str(repo_root),
            "--skip-pr",
        ]
    )
    assert first_exit == 0
    first_summary = _read_summary(repo_root)
    assert first_summary["status"] == "applied-no-pr"

    second_exit = ci_cosmetic_repair.main(
        [
            "--apply",
            "--report",
            str(report),
            "--root",
            str(repo_root),
            "--skip-pr",
        ]
    )
    assert second_exit == 0
    second_summary = _read_summary(repo_root)
    assert second_summary["status"] == "no-changes"


def test_cosmetic_snapshot_updates_file(tmp_path: Path) -> None:
    repo_root = tmp_path
    target = repo_root / "tests" / "fixtures" / "snapshot.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old snapshot\n# cosmetic-repair: snapshot baseline\n", encoding="utf-8")
    replacement = "new snapshot\n# cosmetic-repair: snapshot baseline\n"
    message = "COSMETIC_SNAPSHOT " + json.dumps(
        {
            "path": "tests/fixtures/snapshot.txt",
            "guard": "snapshot",
            "replacement": replacement,
        }
    )
    report = _write_junit(repo_root, message)

    exit_code = ci_cosmetic_repair.main(
        [
            "--apply",
            "--report",
            str(report),
            "--root",
            str(repo_root),
            "--skip-pr",
        ]
    )

    assert exit_code == 0
    assert target.read_text(encoding="utf-8") == replacement
    summary = _read_summary(repo_root)
    assert summary["status"] == "applied-no-pr"
    assert summary.get("changed_files") == ["tests/fixtures/snapshot.txt"]
    assert summary.get("instructions")[0]["kind"] == "snapshot"


def test_dry_run_writes_summary(tmp_path: Path) -> None:
    repo_root = tmp_path
    target = repo_root / "tests" / "fixtures" / "baseline.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "EXPECTED_ALPHA = 1.23450  # cosmetic-repair: float EXPECTED_ALPHA\n",
        encoding="utf-8",
    )
    message = "COSMETIC_TOLERANCE " + json.dumps(
        {
            "path": "tests/fixtures/baseline.py",
            "guard": "float",
            "key": "EXPECTED_ALPHA",
            "actual": 1.23456,
            "digits": 5,
        }
    )
    report = _write_junit(repo_root, message)

    exit_code = ci_cosmetic_repair.main(
        [
            "--dry-run",
            "--report",
            str(report),
            "--root",
            str(repo_root),
        ]
    )

    assert exit_code == 0
    summary = _read_summary(repo_root)
    assert summary["status"] == "dry-run"
    assert summary["mode"] == "dry-run"
    assert summary.get("instructions")


def test_run_pytest_invokes_python(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(cmd, *, text, capture_output):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(ci_cosmetic_repair.subprocess, "run", fake_run)
    report = tmp_path / "report.xml"
    result = ci_cosmetic_repair.run_pytest(report, ["-k", "cosmetic"])

    assert isinstance(result, subprocess.CompletedProcess)
    assert captured["cmd"] == [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        f"--junitxml={report}",
        "-k",
        "cosmetic",
    ]


def test_run_raises_when_command_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, *, cwd=None, text=True, capture_output=True):
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="boom")

    monkeypatch.setattr(ci_cosmetic_repair.subprocess, "run", fake_run)

    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError) as exc:
        ci_cosmetic_repair._run(["git", "status"], cwd=Path("/tmp"))

    assert "boom" in str(exc.value)


def test_run_returns_completed_process(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = subprocess.CompletedProcess(["git", "status"], 0, stdout="ok", stderr="")

    monkeypatch.setattr(ci_cosmetic_repair.subprocess, "run", lambda *args, **kwargs: expected)

    result = ci_cosmetic_repair._run(["git", "status"], cwd=Path("/tmp"))

    assert result is expected


@pytest.mark.parametrize(
    ("kind", "payload", "message"),
    [
        ("COSMETIC_TOLERANCE", {"guard": "float"}, "Missing target path"),
        ("COSMETIC_TOLERANCE", {"path": "tests/foo.py"}, "Missing guard token"),
        (
            "COSMETIC_TOLERANCE",
            {"path": "tests/foo.py", "guard": "float", "key": 1},
            "Invalid key",
        ),
        (
            "COSMETIC_SNAPSHOT",
            {"path": "tests/foo.py", "guard": "snapshot", "replacement": 1},
            "Snapshot repair requires",
        ),
    ],
)
def test_build_instruction_validation(kind: str, payload: dict[str, object], message: str) -> None:
    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError) as exc:
        ci_cosmetic_repair.build_instruction(kind, payload, source="case")

    assert message in str(exc.value)


def test_build_instruction_unsupported_kind() -> None:
    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError) as exc:
        ci_cosmetic_repair.build_instruction(
            "COSMETIC_UNKNOWN",
            {"path": "tests/foo.py", "guard": "float"},
            source="case",
        )

    assert "Unsupported cosmetic repair type" in str(exc.value)


def test_format_value_variants() -> None:
    assert ci_cosmetic_repair._format_value({"actual": 1.2345, "digits": 2}) == "1.23"
    assert ci_cosmetic_repair._format_value({"value": 10, "format": ".1f"}) == "10.0"
    assert ci_cosmetic_repair._format_value({"value": 7}) == "7"
    assert ci_cosmetic_repair._format_value({"value": "text"}) == "text"


def test_format_value_errors() -> None:
    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError):
        ci_cosmetic_repair._format_value({})
    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError):
        ci_cosmetic_repair._format_value({"actual": object()})


def test_load_failure_records_detects_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ci_cosmetic_repair,
        "classify_reports",
        lambda paths: {"cosmetic": [], "runtime": ["err"], "unknown": []},
    )

    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError):
        ci_cosmetic_repair.load_failure_records(Path("report.xml"))


def test_apply_tolerance_update_validates_guard(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("value = 1.0\n", encoding="utf-8")

    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError):
        ci_cosmetic_repair.apply_tolerance_update(target, guard="float", key=None, value="2.0")


def test_apply_tolerance_update_requires_numeric_literal(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("value = 'text'  # cosmetic-repair: float\n", encoding="utf-8")

    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError):
        ci_cosmetic_repair.apply_tolerance_update(target, guard="float", key=None, value="2.0")


def test_apply_snapshot_update_validates_guard(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.txt"
    target.write_text("no guard here", encoding="utf-8")

    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError):
        ci_cosmetic_repair.apply_snapshot_update(
            target, guard="snapshot", key=None, replacement="new"
        )


def test_apply_snapshot_update_with_key(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.txt"
    target.write_text("value\n# cosmetic-repair: snapshot expected\n", encoding="utf-8")

    changed = ci_cosmetic_repair.apply_snapshot_update(
        target,
        guard="snapshot",
        key="expected",
        replacement="updated\n# cosmetic-repair: snapshot expected\n",
    )

    assert changed is True
    assert target.read_text(encoding="utf-8").startswith("updated")


def test_working_tree_changes_parses_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, *, cwd, text, capture_output, check):
        return subprocess.CompletedProcess(cmd, 0, stdout=" M file1\n?? file2\n", stderr="")

    monkeypatch.setattr(ci_cosmetic_repair.subprocess, "run", fake_run)

    changes = ci_cosmetic_repair.working_tree_changes(root=Path("/tmp"))

    assert changes == ["M file1", "?? file2"]


def test_stage_and_commit_uses_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[tuple[str, ...], Path | None]] = []

    def fake_run(cmd, *, cwd=None):
        calls.append((tuple(cmd), cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    class FakeDateTime:
        @staticmethod
        def utcnow() -> dt_datetime:
            return dt_datetime(2024, 1, 2, 3, 4, 5)

    monkeypatch.setattr(ci_cosmetic_repair, "_run", fake_run)
    monkeypatch.setattr(ci_cosmetic_repair, "datetime", FakeDateTime)

    file_path = tmp_path / "tests" / "example.py"
    branch = ci_cosmetic_repair.stage_and_commit(
        [file_path], root=tmp_path, summary="summary", branch_suffix=None
    )

    assert branch == f"{ci_cosmetic_repair.BRANCH_PREFIX}-20240102030405"
    assert calls[0][0] == ("git", "checkout", "-B", branch)
    assert calls[1][0][:2] == ("git", "add")
    assert calls[2][0] == ("git", "commit", "-m", "Cosmetic repair: summary")


def test_push_and_open_pr_returns_last_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(cmd, *, cwd=None):
        calls.append(tuple(cmd))
        if cmd[0] == "gh":
            return subprocess.CompletedProcess(cmd, 0, stdout="first\n\nfinal\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ci_cosmetic_repair, "_run", fake_run)

    pr_url = ci_cosmetic_repair.push_and_open_pr(
        branch="branch",
        base="main",
        title="title",
        body="body",
        labels=("a", "b"),
        root=tmp_path,
    )

    assert calls[0] == ("git", "push", "--force", "origin", "branch")
    assert calls[1] == (
        "gh",
        "pr",
        "create",
        "--title",
        "title",
        "--body",
        "body",
        "--base",
        "main",
        "--head",
        "branch",
        "--label",
        "a",
        "--label",
        "b",
    )
    assert pr_url == "final"


def test_push_and_open_pr_handles_empty_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(cmd, *, cwd=None):
        if cmd[0] == "gh":
            return subprocess.CompletedProcess(cmd, 0, stdout="\n\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ci_cosmetic_repair, "_run", fake_run)

    result = ci_cosmetic_repair.push_and_open_pr(
        branch="branch",
        base="main",
        title="title",
        body="body",
        labels=(),
        root=tmp_path,
    )

    assert result == ""


def test_serialise_instructions(tmp_path: Path) -> None:
    instruction = ci_cosmetic_repair.RepairInstruction(
        kind="tolerance",
        path=Path("tests/example.py"),
        guard="float",
        key="EXPECTED",
        value="1.23",
        metadata={"value": 1.23},
        source="case",
    )

    payload = ci_cosmetic_repair._serialise_instructions([instruction])

    assert payload == [
        {
            "kind": "tolerance",
            "path": "tests/example.py",
            "guard": "float",
            "key": "EXPECTED",
            "source": "case",
            "metadata": {"value": 1.23},
        }
    ]


def test_write_summary_appends_timestamp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeDateTime:
        @staticmethod
        def now(tz):
            return dt_datetime(2024, 5, 6, 7, 8, 9, tzinfo=tz)

    monkeypatch.setattr(ci_cosmetic_repair, "datetime", FakeDateTime)

    ci_cosmetic_repair.write_summary(tmp_path, {"status": "ok"})

    data = json.loads((tmp_path / ci_cosmetic_repair.SUMMARY_FILE).read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    assert data["timestamp"] == "2024-05-06T07:08:09+00:00"


def test_build_pr_body_lists_changes(tmp_path: Path) -> None:
    changed = [tmp_path / "tests" / "example.py"]
    instruction = ci_cosmetic_repair.RepairInstruction(
        kind="tolerance",
        path=Path("tests/example.py"),
        guard="float",
        key="EXPECTED",
        value="1.23",
        metadata={},
        source="case",
    )

    body = ci_cosmetic_repair.build_pr_body(changed, [instruction], root=tmp_path)

    assert "- tests/example.py" in body
    assert "case: tolerance" in body


def test_main_exits_clean_when_pytest_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = tmp_path / ci_cosmetic_repair.DEFAULT_REPORT
    report.write_text("<testsuite/>", encoding="utf-8")

    monkeypatch.setattr(
        ci_cosmetic_repair,
        "run_pytest",
        lambda path, args: subprocess.CompletedProcess(["pytest"], 0, stdout="", stderr=""),
    )
    recorded: list[dict[str, object]] = []

    def fake_write_summary(root: Path, payload: dict[str, object]) -> None:
        recorded.append(payload)

    monkeypatch.setattr(ci_cosmetic_repair, "write_summary", fake_write_summary)

    exit_code = ci_cosmetic_repair.main(["--apply", "--root", str(tmp_path)])

    assert exit_code == 0
    assert recorded[-1]["status"] == "clean"


def test_main_requires_report_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ci_cosmetic_repair,
        "run_pytest",
        lambda path, args: subprocess.CompletedProcess(["pytest"], 1, stdout="", stderr=""),
    )

    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError):
        ci_cosmetic_repair.main(["--apply", "--root", str(tmp_path)])


def test_main_errors_when_pytest_failed_without_instructions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = tmp_path / ci_cosmetic_repair.DEFAULT_REPORT
    report.write_text("<testsuite/>", encoding="utf-8")

    monkeypatch.setattr(
        ci_cosmetic_repair,
        "run_pytest",
        lambda path, args: subprocess.CompletedProcess(["pytest"], 1, stdout="", stderr=""),
    )
    monkeypatch.setattr(ci_cosmetic_repair, "load_failure_records", lambda path: [])
    monkeypatch.setattr(ci_cosmetic_repair, "collect_instructions", lambda records: [])

    recorded: list[dict[str, object]] = []

    def fake_write_summary(root: Path, payload: dict[str, object]) -> None:
        recorded.append(payload)

    monkeypatch.setattr(ci_cosmetic_repair, "write_summary", fake_write_summary)

    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError):
        ci_cosmetic_repair.main(["--apply", "--root", str(tmp_path)])

    assert recorded[-1]["status"] == "error"


def test_main_handles_missing_instructions_without_pytest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = tmp_path / "custom.xml"
    report.write_text("<testsuite/>", encoding="utf-8")

    monkeypatch.setattr(ci_cosmetic_repair, "load_failure_records", lambda path: [])
    monkeypatch.setattr(ci_cosmetic_repair, "collect_instructions", lambda records: [])

    recorded: list[dict[str, object]] = []

    def fake_write_summary(root: Path, payload: dict[str, object]) -> None:
        recorded.append(payload)

    monkeypatch.setattr(ci_cosmetic_repair, "write_summary", fake_write_summary)

    exit_code = ci_cosmetic_repair.main(
        ["--dry-run", "--report", str(report), "--root", str(tmp_path)]
    )

    assert exit_code == 0
    assert recorded[-1]["status"] == "clean"


def test_main_creates_pr_when_requested(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = tmp_path / ci_cosmetic_repair.DEFAULT_REPORT
    report.write_text("<testsuite/>", encoding="utf-8")

    instruction = ci_cosmetic_repair.RepairInstruction(
        kind="tolerance",
        path=Path("tests/example.py"),
        guard="float",
        key="EXPECTED",
        value="1.23",
        metadata={},
        source="case",
    )

    monkeypatch.setattr(
        ci_cosmetic_repair,
        "run_pytest",
        lambda path, args: subprocess.CompletedProcess(["pytest"], 1, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        ci_cosmetic_repair,
        "load_failure_records",
        lambda path: [object()],
    )
    monkeypatch.setattr(
        ci_cosmetic_repair,
        "collect_instructions",
        lambda records: [instruction],
    )

    changed_path = tmp_path / "tests" / "example.py"
    monkeypatch.setattr(
        ci_cosmetic_repair,
        "apply_instructions",
        lambda instructions, root: [changed_path],
    )
    monkeypatch.setattr(
        ci_cosmetic_repair,
        "working_tree_changes",
        lambda root: ["M tests/example.py"],
    )

    monkeypatch.setattr(
        ci_cosmetic_repair,
        "stage_and_commit",
        lambda paths, root, summary, branch_suffix: "branch",
    )
    monkeypatch.setattr(
        ci_cosmetic_repair,
        "build_pr_body",
        lambda changed, instructions, root: "body",
    )
    monkeypatch.setattr(
        ci_cosmetic_repair,
        "push_and_open_pr",
        lambda **kwargs: "https://example.test/pr/1",
    )

    recorded: list[dict[str, object]] = []

    def fake_write_summary(root: Path, payload: dict[str, object]) -> None:
        recorded.append(payload)

    monkeypatch.setattr(ci_cosmetic_repair, "write_summary", fake_write_summary)

    exit_code = ci_cosmetic_repair.main(["--apply", "--root", str(tmp_path)])

    assert exit_code == 0
    assert recorded[-1]["status"] == "pr-created"
    assert recorded[-1]["pr_url"] == "https://example.test/pr/1"
