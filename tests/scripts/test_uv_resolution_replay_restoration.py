"""Failed replay proofs must restore private sources without claiming acceptance."""

import importlib.util
import json
import subprocess
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from xml.etree import ElementTree

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "docs/evidence/issue-3743/uv-resolution/replay_uv_resolution.py"


@pytest.fixture
def private_replay(tmp_path, monkeypatch):
    # Only fixed synthetic XML is parsed here. The real replay keeps defusedxml;
    # this fixture does not test XML hardening or need that site dependency.
    monkeypatch.setitem(sys.modules, "defusedxml", types.SimpleNamespace(ElementTree=ElementTree))
    spec = importlib.util.spec_from_file_location("uv_replay_restoration", DRIVER)
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    relatives = [replay.TEST, replay.HELPER, "templates/consumer-repo/" + replay.HELPER]
    caller_bytes = {relative: (ROOT / relative).read_bytes() for relative in relatives}
    tree = tmp_path / "private-tree"
    output = tmp_path / "reports"

    @contextmanager
    def private_tree(*, prefix):
        assert prefix == "uv-resolution-proof-"
        tree.mkdir()
        yield str(tree)

    monkeypatch.setattr(replay.tempfile, "TemporaryDirectory", private_tree)
    monkeypatch.setattr(sys, "argv", [str(DRIVER), "--output", str(output)])
    return replay, tree, output, caller_bytes


@pytest.mark.parametrize("copy", ["root", "template"])
@pytest.mark.parametrize("phase", ["red", "green"])
@pytest.mark.parametrize("failure", ["timeout", "invalid-proof"])
def test_failed_replay_restores_both_private_helpers(
    private_replay, monkeypatch, copy, phase, failure
):
    replay, tree, output, caller_bytes = private_replay
    error = (
        subprocess.TimeoutExpired([sys.executable, "-m", "pytest"], 120)
        if failure == "timeout"
        else ValueError("invalid proof: injected JUnit rejection")
    )
    calls = []

    def run_case(private, reports, node, proof_phase):
        assert private == tree
        assert reports.parent == output
        selected_copy = "template" if "[template-" in node else "root"
        prefix = "templates/consumer-repo/" if selected_copy == "template" else ""
        relative = prefix + replay.HELPER
        source = tree / relative
        if proof_phase == "red":
            assert source.read_bytes() != caller_bytes[relative]
        else:
            assert source.read_bytes() == caller_bytes[relative]
        calls.append((selected_copy, proof_phase))
        if (selected_copy, proof_phase) == (copy, phase):
            raise error
        return {"node": node, "exit": int(proof_phase == "red")}

    monkeypatch.setattr(replay, "run_case", run_case)
    with pytest.raises(type(error)) as caught:
        replay.main()

    assert caught.value is error
    assert calls[-1] == (copy, phase)
    assert not (output / "controls.json").exists()
    for relative, original in caller_bytes.items():
        assert (tree / relative).read_bytes() == original
        assert (ROOT / relative).read_bytes() == original


@pytest.mark.parametrize("copy", ["root", "template"])
@pytest.mark.parametrize("phase", ["red", "green"])
@pytest.mark.parametrize("failure", ["outcome", "identity", "malformed-xml", "timeout"])
def test_junit_rejection_restores_private_helpers(
    private_replay, monkeypatch, copy, phase, failure
):
    replay, tree, output, caller_bytes = private_replay
    calls = []

    def subprocess_result(argv, **kwargs):
        # Keep main() and run_case() real: only the pytest process result is
        # synthetic, joining proof validation to restoration in one control.
        xml = Path(
            next(arg.removeprefix("--junitxml=") for arg in argv if arg.startswith("--junitxml="))
        )
        proof_phase = xml.stem
        node = argv[3]
        selected_copy = "template" if "[template-" in node else "root"
        prefix = "templates/consumer-repo/" if selected_copy == "template" else ""
        relative = prefix + replay.HELPER
        assert kwargs["cwd"] == tree
        if proof_phase == "green":
            assert (tree / relative).read_bytes() == caller_bytes[relative]
        else:
            assert (tree / relative).read_bytes() != caller_bytes[relative]
        calls.append((selected_copy, proof_phase))
        rejecting = (selected_copy, proof_phase) == (copy, phase)
        if rejecting and failure == "timeout":
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        name = "wrong" if rejecting and failure == "identity" else node.rsplit("::", 1)[-1]
        failed = proof_phase == "red"
        if rejecting and failure == "outcome":
            failed = not failed
        case = f'<testcase name="{name}">' + ("<failure/>" if failed else "") + "</testcase>"
        report = "<testsuite>" + case + "</testsuite>"
        xml.write_text("<testsuite>" if rejecting and failure == "malformed-xml" else report)
        return types.SimpleNamespace(returncode=int(proof_phase == "red"))

    monkeypatch.setattr(replay.subprocess, "run", subprocess_result)
    expected_error = {
        "timeout": subprocess.TimeoutExpired,
        "malformed-xml": ElementTree.ParseError,
    }.get(failure, ValueError)
    with pytest.raises(expected_error):
        replay.main()

    assert calls[-1] == (copy, phase)
    reports = output / f"{copy}-pytest-nonzero"
    assert not (reports / f"{phase}.json").exists()
    assert not (output / "controls.json").exists()
    if phase == "green":
        # RED was accepted before the GREEN rejection; preserve its receipt.
        assert json.loads((reports / "red.json").read_text())["exit"] == 1
    for relative, original in caller_bytes.items():
        assert (tree / relative).read_bytes() == original
        assert (ROOT / relative).read_bytes() == original
