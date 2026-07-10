from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts import validate_backplane_registry as vbr

ROOT = Path(__file__).resolve().parents[1]


def _registry() -> dict:
    return json.loads((ROOT / "config" / "backplane_participants.json").read_text())


def _pension_conformant_entry(registry: dict) -> dict:
    for entry in registry["participants"]:
        if entry["repo"] == "stranske/Pension-Data":
            return entry
    raise AssertionError("missing Pension-Data participant")


def test_registry_has_no_tbd_placeholders_and_validates() -> None:
    registry = _registry()
    findings = vbr.validate_registry(registry)

    assert findings == []
    assert "TBD" not in json.dumps(registry)


def test_parent_issue_and_inactive_participants_are_explicit() -> None:
    registry = _registry()

    assert registry["parent_issue"] == "stranske/Workflows#2743"
    for entry in registry["participants"]:
        assert entry["parent_issue"] == registry["parent_issue"]
        if entry["repo"] != "stranske/Pension-Data":
            assert entry["issue"] is None
            assert entry["issue_deferred"]["reason"]
            assert entry["reference_state"] in {"missing", "not-applicable"}


def test_pension_conformant_entry_has_live_reference_evidence() -> None:
    entry = _pension_conformant_entry(_registry())

    assert entry["issue"] == "stranske/Pension-Data#703"
    assert entry["status"] == "conformant"
    assert entry["reference_state"] == "valid"
    evidence = entry["reference_run_evidence"]
    assert evidence["producer_pr"] == "stranske/Pension-Data#704"
    assert evidence["verifier_followup_pr"] == "stranske/Pension-Data#708"
    assert evidence["run_id"] == "pension-data-one-pdf-reference"
    assert evidence["reference_run_sha256"] == (
        "e124f4cf2f8c0d6854d1bb66f1b159e0e87e7df495d54e2132381a7a36cc1c2f"
    )
    assert evidence["conformance_run_url"].endswith("/86320867619")


def test_conformant_requires_reference_evidence() -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    del entry["reference_run_evidence"]["reference_run_sha256"]

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path.endswith("reference_run_evidence.reference_run_sha256")
        and finding.message == "must be sha256"
        for finding in findings
    )
