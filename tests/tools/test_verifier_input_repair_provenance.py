"""Producer side of #4239: retained provider outcomes carry artifact-bound repair provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tools.verifier_event_recovery import incomplete_cause

ASSESSMENT = {"assessment_identity": {"mode": "evaluate", "provider": "", "model": ""}}


def _write(tmp_path: Path, row: dict, *, receipt_over: dict | None = None) -> None:
    raw = json.dumps(row).encode()
    (tmp_path / "evaluation.json").write_bytes(raw)
    receipt = {
        "mode": "evaluate",
        "status": "completed",
        "exit_code": 0,
        "outputs": {
            "evaluation.json": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        },
        **(receipt_over or {}),
    }
    (tmp_path / "evaluation-execution.json").write_text(json.dumps(receipt))


def _classify(tmp_path: Path, step: str = "success") -> dict:
    return incomplete_cause(ASSESSMENT, directory=tmp_path, step_outcome=step)


def _row(verdict: str, **over) -> dict:
    return {
        "verdict": verdict,
        "used_llm": True,
        "provider_used": "openai/gpt",
        "model": "gpt",
        **over,
    }


def test_unverifiable_provider_result_is_bound_to_retained_bytes_and_stays_nonretryable(tmp_path):
    _write(tmp_path, _row("UNVERIFIABLE_INPUT"))
    cause = _classify(tmp_path)
    assert cause["retry_kind"] == "recover_existing_evaluation"
    assert cause["retryable"] is False
    repair = cause["input_repair"]
    raw = (tmp_path / "evaluation.json").read_bytes()
    assert repair["result"] == {
        "path": "evaluation.json",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    assert (
        repair["receipt"]["raw_sha256"]
        == hashlib.sha256((tmp_path / "evaluation-execution.json").read_bytes()).hexdigest()
    )
    assert repair["provider_verdicts"] == [
        {"provider": "openai/gpt", "model": "gpt", "verdict": "UNVERIFIABLE_INPUT"}
    ]


@pytest.mark.parametrize(
    "row,receipt_over,step",
    [
        (_row("PASS"), None, "success"),  # no input-unverifiable slot
        (_row("UNVERIFIABLE_INPUT", error="boom"), None, "success"),  # errored attempt
        (_row("UNVERIFIABLE_INPUT"), {"exit_code": 1}, "success"),
        (_row("UNVERIFIABLE_INPUT"), {"status": "output_truncated"}, "success"),
        (
            _row("UNVERIFIABLE_INPUT"),
            {"outputs": {"evaluation.json": {"sha256": "0" * 64}}},
            "success",
        ),
        (_row("UNVERIFIABLE_INPUT"), None, "skipped"),
    ],
)
def test_no_provenance_without_complete_joined_provider_evidence(tmp_path, row, receipt_over, step):
    _write(tmp_path, row, receipt_over=receipt_over)
    assert "input_repair" not in _classify(tmp_path, step)


def test_missing_receipt_gives_no_provenance(tmp_path):
    _write(tmp_path, _row("UNVERIFIABLE_INPUT"))
    (tmp_path / "evaluation-execution.json").unlink()
    cause = _classify(tmp_path)
    assert cause["retry_kind"] == "recover_existing_evaluation"
    assert "input_repair" not in cause


COMPARE = {"assessment_identity": {"mode": "compare", "provider": "", "model": ""}}


def _write_compare(tmp_path: Path, rows: list[dict], *, outputs: object = None) -> bytes:
    raw = json.dumps({"results": rows}).encode()
    (tmp_path / "comparison.json").write_bytes(raw)
    receipt = {
        "mode": "compare",
        "status": "completed",
        "exit_code": 0,
        "outputs": (
            {"comparison.json": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
            if outputs is None
            else outputs
        ),
    }
    (tmp_path / "comparison-execution.json").write_text(json.dumps(receipt))
    return raw


def test_compare_mode_two_slots_bind_sorted_verdicts_to_comparison_receipt(tmp_path):
    # Slots are deliberately written out of provider order; one passes, one is input-unverifiable.
    raw = _write_compare(
        tmp_path,
        [
            _row("UNVERIFIABLE_INPUT", provider_used="openai/gpt", model="gpt"),
            _row("PASS", provider_used="anthropic/claude", model="claude"),
        ],
    )
    cause = incomplete_cause(COMPARE, directory=tmp_path, step_outcome="success")
    assert cause["retry_kind"] == "recover_existing_evaluation"
    assert cause["retryable"] is False
    repair = cause["input_repair"]
    assert repair["result"] == {
        "path": "comparison.json",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    assert repair["receipt"] == {
        "path": "comparison-execution.json",
        "raw_sha256": hashlib.sha256(
            (tmp_path / "comparison-execution.json").read_bytes()
        ).hexdigest(),
    }
    assert repair["provider_verdicts"] == [
        {"provider": "anthropic/claude", "model": "claude", "verdict": "PASS"},
        {"provider": "openai/gpt", "model": "gpt", "verdict": "UNVERIFIABLE_INPUT"},
    ]


@pytest.mark.parametrize("output", [None, [], ["sha256"], "sha256", 7, True])
@pytest.mark.parametrize("mode", ["evaluate", "compare"])
def test_malformed_receipt_output_fails_closed_without_losing_recovery_cause(
    tmp_path, mode, output
):
    # The receipt's per-file entry is not an object: provenance is withheld, never raised.
    if mode == "evaluate":
        _write(tmp_path, _row("UNVERIFIABLE_INPUT"))
        receipt_path = tmp_path / "evaluation-execution.json"
        name, manifest = "evaluation.json", ASSESSMENT
    else:
        _write_compare(
            tmp_path,
            [
                _row("PASS", provider_used="anthropic/claude", model="claude"),
                _row("UNVERIFIABLE_INPUT", provider_used="openai/gpt", model="gpt"),
            ],
        )
        receipt_path = tmp_path / "comparison-execution.json"
        name, manifest = "comparison.json", COMPARE
    receipt = json.loads(receipt_path.read_text())
    receipt["outputs"][name] = output
    receipt_path.write_text(json.dumps(receipt))
    cause = incomplete_cause(manifest, directory=tmp_path, step_outcome="success")
    assert cause["retry_kind"] == "recover_existing_evaluation"
    assert cause["retryable"] is False
    assert "input_repair" not in cause


@pytest.mark.parametrize("outputs", [None, [], "outputs", 7])
def test_malformed_receipt_outputs_container_fails_closed(tmp_path, outputs):
    _write(tmp_path, _row("UNVERIFIABLE_INPUT"))
    receipt_path = tmp_path / "evaluation-execution.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["outputs"] = outputs
    receipt_path.write_text(json.dumps(receipt))
    cause = _classify(tmp_path)
    assert cause["retry_kind"] == "recover_existing_evaluation"
    assert "input_repair" not in cause
