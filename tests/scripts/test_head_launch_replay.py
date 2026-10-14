"""Mutation proof must bind the head verdict assertion and reject output reuse."""

import runpy
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

REPLAY = Path(__file__).resolve().parents[2] / "docs/evidence/issue-3743/head-launch/replay.py"
VERDICT_ASSERTION = "assert 'PASS' == 'FAIL_BROKEN'"


@pytest.fixture
def replay():
    return runpy.run_path(str(REPLAY))


def write_report(path, replay, phase, *, message=None, detail=None):
    tree = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(
        tree, "testsuite", tests="1", failures=str(int(phase == "red")), errors="0", skipped="0"
    )
    case = ElementTree.SubElement(
        suite,
        "testcase",
        classname=replay["TEST"][:-3].replace("/", "."),
        name=f"{replay['NAME']}[root-missing]",
    )
    if phase == "red":
        failure = ElementTree.SubElement(
            case,
            "failure",
            type="AssertionError",
            message=(
                message if message is not None else VERDICT_ASSERTION + "\n- FAIL_BROKEN\n+ PASS"
            ),
        )
        failure.text = detail if detail is not None else "AssertionError: " + VERDICT_ASSERTION
    ElementTree.ElementTree(tree).write(path, encoding="utf-8")


@pytest.mark.parametrize("phase", ["red", "green"])
def test_selected_verdict_assertion_and_restored_pass_are_admitted(tmp_path, replay, phase):
    report = tmp_path / "proof.xml"
    write_report(report, replay, phase)
    assert replay["validate_junit"](report, "root-missing", phase)["name"] == (
        f"{replay['NAME']}[root-missing]"
    )


@pytest.mark.parametrize(
    ("message", "detail"),
    [
        ("assert 'other' == 'FAIL_BROKEN'", "AssertionError: assert 'other' == 'FAIL_BROKEN'"),
        ("assert False", "assert result['verdict'] == 'FAIL_BROKEN'\nassert False"),
        ("assert 'FAIL_BROKEN' == 'PASS'", "AssertionError: assert 'FAIL_BROKEN' == 'PASS'"),
        (VERDICT_ASSERTION + " and False", "AssertionError: " + VERDICT_ASSERTION + " and False"),
        (VERDICT_ASSERTION, "assert False\nFAIL_BROKEN appeared in fixture setup"),
        (VERDICT_ASSERTION, ""),
    ],
)
def test_unrelated_assertion_cannot_count_as_mutation_detection(tmp_path, replay, message, detail):
    report = tmp_path / "proof.xml"
    write_report(report, replay, "red", message=message, detail=detail)
    with pytest.raises(ValueError, match="intended admission assertion"):
        replay["validate_junit"](report, "root-missing", "red")


def test_output_reuse_preserves_every_file_before_private_copy(tmp_path, monkeypatch, replay):
    output = tmp_path / "proof"
    output.mkdir()
    (output / "nested").mkdir()
    (output / "receipts.json").write_bytes(b"original receipt\r\n")
    (output / "nested" / "source.py.txt").write_bytes(b"original source\r\n")
    before = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}

    def unexpected_copy(*args, **kwargs):
        pytest.fail("reuse must be rejected before copying or mutating source")

    monkeypatch.setattr(replay["shutil"], "copyfile", unexpected_copy)
    monkeypatch.setattr(sys, "argv", [str(REPLAY), "--output", str(output)])
    with pytest.raises(FileExistsError):
        replay["main"]()
    assert {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    } == before
