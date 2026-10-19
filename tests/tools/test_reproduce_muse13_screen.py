"""Offline historical reproduction detects changed inputs, rows and aggregates."""

from __future__ import annotations

import json
import shutil

import pytest
from tools import reproduce_muse13_screen as proof


@pytest.fixture
def preserved(tmp_path):
    for relative in {*proof.INPUTS, proof.SOURCE, proof.ENSEMBLE}:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(proof.ROOT / relative, destination)
    return tmp_path


def test_complete_historical_reproduction_uses_no_model_requests(preserved, monkeypatch):
    # Any subprocess/model invocation would be a new observation, not replay.
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline reproduction cannot launch a provider")

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert proof.verify(root=preserved) == {
        "cases": 8,
        "judges": 9,
        "pairs": 36,
        "tie_breaks": 252,
    }
    artifact = json.loads((preserved / proof.ARTIFACT).read_text())
    assert {r["source_revision"] for r in artifact["rows"]} == {proof.SOURCE_REVISION}
    assert all(len(r["input_digest"]) == 64 for r in artifact["rows"])
    assert all(r["prediction"] == r["raw_verdict"] for r in artifact["rows"])
    assert not any("prompt" in key for row in artifact["rows"] for key in row)
    standard = next(
        r
        for r in json.loads((preserved / proof.ENSEMBLE).read_text())["judges"]
        if r["judge"] == "muse-api:muse-spark-1.3"
    )
    assert (
        standard["correct"],
        standard["cases"],
        standard["false_pass"],
        standard["false_fail"],
    ) == (4, 8, 2, 2)
    assert standard["may_hold_pass_authority"] is False


@pytest.mark.parametrize(
    "location", ["prediction", "expected", "digest", "revision", "pair", "aggregate", "manifest"]
)
def test_changed_case_or_aggregate_is_rejected(preserved, location):
    target = (
        proof.ARTIFACT
        if location in {"prediction", "expected", "digest", "revision"}
        else proof.ENSEMBLE
    )
    file = preserved / target
    data = json.loads(file.read_text())
    if location == "prediction":
        data["rows"][0]["raw_verdict"] = "FAIL"
    elif location == "expected":
        data["rows"][0]["expected_verdict"] = "NON_PASS"
    elif location == "digest":
        data["rows"][0]["input_digest"] = "0" * 64
    elif location == "revision":
        data["rows"][0]["source_revision"] = "0" * 40
    elif location == "pair":
        data["pairs"][0]["agreements"] = 999
    elif location == "aggregate":
        data["judges"][0]["correct"] = 999
    else:
        data["ordered_input_manifest"][2] = "/tmp/judge-screen/muse13-renamed.json"
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        proof.verify(root=preserved)


def test_changed_versioned_source_is_rejected(preserved):
    source = preserved / proof.SOURCE
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source digest changed"):
        proof.verify(root=preserved)
