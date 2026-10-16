"""Exercise the standalone replay's result validation and private-copy boundary."""

import json
import runpy
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def replay_module():
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / "docs/evidence/issue-3743/shebang-rejection/replay.py"))


@pytest.fixture
def parse_junit(replay_module):
    return replay_module["parse_junit"]


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


@pytest.mark.parametrize(
    "phase,override",
    [
        pytest.param("red", {"exit": 0}, id="red-exit"),
        pytest.param("red", {"name": "test_other[root]"}, id="wrong-test"),
        pytest.param("red", {"name": "test_rejection[template]"}, id="wrong-parameter"),
        pytest.param("red", {"module": "tests.scripts.test_other"}, id="wrong-module"),
        pytest.param("red", {"children": "<failure>RuntimeError</failure>"}, id="non-assertion"),
        pytest.param("red", {"children": "<error>AssertionError</error>"}, id="error"),
        pytest.param("red", {"children": "<skipped/>"}, id="red-skip"),
        pytest.param(
            "red", {"children": "<failure>AssertionError</failure>" * 2}, id="two-failures"
        ),
        pytest.param("red", {"extra_case": '<testcase name="extra"/>'}, id="two-cases"),
        pytest.param("green", {"exit": 1}, id="green-exit"),
        pytest.param(
            "green", {"children": "<failure>AssertionError</failure>"}, id="green-failure"
        ),
        pytest.param("green", {"children": "<skipped/>"}, id="green-skip"),
    ],
)
def test_replay_rejects_invalid_node_results(replay_module, monkeypatch, tmp_path, phase, override):
    result = {
        "exit": 1 if phase == "red" else 0,
        "name": "test_rejection[root]",
        "module": "tests.scripts.test_rejection",
        "children": "<failure>AssertionError</failure>" if phase == "red" else "",
        "extra_case": "",
        **override,
    }

    def run(argv, **kwargs):
        report = Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--junitxml=")))
        report.write_text(
            '<testsuites><testsuite><testcase name="{name}" classname="{module}">'
            "{children}</testcase>{extra_case}</testsuite></testsuites>".format(**result),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            argv, result["exit"], "captured stdout", "captured stderr"
        )

    monkeypatch.setattr(replay_module["subprocess"], "run", run)
    with pytest.raises(AssertionError):
        replay_module["run_node"](
            tmp_path, tmp_path, "tests/scripts/test_rejection.py::test_rejection[root]", phase
        )


def test_replay_restores_private_source_when_red_validation_fails(
    replay_module, monkeypatch, tmp_path
):
    root = Path(__file__).resolve().parents[2]
    helper = replay_module["HELPER"]
    original = (root / helper).read_bytes()
    checkout = tmp_path / "checkout"

    class PrivateCheckout:
        def __init__(self, **kwargs):
            checkout.mkdir()

        def __enter__(self):
            return str(checkout)

        def __exit__(self, *args):
            return False

    def reject_red(private_root, output, node, phase):
        assert private_root == checkout and phase == "red"
        assert (checkout / helper).read_bytes() != original
        raise AssertionError("invalid RED result")

    monkeypatch.setattr(replay_module["tempfile"], "TemporaryDirectory", PrivateCheckout)
    monkeypatch.setitem(replay_module["replay"].__globals__, "run_node", reject_red)
    with pytest.raises(AssertionError, match="invalid RED result"):
        replay_module["replay"](root, tmp_path / "proof")
    assert (checkout / helper).read_bytes() == original
    assert (root / helper).read_bytes() == original


def test_replay_runs_eight_pairs_and_rejects_reuse_before_copying(
    replay_module, monkeypatch, tmp_path
):
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "proof"
    summary = replay_module["replay"](root, output)
    expected = {
        f"{replay_module['TEST']}::{name}[{case}]"
        for name in replay_module["MUTATIONS"]
        for case in ("root", "template")
    }
    assert summary["pair_count"] == len(summary["pairs"]) == 8
    assert {pair["node"] for pair in summary["pairs"]} == expected
    for pair in summary["pairs"]:
        case = "root" if pair["source"] == replay_module["HELPER"] else "template"
        name = pair["node"].split("::")[1].split("[")[0]
        directory = output / f"{case}-{name}"
        original = (directory / "original.py").read_bytes()
        assert original == (directory / "restored.py").read_bytes()
        assert original == (root / pair["source"]).read_bytes()
        assert original != (directory / "mutant.py").read_bytes()
        for phase, exit_code in (("red", 1), ("green", 0)):
            assert pair[phase]["exit"] == exit_code
            assert json.loads((directory / f"{phase}.json").read_text()) == pair[phase]

    before = {
        path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()
    }
    assert len(before) == 93

    def unexpected_copy_or_checkout(*args, **kwargs):
        pytest.fail("output reuse must reject before copying or creating a checkout")

    monkeypatch.setattr(replay_module["shutil"], "copyfile", unexpected_copy_or_checkout)
    monkeypatch.setattr(
        replay_module["tempfile"], "TemporaryDirectory", unexpected_copy_or_checkout
    )
    with pytest.raises(FileExistsError):
        replay_module["replay"](root, output)
    after = {
        path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()
    }
    assert after == before
