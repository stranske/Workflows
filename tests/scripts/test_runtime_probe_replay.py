"""Reject runtime mutation receipts that do not prove the named test ran."""

import runpy
from pathlib import Path

import pytest


@pytest.fixture
def validate():
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / "docs/evidence/issue-3743/runtime-probes/replay.py"))[
        "validate_junit"
    ]


def report(
    *,
    name="probe[root]",
    classname="tests.scripts.private",
    failures=1,
    errors=0,
    skipped=0,
    outcome="<failure />",
):
    return (
        f'<testsuites><testsuite tests="1" failures="{failures}" errors="{errors}" '
        f'skipped="{skipped}"><testcase classname="{classname}" name="{name}">'
        f"{outcome}</testcase>"
        "</testsuite></testsuites>"
    )


def test_replay_accepts_only_executed_red_failure_and_green_pass(validate):
    node = "tests/scripts/private.py::probe[root]"
    assert validate(report(), node, "red") == {
        "tests": 1,
        "failures": 1,
        "errors": 0,
        "skipped": 0,
    }
    assert validate(report(failures=0, outcome=""), node, "green") == {
        "tests": 1,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }


def test_replay_rejects_errors_and_skips_even_with_failure_exit(validate):
    for invalid in (
        report(failures=0, errors=1, outcome="<error />"),
        report(failures=0, skipped=1, outcome="<skipped />"),
    ):
        with pytest.raises(AssertionError):
            validate(invalid, "tests/scripts/private.py::probe[root]", "red")


def test_replay_rejects_wrong_case_and_inconsistent_outcome(validate):
    for invalid in (report(name="other[root]"), report(outcome="<error />")):
        with pytest.raises(AssertionError):
            validate(invalid, "tests/scripts/private.py::probe[root]", "red")


def test_replay_rejects_same_named_case_from_another_module(validate):
    node = "tests/scripts/private.py::probe[root]"
    for phase in ("red", "green"):
        xml = report(
            classname="tests.scripts.other",
            failures=int(phase == "red"),
            outcome="<failure />" if phase == "red" else "",
        )
        with pytest.raises(AssertionError):
            validate(xml, node, phase)
