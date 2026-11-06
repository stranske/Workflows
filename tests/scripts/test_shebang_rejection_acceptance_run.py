"""Verify retained shebang-rejection acceptance command and mutation receipts."""

import json
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-3743/shebang-rejection"
CAPTURE = EVIDENCE / "capture_acceptance_run.py"
RUN = EVIDENCE / "acceptance-run"
HISTORICAL_MAIN_PATHS = (
    "docs/evidence/issue-3743/shebang-rejection/README.md",
    "docs/evidence/issue-3743/shebang-rejection/coverage.ini",
    "docs/evidence/issue-3743/shebang-rejection/replay.py",
    "docs/evidence/issue-3743/shebang-rejection/summary.json",
    "docs/evidence/issue-3743/shebang-rejection/proof.tar.gz",
    "docs/evidence/issue-3743/shebang-rejection/path-lookup/summary.json",
    "docs/evidence/issue-3743/shebang-rejection/path-lookup/proof.tar.gz",
    "docs/evidence/issue-3743/shebang-rejection/replay-validation/summary.json",
    "docs/evidence/issue-3743/shebang-rejection/replay-validation/proof.tar.gz",
    "docs/evidence/issue-3743/shebang-rejection/replay-validation/task-reconciliation.md",
    "scripts/check_deliberate_break.py",
    "templates/consumer-repo/scripts/check_deliberate_break.py",
    "tests/scripts/test_check_deliberate_break_shebang_rejection.py",
    "tests/scripts/test_shebang_rejection_replay.py",
)


def load_capture():
    return runpy.run_path(str(CAPTURE))


def test_literal_command_shapes_reserve_the_specified_output():
    module = load_capture()
    assert module["literal_pytest_argv"]() == [
        "/opt/anaconda3/bin/python3",
        "-m",
        "pytest",
        "tests/scripts/test_check_deliberate_break_shebang_rejection.py",
        "-q",
        "-o",
        "addopts=",
    ]
    assert module["literal_replay_argv"]() == [
        "/opt/anaconda3/bin/python3",
        "docs/evidence/issue-3743/shebang-rejection/replay.py",
        "--output",
        "/tmp/fresh-shebang-rejection-proof",
    ]


def test_missing_interpreter_is_recorded_without_creating_output(tmp_path):
    module = load_capture()
    output = tmp_path / "fresh-shebang-rejection-proof"
    missing = tmp_path / "missing-python"
    record = module["run_command"](
        [str(missing), "replay.py", "--output", str(output)],
        tmp_path,
        30,
    )
    assert record["exit"] == 127
    assert record["stopped"] == "interpreter-absent"
    assert record["cwd"] == str(tmp_path)
    assert record["stderr"] == f"{missing}: No such file or directory\n"
    assert output.exists() is False


def test_run_command_records_cwd_exit_and_console(tmp_path):
    module = load_capture()
    record = module["run_command"]([sys.executable, "-c", "print('ok')"], tmp_path, 30)
    assert record["exit"] == 0
    assert record["stopped"] is None
    assert record["cwd"] == str(tmp_path)
    assert record["stdout"] == "ok\n"


def test_additional_replay_output_is_not_the_reserved_directory():
    module = load_capture()
    destination = module["additional_replay_output"]()
    try:
        assert destination.name == "proof"
        assert destination.exists() is False
        assert destination.resolve() != module["SPECIFIED_OUTPUT"].resolve()
    finally:
        if destination.parent.exists():
            destination.parent.rmdir()


def test_retained_receipts_match_the_acceptance_run_contract():
    module = load_capture()
    summary = module["validate_retained"](ROOT)
    assert summary["cwd"] == str(ROOT)
    assert summary["check_date"]
    assert summary["pair_count"] == 8
    assert summary["literal_pytest_exit"] == 0
    assert summary["literal_replay_exit"] == 0
    assert summary["satisfies_literal_acceptance"] is True
    assert summary["operational_pytest_exit"] == 0
    assert summary["focused_junit_exit"] == 0
    assert summary["replay_exit"] == 0
    assert summary["reuse_exit"] != 0
    assert summary["receipt_interpreter"] == "/opt/anaconda3/bin/python3"
    assert summary["historical_unchanged"] is True

    literal_pytest = json.loads((RUN / "literal-pytest.json").read_text(encoding="utf-8"))
    assert literal_pytest["argv"] == module["literal_pytest_argv"]()
    assert literal_pytest["exit"] == 0
    assert "8 passed" in literal_pytest["stdout"]
    assert "failed" not in literal_pytest["stdout"]
    assert "error" not in literal_pytest["stdout"]
    assert "skipped" not in literal_pytest["stdout"]
    report = module["junit_report"](RUN / "focused.xml")
    assert report["tests"] == 8
    assert report["failures"] == report["errors"] == report["skipped"] == 0
    focused = json.loads((RUN / "focused-junit.json").read_text(encoding="utf-8"))
    assert focused["argv"][0] == summary["receipt_interpreter"]
    test_rel = "tests/scripts/test_check_deliberate_break_shebang_rejection.py"
    assert summary["historical_sha256"][test_rel] == module["digest"](
        (ROOT / test_rel).read_bytes()
    )

    specified = json.loads((RUN / "specified-destination.json").read_text(encoding="utf-8"))
    assert specified["created_by_this_run"] is True
    assert specified["explicit_reuse_checked"] is True
    assert specified["exists_after"] is True
    assert specified["additional_output"] is None
    assert (RUN / "additional-replay.json").exists() is False
    reuse = json.loads((RUN / "reuse-audit.json").read_text(encoding="utf-8"))
    assert reuse["argv"][0] == summary["receipt_interpreter"]
    assert reuse["output"] == str(module["SPECIFIED_OUTPUT"])
    assert reuse["all_bytes_unchanged"] is True
    assert "8 passed" in (RUN / "operational-pytest.stdout").read_text(encoding="utf-8")
    assert (RUN / "focused.xml").is_file()
    assert (RUN / "mutation-proof" / "summary.json").is_file()

    diff = subprocess.run(
        ["git", "diff", "--exit-code", "origin/main", "--", *HISTORICAL_MAIN_PATHS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert diff.returncode == 0, diff.stdout + diff.stderr
