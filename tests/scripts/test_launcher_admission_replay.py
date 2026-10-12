"""Launcher mutation receipts must bind the selected assertion and preserve output."""

import runpy
import sys
from pathlib import Path

import pytest

REPLAY = (
    Path(__file__).resolve().parents[2] / "docs/evidence/issue-3743/launcher-admission/replay.py"
)


@pytest.mark.parametrize(
    "defect", [None, "wrong-module", "wrong-node", "error", "skip", "non-assertion"]
)
def test_replay_requires_selected_assertion_failure(tmp_path, defect):
    replay = runpy.run_path(str(REPLAY))
    module = replay["TEST"][:-3].replace("/", ".")
    name = f"{replay['NAME']}[root-missing]"
    outcome = (
        '<failure message="AssertionError: assert True is False">assert True is False</failure>'
    )
    if defect == "wrong-module":
        module = "tests.scripts.other"
    elif defect == "wrong-node":
        name = "test_other"
    elif defect == "error":
        outcome = '<error type="RuntimeError" />'
    elif defect == "skip":
        outcome = "<skipped />"
    elif defect == "non-assertion":
        outcome = '<failure type="RuntimeError" message="RuntimeError: assert True is False">assert True is False</failure>'
    report = tmp_path / "junit.xml"
    report.write_text(
        f'<testsuites><testsuite><testcase classname="{module}" name="{name}">'
        f"{outcome}</testcase></testsuite></testsuites>"
    )
    if defect:
        with pytest.raises(ValueError):
            replay["validate_junit"](report, "root-missing", "red")
    else:
        assert replay["validate_junit"](report, "root-missing", "red")["name"] == name


@pytest.mark.parametrize(
    "xml",
    [
        '<!DOCTYPE testsuites [<!ENTITY x "boom">]><testsuites>&x;</testsuites>',
        '<!DOCTYPE testsuites SYSTEM "file:///etc/passwd"><testsuites />',
    ],
)
def test_replay_rejects_xml_declarations(tmp_path, xml):
    replay = runpy.run_path(str(REPLAY))
    report = tmp_path / "junit.xml"
    report.write_text(xml)
    with pytest.raises(ValueError, match="declarations and external entities"):
        replay["validate_junit"](report, "root-missing", "red")


def test_output_reuse_fails_before_any_mutation(tmp_path, monkeypatch):
    replay = runpy.run_path(str(REPLAY))
    output = tmp_path / "proof"
    output.mkdir()
    retained = output / "receipts.json"
    original = b"existing proof must survive\n"
    retained.write_bytes(original)

    def unexpected_copy(*args, **kwargs):
        pytest.fail("output reuse reached private source copying")

    monkeypatch.setattr(replay["shutil"], "copyfile", unexpected_copy)
    monkeypatch.setattr(sys, "argv", [str(REPLAY), "--output", str(output)])
    with pytest.raises(FileExistsError):
        replay["main"]()
    assert retained.read_bytes() == original
    assert list(output.iterdir()) == [retained]
