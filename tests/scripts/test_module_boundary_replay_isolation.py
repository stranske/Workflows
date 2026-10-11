"""A failed evidence replay must preserve concurrent caller edits."""

import runpy
import shlex
import shutil
from pathlib import Path

import pytest


@pytest.mark.parametrize("relative_output", [False, True], ids=["absolute", "relative"])
def test_failed_replay_preserves_concurrent_caller_edit(tmp_path, monkeypatch, relative_output):
    root = Path(__file__).resolve().parents[2]
    relative = Path("docs/evidence/issue-3743/module-boundaries/replay.py")
    replay = runpy.run_path(str(root / relative))
    caller = tmp_path / "caller"
    for name in (
        "scripts/check_deliberate_break.py",
        "templates/consumer-repo/scripts/check_deliberate_break.py",
        replay["TEST"],
    ):
        target = caller / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    source = caller / "scripts/check_deliberate_break.py"
    template = caller / "templates/consumer-repo/scripts/check_deliberate_break.py"
    original = source.read_bytes()
    template_original = template.read_bytes()
    concurrent = original + b"\n# concurrent caller edit\n"
    private_roots = []

    def interrupted_run(argv, *, cwd, env, capture_output, timeout):
        assert all("proof with spaces" not in arg for arg in argv)
        options = shlex.split(env["PYTEST_ADDOPTS"])
        assert len(options) == 1 and options[0].startswith(f"--junitxml={output}/")
        private_roots.append(cwd)
        assert cwd != caller
        assert (cwd / "scripts/check_deliberate_break.py").read_bytes() != original
        assert source.read_bytes() == original
        source.write_bytes(concurrent)
        raise RuntimeError("simulated failed replay")

    monkeypatch.setitem(replay["main"].__globals__, "__file__", str(caller / relative))
    monkeypatch.setattr(replay["subprocess"], "run", interrupted_run)
    output = tmp_path / "proof with spaces"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        replay["sys"],
        "argv",
        [str(relative), "--output", output.name if relative_output else str(output)],
    )
    with pytest.raises(RuntimeError, match="simulated failed replay"):
        replay["main"]()
    assert source.read_bytes() == concurrent
    assert template.read_bytes() == template_original
    assert len(private_roots) == 1
    assert not private_roots[0].exists()
    assert (output / "results.json").is_file()
