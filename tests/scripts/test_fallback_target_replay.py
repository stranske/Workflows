"""Fallback mutation proof rejects JUnit that does not prove the selected verdict."""

import runpy
from pathlib import Path
from xml.etree import ElementTree

import pytest

REPLAY = (
    Path(__file__).resolve().parents[2]
    / "docs/evidence/issue-3743/fallback-target-selection/replay.py"
)
LABELS = ["root-blank-target", "root-yaml-target", "template-blank-target", "template-yaml-target"]


@pytest.fixture
def replay():
    return runpy.run_path(str(REPLAY))


def report_tree(replay, label="root-blank-target", phase="red"):
    suite = ElementTree.Element(
        "testsuite", tests="1", failures=str(int(phase == "red")), errors="0", skipped="0"
    )
    case = ElementTree.SubElement(
        suite,
        "testcase",
        classname=replay["TEST"][:-3].replace("/", "."),
        name=f"{replay['NAME']}[{label}]",
    )
    if phase == "red":
        assertion = replay["FAILURE_ASSERTIONS"][label.split("-", 1)[1]]
        failure = ElementTree.SubElement(case, "failure", type="AssertionError", message=assertion)
        failure.text = f"E   {assertion}\n{replay['TEST']}:42: AssertionError"
    return suite, case


def write_report(tmp_path, suite):
    report = tmp_path / "proof.xml"
    ElementTree.ElementTree(suite).write(report, encoding="utf-8")
    return report


@pytest.mark.parametrize("label", LABELS)
@pytest.mark.parametrize("phase", ["red", "green"])
def test_exact_selected_assertion_and_restored_pass_are_accepted(tmp_path, replay, label, phase):
    suite, case = report_tree(replay, label, phase)
    assert replay["validate_junit"](write_report(tmp_path, suite), label, phase) == case.attrib


@pytest.mark.parametrize(
    ("attribute", "value", "reason"),
    [
        ("name", "test_unrelated[root-blank-target]", "wrong selected case"),
        (
            "name",
            "test_fallback_selects_the_implementation_target[template-blank-target]",
            "wrong selected case",
        ),
        ("classname", "tests.test_other", "wrong test module"),
    ],
)
def test_wrong_selected_case_is_rejected(tmp_path, replay, attribute, value, reason):
    suite, case = report_tree(replay)
    case.set(attribute, value)
    with pytest.raises(ValueError, match=reason):
        replay["validate_junit"](write_report(tmp_path, suite), "root-blank-target", "red")


@pytest.mark.parametrize("phase", ["red", "green"])
@pytest.mark.parametrize("outcome", ["error", "skipped"])
def test_error_or_skip_cannot_prove_detection_even_with_forged_totals(
    tmp_path, replay, phase, outcome
):
    suite, case = report_tree(replay, phase=phase)
    ElementTree.SubElement(case, outcome, message="setup failed or case not executed")
    with pytest.raises(ValueError, match="unexpected or misplaced JUnit outcomes"):
        replay["validate_junit"](write_report(tmp_path, suite), "root-blank-target", phase)


@pytest.mark.parametrize("label", LABELS)
@pytest.mark.parametrize("changed_field", ["message", "text", "type"])
def test_unrelated_assertion_failure_is_rejected(tmp_path, replay, label, changed_field):
    suite, case = report_tree(replay, label)
    failure = case.find("failure")
    if changed_field == "text":
        failure.text = f"E   assert False\n{replay['TEST']}:42: AssertionError"
    else:
        failure.set(changed_field, "assert False" if changed_field == "message" else "ValueError")
    with pytest.raises(ValueError, match="intended target-selection assertion"):
        replay["validate_junit"](write_report(tmp_path, suite), label, "red")
