"""The standalone replay reads JUnit without permitting DTDs or entity declarations."""

import runpy
from pathlib import Path

import pytest


@pytest.fixture
def parse_junit():
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / "docs/evidence/issue-3743/shebang-rejection/replay.py"))[
        "parse_junit"
    ]


def test_replay_reads_pytest_junit(parse_junit, tmp_path):
    report = tmp_path / "junit.xml"
    report.write_bytes(
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<testsuites><testsuite><testcase name="test_rejection[root]" '
        b'classname="tests.scripts.test_rejection" /></testsuite></testsuites>'
    )
    cases = list(parse_junit(report).iter("testcase"))
    assert len(cases) == 1
    assert cases[0].attrib == {
        "name": "test_rejection[root]",
        "classname": "tests.scripts.test_rejection",
    }


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
@pytest.mark.parametrize(
    "declaration",
    [
        '<!DOCTYPE testsuites SYSTEM "file:///must-not-be-read">',
        '<!DOCTYPE testsuites [<!ENTITY probe "must-not-expand">]>',
        '<!DOCTYPE testsuites [<!ENTITY probe SYSTEM "file:///must-not-be-read">]>',
    ],
)
def test_replay_rejects_dtd_before_processing_entities(
    parse_junit, tmp_path, encoding, declaration
):
    report = tmp_path / "junit.xml"
    report.write_bytes(
        (f'<?xml version="1.0" encoding="{encoding}"?>' + declaration + "<testsuites/>").encode(
            encoding
        )
    )
    with pytest.raises(ValueError, match="must not contain DTDs or entity declarations"):
        parse_junit(report)
