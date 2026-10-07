"""Failed replay proofs must restore private sources without claiming acceptance."""

import importlib.util
import subprocess
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "docs/evidence/issue-3743/uv-resolution/replay_uv_resolution.py"


@pytest.mark.parametrize("copy", ["root", "template"])
@pytest.mark.parametrize("phase", ["red", "green"])
@pytest.mark.parametrize("failure", ["timeout", "invalid-proof"])
def test_failed_replay_restores_both_private_helpers(tmp_path, monkeypatch, copy, phase, failure):
    # These controls exercise restoration only; run_case is replaced and no XML
    # is parsed. Keep them independent of the real replay's site dependencies.
    monkeypatch.setitem(sys.modules, "defusedxml", types.SimpleNamespace(ElementTree=None))
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
