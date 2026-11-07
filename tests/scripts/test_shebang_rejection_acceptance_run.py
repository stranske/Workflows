"""Verify retained shebang-rejection acceptance command and mutation receipts."""

import json
import runpy
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-3743/shebang-rejection"
CAPTURE = EVIDENCE / "capture_acceptance_run.py"
RUN = EVIDENCE / "acceptance-run"


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
    assert summary["cwd"]
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


@pytest.mark.parametrize("defect", ["pytest", "replay", "junit", "validation", "promotion", None])
def test_capture_preserves_prior_tree_until_staged_validation_succeeds(
    tmp_path, monkeypatch, defect
):
    module = load_capture()
    root = tmp_path / "repo"
    for relative in module["HISTORICAL"]:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    run_dir = root / module["EVIDENCE"] / "acceptance-run"
    shutil.copytree(RUN, run_dir)
    before = module["file_hashes"](run_dir)
    namespace = module["capture"].__globals__
    specified = tmp_path / "literal-proof"
    monkeypatch.setitem(namespace, "SPECIFIED_OUTPUT", specified)

    def run_command(argv, cwd, timeout):
        record = {
            "argv": argv,
            "cwd": str(cwd),
            "exit": 0,
            "stopped": None,
            "stdout": "8 passed\n",
            "stderr": "",
        }
        if "--output" in argv:
            output = Path(argv[-1])
            if defect == "replay" or output.exists():
                record.update(exit=1, stderr="File exists: injected replay failure\n")
            else:
                shutil.copytree(RUN / "mutation-proof", output)
        elif any(arg.startswith("--junitxml=") for arg in argv):
            output = Path(argv[-1].split("=", 1)[1])
            shutil.copyfile(RUN / "focused.xml", output)
            if defect == "junit":
                output.write_text("<testsuites/>")
        elif defect == "pytest":
            record.update(exit=1, stderr="injected pytest failure\n")
        return record

    monkeypatch.setitem(namespace, "run_command", run_command)
    validate = namespace["validate_retained"]
    validated = []

    def validate_staged(check_root, staged=None):
        assert module["file_hashes"](run_dir) == before
        assert staged != run_dir
        result = validate(check_root, staged)
        validated.append(staged)
        if defect == "validation":
            raise AssertionError("injected validation failure")
        return result

    monkeypatch.setitem(namespace, "validate_retained", validate_staged)
    rename = Path.rename

    def fail_promotion(path, target):
        if defect == "promotion" and path.name == "acceptance-run" and path != run_dir:
            raise OSError("injected promotion failure")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_promotion)
    if defect is None:
        module["capture"](root)
        assert validated
        assert not list(run_dir.parent.glob(".acceptance-attempt-*"))
        assert validate(root)["satisfies_literal_acceptance"] is True
    else:
        with pytest.raises((AssertionError, RuntimeError, OSError)):
            module["capture"](root)
        assert module["file_hashes"](run_dir) == before
        attempts = list(run_dir.parent.glob(".acceptance-attempt-*"))
        assert len(attempts) == 1
        failure = json.loads((attempts[0] / "failure.json").read_text())
        assert failure["error"]
        assert (attempts[0] / "acceptance-run/literal-pytest.json").is_file()
        assert not (attempts[0] / "previous").exists()
