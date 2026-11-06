"""Check the merged-main shebang-rejection inspection record."""

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-3743/shebang-rejection"
INSPECTOR = EVIDENCE / "inspect_main_acceptance.py"
MAP_PATH = EVIDENCE / "main-acceptance-map.json"
PRE_PATH = EVIDENCE / "pre-change-record.json"
INSPECTED_MAIN = "7ab99d09429a3b35aa55f7744f8c75b467f42536"


@pytest.fixture(scope="module")
def inspector():
    return runpy.run_path(str(INSPECTOR))


def test_historical_archives_verify_and_current_bindings_do_not(inspector):
    archives = inspector["historical_archives"](ROOT)
    assert [item["verified"] for item in archives] == [True, True, True]
    rows = inspector["binding_rows"](ROOT)
    assert rows
    assert all(
        row["archive_copy_matches_summary"] is not False
        for row in rows
        if row["archive_copy_sha256"] is not None
    )
    shebang_gaps = [
        row for row in rows if row["path"] == inspector["TEST"] and row["status"] == "mismatch"
    ]
    assert len(shebang_gaps) == 3
    helpers = inspector["production_helpers"](ROOT)
    assert helpers["equal_each_other"] is True
    assert helpers["root_equals_origin_main"] is True
    assert helpers["template_equals_origin_main"] is True
    contract = inspector["test_contract"](ROOT)
    assert contract["declared_cases_present"] is True
    assert contract["real_executable_file"] is True
    assert contract["no_available_probe"] is True
    assert contract["unmanaged_runtime"] is True
    assert contract["unsuccessful_probe"] is True
    replay = inspector["replay_contract"](ROOT)
    assert replay["anchors_unique"] is True
    assert replay["claims_output_before_copy"] is True
    assert replay["restores_original_bytes"] is True


def test_recorded_map_names_main_commit_and_acceptance_gaps(inspector):
    report = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    pre_change = json.loads(PRE_PATH.read_text(encoding="utf-8"))
    assert report["pre_change"] == pre_change
    assert report["inspected_main"] == {
        "ref": "origin/main",
        "commit": INSPECTED_MAIN,
        "committed_at": report["inspected_main"]["committed_at"],
        "subject": report["inspected_main"]["subject"],
    }
    assert report["inspected_main"]["subject"]
    assert report["check_date"] == "2026-11-06"
    assert pre_change["check_date"] == "2026-11-06"
    assert "Attempt each literal acceptance command at most once." in pre_change["stop_rule"]
    assert pre_change["focused_limit_seconds"] == 120
    assert pre_change["protected_files_edited_before_record"] is False
    assert [item["argv"] for item in pre_change["literal_commands"]] == [
        list(argv) for argv in inspector["LITERAL_COMMANDS"]
    ]
    assert [item["exit"] for item in pre_change["literal_commands"]] == [127, 127]
    assert [item["stopped"] for item in pre_change["literal_commands"]] == [
        "interpreter-absent",
        "interpreter-absent",
    ]
    operational = pre_change["operational_pytest"]
    assert operational["exit"] == 0
    assert operational["passed"] == 8
    assert operational["junit"] == {"tests": 8, "failures": 0, "errors": 0, "skipped": 0}
    assert operational["under_two_minutes"] is True
    assert operational["satisfies_literal_interpreter"] is False
    acceptance = report["acceptance"]
    assert [item["id"] for item in acceptance] == [item["id"] for item in inspector["REQUIREMENTS"]]
    assert {item["disposition"] for item in acceptance} == {"gap"}
    assert all(item["gap"] and item["verified_evidence"] for item in acceptance)
    replay = report["replay_confirmation"]
    assert replay["exit"] == 0
    assert replay["satisfies_literal_interpreter"] is False
    assert len(replay["pairs"]) == 8
    assert all(
        pair["red_exit"] == 1
        and pair["green_exit"] == 0
        and pair["restored_matches_original"] is True
        and pair["mutant_differs"] is True
        for pair in replay["pairs"]
    )
    assert replay["reuse"]["exit"] != 0
    assert replay["reuse"]["proof_files_unchanged"] is True
    assert replay["reuse"]["proof_file_count"] == 93
    assert all(item["verified"] for item in report["archives"])
    assert report["helpers"]["equal_each_other"] is True
    assert report["historical_tree"]["match_origin_main"] is True


def test_focused_acceptance_path_passes_eight_under_two_minutes(inspector):
    outcome = inspector["run_focused_pytest"](ROOT)
    assert outcome["exit"] == 0
    assert outcome["passed"] == 8
    assert outcome["junit"]["tests"] == 8
    assert outcome["junit"]["failures"] == 0
    assert outcome["junit"]["errors"] == 0
    assert outcome["junit"]["skipped"] == 0
    assert outcome["under_two_minutes"] is True
    assert outcome["duration_seconds"] < 120
    assert "skipped" not in outcome["summary_line"]
    assert "error" not in outcome["summary_line"]


def test_literal_commands_stop_when_interpreter_is_absent(inspector):
    interpreter = Path(inspector["LITERAL_COMMANDS"][0][0])
    if interpreter.is_file():
        pytest.skip("literal interpreter is present; absence was recorded on the inspection runner")
    proof = Path("/tmp/fresh-shebang-rejection-proof")
    existed = proof.exists()
    attempts = [
        inspector["attempt_literal_command"](ROOT, list(argv))
        for argv in inspector["LITERAL_COMMANDS"]
    ]
    assert [item["exit"] for item in attempts] == [127, 127]
    assert [item["stopped"] for item in attempts] == ["interpreter-absent", "interpreter-absent"]
    assert proof.exists() is existed
