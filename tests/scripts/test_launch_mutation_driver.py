"""The retained proof driver must restore source even when validation fails."""

import gzip
import hashlib
import json
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


def test_driver_success_writes_complete_receipts_for_both_copies(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    driver = runpy.run_path(
        str(root / "docs/evidence/issue-3743/launch-boundaries/wf-mutation-driver.py")
    )
    originals = {}
    for prefix in ["", "templates/consumer-repo/"]:
        source = tmp_path / prefix / "scripts/check_deliberate_break.py"
        source.parent.mkdir(parents=True)
        originals[source] = (root / prefix / "scripts/check_deliberate_break.py").read_bytes()
        source.write_bytes(originals[source])
    test = tmp_path / driver["test"]
    test.parent.mkdir(parents=True)
    test.write_bytes((root / driver["test"]).read_bytes())
    calls = []

    def run(argv, **kwargs):
        red = len(calls) % 2 == 0
        source = (
            tmp_path
            / ("templates/consumer-repo/" if "[template]" in argv[3] else "")
            / "scripts/check_deliberate_break.py"
        )
        assert (source.read_bytes() != originals[source]) == red
        assert kwargs["timeout"] == 300
        calls.append((argv, source.read_bytes()))
        return subprocess.CompletedProcess(
            argv, 1 if red else 0, "synthetic stdout", "synthetic stderr"
        )

    monkeypatch.setattr(subprocess, "run", run)
    output = tmp_path / "output"
    driver["main"](repo=tmp_path, out=output)
    receipts = json.loads((output / "wf-mutations.json").read_text())
    assert len(calls) == 20
    assert len(receipts) == 10
    assert {r["side"] for r in receipts} == {"root", "template"}
    assert len({(r["side"], r["case"]) for r in receipts}) == 10
    for index, receipt in enumerate(receipts):
        argv, mutant = calls[2 * index]
        assert receipt["argv"] == argv
        assert receipt["red_exit"] == 1
        assert receipt["green_exit"] == 0
        assert receipt["restored_byte_identical"] is True
        assert receipt["mutant_sha256"] == hashlib.sha256(mutant).hexdigest()
        prefix = "templates/consumer-repo/" if receipt["side"] == "template" else ""
        source = tmp_path / prefix / "scripts/check_deliberate_break.py"
        assert source.read_bytes() == originals[source]
        assert receipt["source_sha256"] == hashlib.sha256(originals[source]).hexdigest()
        assert receipt["test_sha256"] == hashlib.sha256(test.read_bytes()).hexdigest()
    logs = list(output.glob("*.log.gz"))
    assert len(logs) == 20
    assert all(
        gzip.decompress(path.read_bytes()) == b"synthetic stdoutsynthetic stderr" for path in logs
    )
