from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
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

    # The live registry must be STRUCTURALLY valid. Operational freshness (a
    # reference run aging past the 7-day window) is a non-blocking "stale" finding:
    # it is surfaced by the dedicated backplane lane (health-78) but must not fail
    # this structural check, which runs in the required suite for every unrelated PR.
    assert vbr.blocking_findings(findings) == []
    assert "TBD" not in json.dumps(registry)


def test_stale_reference_run_is_non_blocking_severity() -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    entry["reference_run_evidence"]["generated_at"] = "2026-01-01T00:00:00Z"

    findings = vbr.validate_registry(registry)

    stale = [f for f in findings if f.message == "reference run is stale"]
    assert stale
    assert all(f.severity == vbr.STALE_SEVERITY for f in stale)
    # Staleness alone must not block: no structural (error-severity) findings remain.
    assert vbr.blocking_findings(findings) == []


def test_structural_defects_remain_blocking_despite_staleness_carveout() -> None:
    # Deliberate-break guard: the freshness carve-out must not weaken structural
    # validation. A malformed reference run (missing sha256) still blocks.
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    del entry["reference_run_evidence"]["reference_run_sha256"]

    findings = vbr.validate_registry(registry)

    assert vbr.blocking_findings(findings)


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
    assert evidence["source_issue"] == "stranske/Pension-Data#703"
    assert evidence["producer_pr"] == "stranske/Pension-Data#704"
    assert evidence["verifier_followup_issue"] == "stranske/Pension-Data#707"
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


@pytest.mark.parametrize("bad_run_id", [123, ["pension-run"], ""])
def test_reference_run_id_must_be_non_empty_string(bad_run_id: object) -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    entry["reference_run_evidence"]["run_id"] = bad_run_id

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path.endswith("reference_run_evidence.run_id")
        and finding.message == "must be populated"
        for finding in findings
    )


def test_strict_cli_flag_matches_documented_invocation(tmp_path: Path) -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    entry["reference_run_evidence"]["generated_at"] = datetime.now(UTC).isoformat()
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    assert vbr.main(["--strict", str(registry_path)]) == 0


def test_deferred_issue_reason_must_be_non_empty_string() -> None:
    registry = copy.deepcopy(_registry())
    entry = registry["participants"][1]
    entry["issue_deferred"]["reason"] = {"text": "not a string"}

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path.endswith("issue_deferred.reason")
        and finding.message == "deferred issue needs a reason"
        for finding in findings
    )


def test_expired_deferred_issue_is_rejected() -> None:
    registry = copy.deepcopy(_registry())
    entry = registry["participants"][1]
    entry["issue_deferred"]["expires_at"] = "2026-01-01T00:00:00Z"

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path.endswith("issue_deferred.expires_at")
        and finding.message == "deferred issue expired"
        for finding in findings
    )


def test_stale_reference_run_is_rejected() -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    entry["reference_run_evidence"]["generated_at"] = "2026-01-01T00:00:00Z"

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path.endswith("reference_run_evidence.generated_at")
        and finding.message == "reference run is stale"
        for finding in findings
    )


def test_future_reference_run_is_rejected() -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    entry["reference_run_evidence"]["generated_at"] = "2999-01-01T00:00:00Z"

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path.endswith("reference_run_evidence.generated_at")
        and finding.message == "must not be in the future"
        for finding in findings
    )


def test_stale_after_hours_is_bounded() -> None:
    registry = copy.deepcopy(_registry())
    registry["stale_after_hours"] = 10**20

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path == "stale_after_hours"
        and finding.message == f"stale_after_hours must be <= {vbr.MAX_STALE_AFTER_HOURS}"
        for finding in findings
    )


def test_reference_urls_are_field_specific_and_complete() -> None:
    registry = copy.deepcopy(_registry())
    evidence = _pension_conformant_entry(registry)["reference_run_evidence"]
    evidence["emit_reference_run_url"] = "https://github.com/stranske/Pension-Data/issues/703"
    evidence["conformance_run_url"] = (
        "https://github.com/stranske/Pension-Data/actions/runs/29080121547/job/86320867619 extra"
    )
    evidence["disposition_comment"] = (
        "https://github.com/stranske/Pension-Data/actions/runs/29080121547/job/86320867619"
    )

    findings = vbr.validate_registry(registry)

    messages = {finding.path: finding.message for finding in findings}
    assert (
        messages["participants[0].reference_run_evidence.emit_reference_run_url"]
        == "must be GitHub run job URL"
    )
    assert (
        messages["participants[0].reference_run_evidence.conformance_run_url"]
        == "must be GitHub run job URL"
    )
    assert (
        messages["participants[0].reference_run_evidence.disposition_comment"]
        == "must be GitHub issue comment URL"
    )


def test_conformant_source_issue_must_match_participant_issue() -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    entry["reference_run_evidence"]["source_issue"] = "stranske/Pension-Data#707"

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path.endswith("reference_run_evidence.source_issue")
        and finding.message == "must match participant issue"
        for finding in findings
    )


def test_conformant_entry_requires_real_issue() -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    entry["issue"] = None
    entry["issue_deferred"] = {
        "expires_at": "2026-08-15T00:00:00Z",
        "reason": "invalid for conformant entries",
    }

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path == "participants[0].issue"
        and finding.message == "conformant entry needs a real issue ref"
        for finding in findings
    )


def test_malformed_participant_returns_finding_instead_of_crashing() -> None:
    registry = copy.deepcopy(_registry())
    registry["participants"].append(None)

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path == f"participants[{len(registry['participants']) - 1}]"
        and finding.message == "participant entry must be an object"
        for finding in findings
    )


def test_malformed_participant_json_report_returns_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = copy.deepcopy(_registry())
    registry["participants"].append(None)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    assert vbr.main(["--json", str(registry_path)]) == 1
    report = json.loads(capsys.readouterr().out)

    assert any(
        finding["path"] == f"participants[{len(registry['participants']) - 1}]"
        and finding["message"] == "participant entry must be an object"
        for finding in report["findings"]
    )


def test_conformant_requires_ordered_lifecycle_history() -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    entry["lifecycle_history"] = [
        {
            "status": "planned",
            "at": "2026-07-10T02:32:58Z",
            "evidence": "stranske/Workflows#2743",
        },
        {
            "status": "conformant",
            "at": "2026-07-10T08:33:31Z",
            "evidence": "https://github.com/stranske/Pension-Data/actions/runs/29080121547/job/86320867619",
        },
    ]

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path == "participants[0].lifecycle_history"
        and finding.message == "must progress planned -> emitting -> conformant"
        for finding in findings
    )


def test_conformant_rejects_missing_lifecycle_history() -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    del entry["lifecycle_history"]

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path == "participants[0].lifecycle_history"
        and finding.message == "conformant entry needs lifecycle history"
        for finding in findings
    )


def test_conformant_rejects_decreasing_lifecycle_timestamps() -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    entry["lifecycle_history"][2]["at"] = "2026-07-10T01:00:00Z"

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path == "participants[0].lifecycle_history[2].at"
        and finding.message == "lifecycle timestamps must be monotonic"
        for finding in findings
    )


def test_conformant_rejects_invalid_lifecycle_evidence() -> None:
    registry = copy.deepcopy(_registry())
    entry = _pension_conformant_entry(registry)
    entry["lifecycle_history"][1][
        "evidence"
    ] = "https://github.com/stranske/Pension-Data/issues/703"

    findings = vbr.validate_registry(registry)

    assert any(
        finding.path == "participants[0].lifecycle_history[1].evidence"
        and finding.message == "must be issue ref or GitHub run job URL"
        for finding in findings
    )
