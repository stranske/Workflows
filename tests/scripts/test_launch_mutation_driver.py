"""The retained proof driver must restore source even when validation fails."""

import runpy
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("failure", ["oserror", "timeout", "zero", "collection", "green-timeout"])
def test_driver_restores_source_on_validation_failure(tmp_path, monkeypatch, failure):
    root = Path(__file__).resolve().parents[2]
    driver = runpy.run_path(
        str(root / "docs/evidence/issue-3743/launch-boundaries/wf-mutation-driver.py")
    )
    source = tmp_path / "scripts/check_deliberate_break.py"
    source.parent.mkdir()
    original = (root / "scripts/check_deliberate_break.py").read_bytes()
    source.write_bytes(original)
    calls = []

    def run(argv, **kwargs):
        calls.append(kwargs)
        assert kwargs["timeout"] == 300
        if len(calls) == 1:
            assert source.read_bytes() != original
            if failure == "oserror":
                raise OSError("validation launch failed")
            if failure == "timeout":
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return subprocess.CompletedProcess(
                argv, 1 if failure == "green-timeout" else (0 if failure == "zero" else 2), "", ""
            )
        assert source.read_bytes() == original
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", run)
    error = (
        OSError
        if failure == "oserror"
        else (subprocess.TimeoutExpired if "timeout" in failure else AssertionError)
    )
    with pytest.raises(error):
        driver["main"](repo=tmp_path, out=tmp_path)
    assert source.read_bytes() == original
    assert len(calls) == (2 if failure == "green-timeout" else 1)
