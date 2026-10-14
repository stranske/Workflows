"""The finding replay accepts ordinary JUnit but rejects XML entity expansion."""

import importlib.util
from pathlib import Path

import pytest

REPLAY_PATH = (
    Path(__file__).resolve().parents[2] / "docs/evidence/issue-3835-evidence-destinations/replay.py"
)
SPEC = importlib.util.spec_from_file_location("evidence_destination_replay", REPLAY_PATH)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def test_replay_reads_ordinary_junit(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_text('<testsuite><testcase name="ordinary"/></testsuite>')
    assert replay.junit_counts(junit) == (1, 0, 0)


@pytest.mark.parametrize(
    "declaration",
    [
        '<!DOCTYPE testsuite [<!ENTITY proof "expanded">]>',
        '<!DOCTYPE testsuite SYSTEM "file:///forbidden-external.dtd">',
        '<!DOCTYPE testsuite [<!ENTITY proof SYSTEM "file:///forbidden-entity">]>',
    ],
)
def test_replay_rejects_entity_expansion(tmp_path, declaration):
    junit = tmp_path / "junit.xml"
    junit.write_text(declaration + '<testsuite><testcase name="&proof;"/></testsuite>')
    with pytest.raises(ValueError, match="DTDs and entities are forbidden"):
        replay.junit_counts(junit)
