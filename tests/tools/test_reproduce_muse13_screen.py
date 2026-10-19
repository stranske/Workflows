"""Offline historical reproduction detects changed inputs, rows and aggregates."""

from __future__ import annotations

import json
import shutil

import pytest
from tools import reproduce_muse13_screen as proof


@pytest.fixture
def preserved(tmp_path):
    for relative in {*proof.INPUTS, proof.SOURCE, proof.ENSEMBLE, proof.POLICY}:
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
    receipt = json.loads((preserved / proof.ENSEMBLE).read_text())["evidence_reproduction"]
    assert receipt["policy"] == str(proof.POLICY)
    assert receipt["policy_sha256"] == proof.POLICY_SHA256
    assert receipt["input_sha256"] == {
        str(path): digest for path, digest in proof.INPUT_SHA256.items()
    }
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
    "location",
    [
        "prediction",
        "expected",
        "digest",
        "revision",
        "pair",
        "aggregate",
        "manifest",
        "peer_raw",
        "policy",
    ],
)
def test_changed_case_or_aggregate_is_rejected(preserved, location):
    if location == "policy":
        target = proof.POLICY
    elif location in {"prediction", "expected", "digest", "revision"}:
        target = proof.ARTIFACT
    elif location == "peer_raw":
        target = proof.DIRECTORY / "current-prompt-claude-cursor-muse12.json"
    else:
        target = proof.ENSEMBLE
    file = preserved / target
    data = json.loads(file.read_text())
    if location == "prediction":
        data["rows"][0]["prediction"] = (
            "FAIL" if data["rows"][0]["prediction"] != "FAIL" else "PASS"
        )
    elif location == "expected":
        data["rows"][0]["expected_verdict"] = "NON_PASS"
    elif location == "digest":
        data["rows"][0]["input_digest"] = "0" * 64
    elif location == "revision":
        data["rows"][0]["source_revision"] = "0" * 40
    elif location == "pair":
        data["pairs"][0]["agreement"] = 999
    elif location == "aggregate":
        data["judges"][0]["correct"] = 999
    elif location == "manifest":
        data["ordered_input_manifest"][2] = "/tmp/judge-screen/muse13-renamed.json"
    elif location == "peer_raw":
        # Same aggregate class (NON_PASS) but different preserved raw bytes must still fail.
        for row in data["rows"]:
            if row.get("raw_verdict") == "UNVERIFIABLE_INPUT":
                row["raw_verdict"] = "FAIL"
                break
        else:
            raise AssertionError("expected an UNVERIFIABLE_INPUT peer row to mutate")
    else:
        data["profiles"]["verifier-balanced"]["approval_stage"]["minimum_adjudicated_cases"] = 1
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        proof.verify(root=preserved)


def test_changed_versioned_source_is_rejected(preserved):
    source = preserved / proof.SOURCE
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source digest changed"):
        proof.verify(root=preserved)


def test_replay_passes_pinned_policy_into_analyze(preserved, monkeypatch):
    """Replay must supply the versioned policy so live config cannot change authority fields."""
    seen: dict = {}
    real_analyze = proof.analyze

    def capture(decisions, truth, **kwargs):
        seen["policy"] = kwargs.get("policy")
        return real_analyze(decisions, truth, **kwargs)

    monkeypatch.setattr(proof, "analyze", capture)
    assert proof.verify(root=preserved)["cases"] == 8
    assert seen["policy"] == proof.load_pinned_policy(preserved)
    assert (
        seen["policy"]["profiles"]["verifier-balanced"]["approval_stage"][
            "minimum_adjudicated_cases"
        ]
        == 75
    )


def test_write_recreates_artifact_and_receipt_then_cli_check_accepts(
    preserved, monkeypatch, capsys
):
    import sys

    artifact = preserved / proof.ARTIFACT
    artifact.unlink()
    ensemble = preserved / proof.ENSEMBLE
    stored = json.loads(ensemble.read_text())
    stored.pop("evidence_reproduction")
    stored.pop("ordered_input_manifest")
    ensemble.write_text(json.dumps(stored))

    expected = {"cases": 8, "judges": 9, "pairs": 36, "tie_breaks": 252}
    assert proof.verify(write=True, root=preserved) == expected
    assert json.loads(artifact.read_text()) == proof.standard_observations(preserved)
    rewritten = json.loads(ensemble.read_text())
    assert rewritten["ordered_input_manifest"] == [str(path) for path in proof.INPUTS]
    assert rewritten["evidence_reproduction"]["offline"] is True
    assert rewritten["evidence_reproduction"]["input_sha256"] == proof.verify_pinned_inputs(
        preserved
    )
    assert {k: v for k, v in rewritten.items() if k in stored} == stored

    # The CLI uses its real verifier, rooted only at the disposable evidence copy.
    real_verify = proof.verify
    monkeypatch.setattr(proof, "verify", lambda **kwargs: real_verify(root=preserved, **kwargs))
    monkeypatch.setattr(sys, "argv", ["reproduce_muse13_screen", "--check"])
    assert proof.main() == 0
    assert json.loads(capsys.readouterr().out) == expected
