"""Focused unit tests for scripts/validate_run_contract.py (issue #2630).

Covers opt-in skip, consumer ingest validation, producer/bridge required sections,
unsafe raw payload path reporting, and manifest artifact cross-checks. Uses temp
registries and inline envelopes only — no network or schema edits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import validate_run_contract as vrc

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "docs" / "contracts" / "schemas"
FIXTURES = ROOT / "tests" / "fixtures" / "backplane"


def _minimal_run_envelope(**overrides: object) -> dict:
    envelope = {
        "schema_version": "run-contract/v1",
        "repo": "stranske/Test-Producer",
        "tool": "test-tool",
        "run_id": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "status": "success",
        "github_issue": "stranske/Workflows#2630",
        "actor": {"kind": "ci", "id": "test", "intent": "unit test"},
        "inputs": {"validated": True},
        "outputs": {
            "manifest_ref": "artifact:manifest.json",
            "summary": {},
            "artifact_ids": [],
        },
        "provenance": {"tool_version": "0.1.0"},
        "cost": {"usd": 0.01, "input_tokens": 1, "output_tokens": 1},
        "latency": {"wall_ms": 10.0},
        "warnings": [],
        "data_quality": {"overall_status": "ok"},
        "evidence_refs": [],
        "identity_refs": ["manager:test"],
    }
    envelope.update(overrides)
    return envelope


def _participant(
    repo: str,
    *,
    role: str = "producer",
    status: str = "emitting",
    required_sections: list[str] | None = None,
    ingests: list[str] | None = None,
) -> dict:
    entry: dict = {
        "repo": repo,
        "role": role,
        "status": status,
        "contract_version": "run-contract/v1",
    }
    if required_sections is not None:
        entry["required_sections"] = required_sections
    if ingests is not None:
        entry["ingests"] = ingests
    return entry


def _registry(*participants: dict) -> dict:
    return {"participants": list(participants)}


def _validate(
    envelope: dict,
    *,
    repo: str,
    registry: dict,
    manifest: dict | None = None,
):
    return vrc.validate_envelope(
        envelope=envelope,
        schema_dir=SCHEMA_DIR,
        registry=registry,
        repo=repo,
        manifest=manifest,
    )


@pytest.mark.parametrize(
    "status",
    [None, "none", "candidate"],
)
def test_opt_in_skip_for_non_emitting_registry_status(status: str | None) -> None:
    repo = "stranske/Skip-Me"
    entry = _participant(repo, status=status or "none")
    if status is None:
        entry.pop("status")
    report = _validate(_minimal_run_envelope(), repo=repo, registry=_registry(entry))
    assert report.skipped
    assert report.conformant
    assert not report.violations


def test_opt_in_skip_for_absent_registry_entry() -> None:
    report = _validate(
        _minimal_run_envelope(),
        repo="stranske/not-in-registry",
        registry=_registry(),
    )
    assert report.skipped
    assert report.conformant


def test_cli_missing_envelope_skips_for_candidate_and_absent(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(_registry(_participant("stranske/Candidate", status="candidate"))),
        encoding="utf-8",
    )
    missing = tmp_path / "missing" / "run.json"
    for repo in ("stranske/Candidate", "stranske/absent"):
        rc = vrc.main(
            [
                str(missing),
                "--registry",
                str(registry_path),
                "--schema-dir",
                str(SCHEMA_DIR),
                "--repo",
                repo,
            ]
        )
        assert rc == 0, repo


def test_consumer_validates_ingested_schema_without_run_envelope() -> None:
    repo = "stranske/Evidence-Consumer"
    evidence = {
        "schema_version": "evidence-object/v1",
        "evidence_id": "ev-2630",
        "fact_ref": "metric.alpha",
        "source_id": "source-1",
        "method": "computed",
    }
    registry = _registry(
        _participant(
            repo,
            role="consumer",
            status="conformant",
            ingests=["evidence-object/v1"],
        )
    )

    report = _validate(evidence, repo=repo, registry=registry)

    assert report.conformant
    assert report.role == "consumer"
    assert not report.skipped
    assert "schema_version" not in {v.path for v in report.violations}


def test_consumer_without_declared_ingests_fails() -> None:
    repo = "stranske/Bare-Consumer"
    registry = _registry(_participant(repo, role="consumer", status="conformant"))

    report = _validate({"any": "payload"}, repo=repo, registry=registry)

    assert not report.conformant
    assert any(v.path == "ingests" for v in report.violations)


@pytest.mark.parametrize("role", ["producer", "bridge"])
def test_required_section_absent_fails_for_emitting_roles(role: str) -> None:
    repo = f"stranske/{role.title()}-Required"
    envelope = _minimal_run_envelope(repo=repo)
    envelope.pop("cost")
    registry = _registry(
        _participant(
            repo,
            role=role,
            status="emitting",
            required_sections=["cost", "latency"],
        )
    )

    report = _validate(envelope, repo=repo, registry=registry)

    assert not report.conformant
    assert report.role == role
    assert any(v.path == "cost" and "key absent" in v.message for v in report.violations)


def test_required_section_present_but_empty_fails_for_cost() -> None:
    repo = "stranske/Empty-Cost"
    envelope = _minimal_run_envelope(repo=repo, cost={})
    registry = _registry(
        _participant(
            repo,
            status="emitting",
            required_sections=["cost"],
        )
    )

    report = _validate(envelope, repo=repo, registry=registry)

    assert not report.conformant
    assert any(v.path == "cost" and "populated" in v.message for v in report.violations)


def test_required_empty_ok_sections_do_not_fail() -> None:
    repo = "stranske/Empty-Ok-Sections"
    envelope = _minimal_run_envelope(
        repo=repo,
        warnings=[],
        evidence_refs=[],
        identity_refs=[],
    )
    registry = _registry(
        _participant(
            repo,
            status="emitting",
            required_sections=["warnings", "evidence_refs", "identity_refs"],
        )
    )

    report = _validate(envelope, repo=repo, registry=registry)

    assert report.conformant


def test_unsafe_raw_payload_reports_nested_path() -> None:
    repo = "stranske/Unsafe-Nested"
    envelope = _minimal_run_envelope(
        repo=repo,
        outputs={
            "manifest_ref": "artifact:manifest.json",
            "summary": {"rows": [{"id": 1}]},
            "artifact_ids": [],
        },
    )
    registry = _registry(_participant(repo, status="emitting"))

    report = _validate(envelope, repo=repo, registry=registry)

    assert not report.conformant
    unsafe = [v for v in report.violations if "unsafe raw payload" in v.message]
    assert any(v.path == "outputs.summary.rows" for v in unsafe)
    assert all("id" not in v.message for v in unsafe)


def test_unsafe_raw_payload_reports_list_index_path() -> None:
    repo = "stranske/Unsafe-List"
    envelope = _minimal_run_envelope(
        repo=repo,
        inputs={"refs": [{"prompt": "secret"}]},
    )
    registry = _registry(_participant(repo, status="emitting"))

    report = _validate(envelope, repo=repo, registry=registry)

    assert not report.conformant
    unsafe = [v for v in report.violations if "unsafe raw payload" in v.message]
    assert any(
        v.path == "inputs.refs[0].prompt" and "unsafe raw payload field 'prompt'" in v.message
        for v in unsafe
    )
    assert all("secret" not in v.message for v in unsafe)


def test_unsafe_raw_payload_allows_empty_sentinel_values() -> None:
    repo = "stranske/Unsafe-Empty-Ok"
    envelope = _minimal_run_envelope(
        repo=repo,
        inputs={
            "prompt": "",
            "raw_output": None,
            "rows": [],
            "document_text": {},
        },
    )
    registry = _registry(_participant(repo, status="emitting"))

    report = _validate(envelope, repo=repo, registry=registry)

    unsafe = [v for v in report.violations if "unsafe raw payload" in v.message]
    assert unsafe == []


def test_manifest_cross_check_passes_when_artifact_refs_match() -> None:
    repo = "stranske/Manifest-Ok"
    artifact_id = "report-xlsx"
    envelope = _minimal_run_envelope(
        repo=repo,
        outputs={
            "manifest_ref": "artifact:manifest.json",
            "summary": {},
            "artifact_ids": [artifact_id],
        },
    )
    manifest = {
        "schema_version": "artifact-manifest/v1",
        "run_id": envelope["run_id"],
        "tool": envelope["tool"],
        "artifacts": [
            {
                "artifact_id": artifact_id,
                "name": "report.xlsx",
                "path": "report.xlsx",
                "sha256": "b" * 64,
            }
        ],
    }
    registry = _registry(_participant(repo, status="emitting"))

    report = _validate(envelope, repo=repo, registry=registry, manifest=manifest)

    assert report.conformant
    assert not any("manifest" in v.message.lower() for v in report.violations)


def test_manifest_cross_check_fails_when_artifact_id_missing() -> None:
    repo = "stranske/Manifest-Missing-Id"
    envelope = _minimal_run_envelope(
        repo=repo,
        outputs={
            "manifest_ref": "artifact:manifest.json",
            "summary": {},
            "artifact_ids": ["missing-artifact"],
        },
    )
    manifest = {
        "schema_version": "artifact-manifest/v1",
        "run_id": envelope["run_id"],
        "tool": envelope["tool"],
        "artifacts": [
            {
                "artifact_id": "other-artifact",
                "name": "other.bin",
                "path": "other.bin",
                "sha256": "c" * 64,
            }
        ],
    }
    registry = _registry(_participant(repo, status="emitting"))

    report = _validate(envelope, repo=repo, registry=registry, manifest=manifest)

    assert not report.conformant
    assert any(
        v.path == "outputs.artifact_ids"
        and "artifact_id 'missing-artifact' not in manifest" in v.message
        for v in report.violations
    )


def test_manifest_cross_check_fails_when_sha256_missing() -> None:
    repo = "stranske/Manifest-No-Hash"
    artifact_id = "report-xlsx"
    envelope = _minimal_run_envelope(
        repo=repo,
        outputs={
            "manifest_ref": "artifact:manifest.json",
            "summary": {},
            "artifact_ids": [artifact_id],
        },
    )
    manifest = {
        "schema_version": "artifact-manifest/v1",
        "run_id": envelope["run_id"],
        "tool": envelope["tool"],
        "artifacts": [
            {
                "artifact_id": artifact_id,
                "name": "report.xlsx",
                "path": "report.xlsx",
            }
        ],
    }
    registry = _registry(_participant(repo, status="emitting"))

    report = _validate(envelope, repo=repo, registry=registry, manifest=manifest)

    assert not report.conformant
    assert any(
        v.path == "manifest.artifacts"
        and f"manifest artifact '{artifact_id}' missing sha256" in v.message
        for v in report.violations
    )


def test_fixture_valid_run_passes_with_matching_manifest() -> None:
    envelope = json.loads((FIXTURES / "valid_run.json").read_text())
    manifest = json.loads((FIXTURES / "valid_manifest.json").read_text())
    registry = json.loads((ROOT / "config" / "backplane_participants.json").read_text())

    report = _validate(
        envelope,
        repo="stranske/Pension-Data",
        registry=registry,
        manifest=manifest,
    )

    assert report.conformant
    assert not report.skipped
