"""Focused unit tests for scripts/validate_run_contract.py (issue #2630).

Covers opt-in skip, consumer ingest validation, producer/bridge required sections,
unsafe raw payload path reporting, and manifest artifact cross-checks. Uses temp
registries and inline envelopes only — no network or schema edits.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
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


def test_document_page_checks_reject_conflicts_and_noncanonical_dates() -> None:
    report = vrc.Report(repo="owner/repo")
    vrc._check_document_page(
        {
            "document_ref": {
                "sha256": "abc",
                "supersedes": "abc",
                "page": 1,
                "doc_key": "document/2026-2-03",
            },
            "locator": {"page": 2},
        },
        report,
    )

    assert not report.conformant
    assert [violation.path for violation in report.violations] == [
        "document_ref/supersedes",
        "document_ref/page",
        "document_ref/doc_key",
    ]


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
    run_json: Path | None = None,
):
    return vrc.validate_envelope(
        envelope=envelope,
        schema_dir=SCHEMA_DIR,
        registry=registry,
        repo=repo,
        manifest=manifest,
        run_json=run_json,
    )


@pytest.mark.parametrize(
    "context,expected_path,expected_message",
    [
        ("no-manifest", "manifest", "emitted_evidence_policy requires an artifact manifest object"),
        ("no-run", "run_json", "emitted_evidence_policy requires run_json artifact context"),
        ("missing-parent", "run_json", "run_json parent is not an existing artifact directory"),
        (
            "bad-artifacts",
            "manifest.artifacts",
            "manifest artifacts must be a list for evidence closure",
        ),
    ],
)
def test_evidence_closure_requires_complete_artifact_context(
    tmp_path: Path, context: str, expected_path: str, expected_message: str
) -> None:
    manifest = (
        None
        if context == "no-manifest"
        else {"artifacts": {"bad": True} if context == "bad-artifacts" else []}
    )
    run_json = None if context == "no-run" else tmp_path / "run.json"
    if context == "missing-parent":
        run_json = tmp_path / "absent" / "run.json"
    report = vrc.Report(repo="closure")

    vrc._validate_manifest_evidence_closure(
        envelope={}, manifest=manifest, run_json=run_json, schema_dir=SCHEMA_DIR, report=report
    )

    assert not report.conformant
    assert [(v.path, v.message) for v in report.violations] == [(expected_path, expected_message)]


@pytest.mark.parametrize("kind", ["file-link", "directory-link", "directory"])
def test_evidence_paths_reject_symlink_components_and_directories(
    tmp_path: Path, kind: str
) -> None:
    folder = tmp_path / "artifacts"
    folder.mkdir()
    (folder / "evidence.json").write_text("{}", encoding="utf-8")
    if kind == "file-link":
        (tmp_path / "link.json").symlink_to(folder / "evidence.json")
        path = "link.json"
    elif kind == "directory-link":
        (tmp_path / "link").symlink_to(folder, target_is_directory=True)
        path = "link/evidence.json"
    else:
        path = "artifacts"
    report = vrc.Report(repo="closure")

    assert vrc._safe_evidence_path(tmp_path, {"path": path}, report, 3) is None
    assert not report.conformant
    assert report.violations == [
        vrc.Violation(
            path="manifest.artifacts[3].path",
            message=(
                "evidence artifact must be an existing regular file"
                if kind == "directory"
                else "evidence artifact path must not traverse a symlink"
            ),
        )
    ]


@pytest.mark.parametrize("failure", ["hash", "json", "utf8"])
def test_evidence_closure_reports_unreadable_artifact_bytes(
    tmp_path: Path, monkeypatch, failure: str
) -> None:
    path = tmp_path / "evidence-test.json"
    path.write_bytes(b"\xff" if failure == "utf8" else b"{")
    manifest = {
        "artifacts": [
            {
                "name": path.name,
                "path": path.name,
                "kind": "evidence",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ]
    }
    if failure == "hash":

        def cannot_hash(_path):
            raise OSError("artifact removed during hashing")

        monkeypatch.setattr(vrc, "_sha256_file", cannot_hash)
    report = vrc.Report(repo="closure")

    vrc._validate_manifest_evidence_closure(
        envelope={"evidence_refs": []},
        manifest=manifest,
        run_json=tmp_path / "run.json",
        schema_dir=SCHEMA_DIR,
        report=report,
    )

    assert not report.conformant
    assert len(report.violations) == 1
    assert report.violations[0].path == str(path)
    assert report.violations[0].message.startswith(
        "cannot hash evidence artifact:" if failure == "hash" else "cannot load evidence artifact:"
    )


@pytest.mark.parametrize("refs", [None, "evidence:a", [7]])
def test_evidence_closure_rejects_malformed_reference_lists(tmp_path: Path, refs) -> None:
    report = vrc.Report(repo="closure")

    vrc._validate_manifest_evidence_closure(
        envelope={"evidence_refs": refs},
        manifest={"artifacts": []},
        run_json=tmp_path / "run.json",
        schema_dir=SCHEMA_DIR,
        report=report,
    )

    assert not report.conformant
    assert report.violations == [
        vrc.Violation(
            path="evidence_refs",
            message="evidence_refs must be a list of strings for evidence closure",
        )
    ]


@pytest.mark.parametrize("valid", [True, False])
def test_evidence_cli_writes_report_and_appends_actual_conformance_in_warn_only_mode(
    tmp_path: Path, capsys, valid: bool
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_bytes(
        (FIXTURES / "valid_native_document_evidence.json").read_bytes() if valid else b"{"
    )
    report_path = tmp_path / "report.json"
    output = tmp_path / "github-output"
    output.write_text("existing=value\n", encoding="utf-8")

    assert (
        vrc.main(
            [
                "--evidence-objects",
                str(evidence),
                "--schema-dir",
                str(SCHEMA_DIR),
                "--report-json",
                str(report_path),
                "--github-output",
                str(output),
                "--warn-only",
            ]
        )
        == 0
    )

    report = json.loads(report_path.read_text())
    assert report["repo"] == "evidence-object/v1"
    assert report["conformant"] is valid
    assert report["skipped"] is False
    assert bool(report["violations"]) is not valid
    assert output.read_text() == f"existing=value\nconformant={str(valid).lower()}\n"
    captured = capsys.readouterr()
    if valid:
        assert captured.out == "evidence-object/v1: 1 file(s) conform to schema\n"
        assert captured.err == ""
    else:
        assert captured.out == ""
        assert "cannot load evidence object" in captured.err


@pytest.mark.parametrize("invalid_evidence", [False, True])
def test_consumer_tracked_variable_resolves_embedded_evidence_offline(
    invalid_evidence: bool, monkeypatch
) -> None:
    def reject_remote_schema(*args, **kwargs):
        raise AssertionError("Schema validation must use bundled evidence schema")

    monkeypatch.setattr("urllib.request.urlopen", reject_remote_schema)
    envelope = json.loads((FIXTURES / "valid_tracked_variable.json").read_text())
    if invalid_evidence:
        envelope["evidence"].pop("method")
    repo = "stranske/Tracked-Consumer"
    report = _validate(
        envelope,
        repo=repo,
        registry=_registry(_participant(repo, role="consumer", ingests=["tracked-variable/v1"])),
    )
    assert report.conformant is not invalid_evidence
    assert not report.skipped
    if invalid_evidence:
        assert any("method" in v.message for v in report.violations)


@pytest.mark.parametrize("path", ["", "..", "/absolute.json", "folder\\evidence.json"])
def test_manifest_evidence_paths_reject_nonportable_or_escaping_locations(
    tmp_path: Path, path: str
) -> None:
    report = vrc.Report(repo="test")

    resolved = vrc._safe_evidence_path(tmp_path, {"path": path}, report, 2)

    assert resolved is None
    assert report.violations[0].path == "manifest.artifacts[2].path"
    expected = (
        "evidence artifact path must be a non-empty relative POSIX path"
        if path in {"", "folder\\evidence.json"}
        else "evidence artifact path must not be absolute or traverse parents"
    )
    assert report.violations[0].message == expected


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
        "excerpt": "Computed from source-1.",
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


def _write_evidence_closure_run(
    tmp_path: Path,
    *,
    evidence: list[tuple[str, dict]],
    refs: list[str] | None = None,
    mutate_manifest: Callable[[dict], None] | None = None,
) -> tuple[dict, dict, Path]:
    """Create an on-disk producer run whose evidence paths are manifest-relative."""
    repo = "stranske/Evidence-Closure"
    envelope = _minimal_run_envelope(
        repo=repo,
        evidence_refs=refs if refs is not None else [item[1]["evidence_id"] for item in evidence],
    )
    artifacts = []
    for artifact_id, document in evidence:
        filename = f"{artifact_id}.json"
        path = tmp_path / filename
        path.write_text(json.dumps(document), encoding="utf-8")
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "name": filename,
                "kind": "evidence",
                "path": filename,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "schema_version": "artifact-manifest/v1",
        "run_id": envelope["run_id"],
        "tool": envelope["tool"],
        "artifacts": artifacts,
    }
    if mutate_manifest:
        mutate_manifest(manifest)
    run_json = tmp_path / "run.json"
    run_json.write_text(json.dumps(envelope), encoding="utf-8")
    return envelope, manifest, run_json


def _evidence(evidence_id: str = "ev-closure") -> dict:
    return {
        "schema_version": "evidence-object/v1",
        "evidence_id": evidence_id,
        "fact_ref": "metric.alpha",
        "source_id": "source-1",
        "method": "computed",
        "excerpt": "Computed from source-1.",
    }


def _closure_registry(repo: str, *, enabled: bool = True, role: str = "producer") -> dict:
    entry = _participant(repo, status="emitting", role=role)
    if enabled:
        entry["emitted_evidence_policy"] = "manifest-evidence-closure/v1"
    return _registry(entry)


@pytest.mark.parametrize("role", ["producer", "bridge"])
def test_manifest_evidence_closure_accepts_hashed_evidence_files(tmp_path: Path, role: str) -> None:
    envelope, manifest, run_json = _write_evidence_closure_run(
        tmp_path, evidence=[("evidence-1", _evidence())]
    )
    report = _validate(
        envelope,
        repo=envelope["repo"],
        registry=_closure_registry(envelope["repo"], role=role),
        manifest=manifest,
        run_json=run_json,
    )
    assert report.conformant, [violation.message for violation in report.violations]


def test_manifest_evidence_closure_ignores_non_object_explainability_artifact(
    tmp_path: Path,
) -> None:
    """Inv-Man labels its explainability summary as evidence, not evidence-object/v1."""
    envelope, manifest, run_json = _write_evidence_closure_run(
        tmp_path, evidence=[("evidence-1", _evidence())]
    )
    explanation = tmp_path / "explainability.json"
    explanation.write_text(json.dumps({"summary": "not an evidence object"}), encoding="utf-8")
    manifest["artifacts"].append(
        {
            "artifact_id": "explainability.json",
            "name": explanation.name,
            "kind": "evidence",
            "path": explanation.name,
            "sha256": hashlib.sha256(explanation.read_bytes()).hexdigest(),
        }
    )

    report = _validate(
        envelope,
        repo=envelope["repo"],
        registry=_closure_registry(envelope["repo"]),
        manifest=manifest,
        run_json=run_json,
    )
    assert report.conformant, [violation.message for violation in report.violations]


def test_manifest_evidence_closure_rejects_schema_break_even_with_updated_hash(
    tmp_path: Path,
) -> None:
    bad_evidence = _evidence()
    bad_evidence["method"] = "corrupt-but-rehashed"
    envelope, manifest, run_json = _write_evidence_closure_run(
        tmp_path, evidence=[("evidence-1", bad_evidence)]
    )
    report = _validate(
        envelope,
        repo=envelope["repo"],
        registry=_closure_registry(envelope["repo"]),
        manifest=manifest,
        run_json=run_json,
    )
    assert not report.conformant
    assert not any("SHA-256" in violation.message for violation in report.violations)
    assert any(
        "evidence schema validation failed (enum)" in violation.message
        for violation in report.violations
    )
    assert all("corrupt-but-rehashed" not in violation.message for violation in report.violations)


def test_manifest_evidence_schema_error_redacts_excerpt(tmp_path: Path) -> None:
    secret_excerpt = "PRIVATE-SOURCE-TEXT" + "x" * 2000
    bad_evidence = _evidence()
    bad_evidence["excerpt"] = secret_excerpt
    envelope, manifest, run_json = _write_evidence_closure_run(
        tmp_path, evidence=[("evidence-1", bad_evidence)]
    )
    report = _validate(
        envelope,
        repo=envelope["repo"],
        registry=_closure_registry(envelope["repo"]),
        manifest=manifest,
        run_json=run_json,
    )
    assert not report.conformant
    assert any(
        "evidence schema validation failed (maxLength)" in v.message for v in report.violations
    )
    assert all("PRIVATE-SOURCE-TEXT" not in v.message for v in report.violations)


def test_standalone_evidence_schema_error_redacts_excerpt(tmp_path: Path) -> None:
    secret_excerpt = "PRIVATE-STANDALONE-TEXT" + "x" * 2000
    evidence = _evidence()
    evidence["excerpt"] = secret_excerpt
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    report = vrc.validate_evidence_objects(paths=[path], schema_dir=SCHEMA_DIR)
    assert not report.conformant
    assert any(
        "evidence schema validation failed (maxLength)" in v.message for v in report.violations
    )
    assert all("PRIVATE-STANDALONE-TEXT" not in v.message for v in report.violations)


@pytest.mark.parametrize(
    "case",
    [
        "dangling",
        "orphan",
        "duplicate",
        "hash",
        "traversal",
        "missing",
        "missing_manifest",
        "missing_file",
        "malformed",
        "malformed_entry",
    ],
)
def test_manifest_evidence_closure_rejects_broken_closure(tmp_path: Path, case: str) -> None:
    evidence = [("evidence-1", _evidence("ev-1"))]
    refs: list[str] | None = None
    mutate = None
    if case == "dangling":
        refs = ["ev-missing"]
    elif case == "orphan":
        refs = []
    elif case == "duplicate":
        evidence.append(("evidence-2", _evidence("ev-1")))
    elif case == "hash":

        def mutate(manifest: dict) -> None:
            manifest["artifacts"][0].update(sha256="0" * 64)

    elif case == "traversal":

        def mutate(manifest: dict) -> None:
            manifest["artifacts"][0].update(path="../escape.json")

    elif case == "missing_file":

        def mutate(manifest: dict) -> None:
            manifest["artifacts"][0].update(path="missing.json")

    elif case == "malformed":

        def mutate(manifest: dict) -> None:
            manifest["artifacts"][0].update(path=7)

    elif case == "malformed_entry":

        def mutate(manifest: dict) -> None:
            manifest["artifacts"].append(None)

    envelope, manifest, run_json = _write_evidence_closure_run(
        tmp_path, evidence=evidence, refs=refs, mutate_manifest=mutate
    )
    report = _validate(
        envelope,
        repo=envelope["repo"],
        registry=_closure_registry(envelope["repo"]),
        manifest=None if case == "missing_manifest" else manifest,
        run_json=None if case == "missing" else run_json,
    )
    assert not report.conformant, case
    expected = {
        "dangling": "has no emitted evidence artifact",
        "orphan": "is absent from evidence_refs",
        "duplicate": "duplicate evidence_id",
        "hash": "SHA-256 does not match",
        "traversal": "must not be absolute or traverse parents",
        "missing": "requires run_json artifact context",
        "missing_manifest": "requires an artifact manifest",
        "missing_file": "cannot resolve evidence artifact",
        "malformed": "must be a non-empty relative POSIX path",
        "malformed_entry": "manifest:",
    }[case]
    assert any(expected in violation.message for violation in report.violations)


def test_manifest_evidence_closure_is_disabled_without_exact_policy(tmp_path: Path) -> None:
    envelope, manifest, run_json = _write_evidence_closure_run(
        tmp_path,
        evidence=[("evidence-1", _evidence())],
        mutate_manifest=lambda manifest: manifest["artifacts"][0].update(path="missing.json"),
    )
    report = _validate(
        envelope,
        repo=envelope["repo"],
        registry=_closure_registry(envelope["repo"], enabled=False),
        manifest=manifest,
        run_json=run_json,
    )
    assert report.conformant


def test_required_format_checker_fails_closed_for_missing_and_ineffective_formats(
    monkeypatch,
) -> None:
    monkeypatch.delitem(vrc.FormatChecker.checkers, "uri", raising=False)
    with pytest.raises(RuntimeError, match="unavailable: uri"):
        vrc._required_format_checker("uri")

    monkeypatch.setattr(vrc.FormatChecker, "conforms", lambda *_args: True)
    with pytest.raises(RuntimeError, match="ineffective: date-time"):
        vrc._required_format_checker("date-time")


def test_standalone_validators_enforce_document_page_consistency(tmp_path: Path) -> None:
    evidence = _evidence("ev-page")
    evidence["document_ref"] = {"sha256": "same", "supersedes": "same", "doc_key": "a/2026-1-01"}
    evidence["locator"] = {"page": 2}
    evidence["document_ref"]["page"] = 1
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    report = vrc.validate_evidence_objects(paths=[path], schema_dir=SCHEMA_DIR)

    assert not report.conformant
    assert {violation.path for violation in report.violations} >= {
        f"{path}:/document_ref/supersedes",
        f"{path}:/document_ref/page",
        f"{path}:/document_ref/doc_key",
    }


@pytest.mark.parametrize(
    ("mode", "fixture", "expected_repo"),
    [
        ("--tracked-variables", "valid_tracked_variable.json", "tracked-variable/v1"),
        ("--mirror-manifest", "valid_document_mirror.json", "document-mirror/v1"),
    ],
)
def test_standalone_cli_modes_write_success_reports(
    tmp_path: Path, mode: str, fixture: str, expected_repo: str
) -> None:
    report_path = tmp_path / "report.json"
    output_path = tmp_path / "github-output"

    assert (
        vrc.main(
            [
                mode,
                str(FIXTURES / fixture),
                "--schema-dir",
                str(SCHEMA_DIR),
                "--report-json",
                str(report_path),
                "--github-output",
                str(output_path),
            ]
        )
        == 0
    )
    assert json.loads(report_path.read_text())["repo"] == expected_repo
    assert output_path.read_text() == "conformant=true\n"


def test_consumer_convention_only_and_unknown_ingests_are_distinguished() -> None:
    repo = "stranske/Convention-Only"
    convention = _validate(
        {"anything": "allowed"},
        repo=repo,
        registry=_registry(
            _participant(repo, role="consumer", ingests=["identity-map-conventions"])
        ),
    )
    assert convention.conformant

    unknown = _validate(
        {"anything": "allowed"},
        repo=repo,
        registry=_registry(_participant(repo, role="consumer", ingests=["unknown/v1"])),
    )
    assert not unknown.conformant
    assert "unknown ingest schema token 'unknown/v1'" in unknown.violations[0].message


def test_missing_active_envelope_is_a_failure_and_cli_persists_result(tmp_path: Path) -> None:
    repo = "stranske/Active"
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(_registry(_participant(repo))), encoding="utf-8")
    report_path = tmp_path / "report.json"
    output_path = tmp_path / "github-output"

    assert (
        vrc.main(
            [
                str(tmp_path / "missing.json"),
                "--registry",
                str(registry_path),
                "--repo",
                repo,
                "--schema-dir",
                str(SCHEMA_DIR),
                "--report-json",
                str(report_path),
                "--github-output",
                str(output_path),
            ]
        )
        == 1
    )
    assert json.loads(report_path.read_text())["conformant"] is False
    assert output_path.read_text() == "conformant=false\n"


def test_unknown_evidence_policy_and_noncanonical_schema_version_fail() -> None:
    repo = "stranske/Bad-Policy"
    registry = _registry(_participant(repo))
    registry["participants"][0]["emitted_evidence_policy"] = "unknown/v1"
    report = _validate(
        _minimal_run_envelope(repo=repo, schema_version="wrong/v1"),
        repo=repo,
        registry=registry,
    )

    assert not report.conformant
    assert {violation.path for violation in report.violations} >= {
        "schema_version",
        "emitted_evidence_policy",
    }


def test_standalone_validators_report_unreadable_and_invalid_documents(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    tracked = vrc.validate_tracked_variables(paths=[missing], schema_dir=SCHEMA_DIR)
    mirror = vrc.validate_mirror_manifests(paths=[missing], schema_dir=SCHEMA_DIR)

    assert tracked.violations[0].path == str(missing)
    assert mirror.violations[0].path == str(missing)

    invalid_tracked = FIXTURES / "invalid_tracked_variable_missing_evidence.json"
    invalid_mirror = FIXTURES / "invalid_document_mirror_bad_urls.json"
    assert not vrc.validate_tracked_variables(
        paths=[invalid_tracked], schema_dir=SCHEMA_DIR
    ).conformant
    assert not vrc.validate_mirror_manifests(
        paths=[invalid_mirror], schema_dir=SCHEMA_DIR
    ).conformant


def test_self_smoke_exercises_bundled_schemas_and_fixtures(capsys) -> None:
    assert vrc._self_smoke(SCHEMA_DIR, ROOT / "config" / "backplane_participants.json") == 0
    output = capsys.readouterr().out
    assert "PASS schema loads + valid Draft202012: run-contract-v1.schema.json" in output
    assert "PASS fixture valid_run.json: expected conform" in output


def test_main_rejects_ambiguous_or_missing_envelope_arguments() -> None:
    with pytest.raises(SystemExit, match="2"):
        vrc.main(["--evidence-objects", "one.json", "--tracked-variables", "two.json"])
    with pytest.raises(SystemExit, match="2"):
        vrc.main([])


def test_main_reports_missing_positional_envelope_after_registry_load(
    tmp_path: Path, capsys
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(_registry()), encoding="utf-8")

    assert vrc.main(["--registry", str(registry_path), "--repo", "stranske/None"]) == 2
    assert "run_json path is required" in capsys.readouterr().err


def test_document_page_accepts_unknown_and_skips_non_string_doc_key() -> None:
    report = vrc.Report(repo="owner/repo")
    vrc._check_document_page(
        {"document_ref": {"sha256": "a" * 64, "doc_key": "document/unknown"}}, report
    )
    vrc._check_document_page({"document_ref": {"sha256": "a" * 64, "doc_key": 3}}, report)
    assert report.conformant


def test_safe_evidence_path_rejects_parent_traversal(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    report = vrc.Report(repo="owner/repo")
    assert vrc._safe_evidence_path(run_dir, {"path": "../outside.json"}, report, 0) is None
    assert any("must not be absolute or traverse parents" in v.message for v in report.violations)


def test_safe_evidence_path_escape_check_after_resolve(tmp_path: Path, monkeypatch) -> None:
    """Cover the post-resolve escape fail (377–378).

    Explicit ``..`` / symlink rejects run first, so a normal relative path cannot
    reach this branch. Force ``is_relative_to`` false after resolve succeeds.
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    evidence = run_dir / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")

    real_is_relative_to = Path.is_relative_to

    def _force_escape(self: Path, other: Path) -> bool:
        if self.resolve() == evidence.resolve():
            return False
        return real_is_relative_to(self, other)

    monkeypatch.setattr(Path, "is_relative_to", _force_escape)
    report = vrc.Report(repo="owner/repo")
    assert vrc._safe_evidence_path(run_dir, {"path": "evidence.json"}, report, 0) is None
    assert any("escapes the run directory" in v.message for v in report.violations)


def test_manifest_evidence_requires_string_sha256(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    evidence = run_dir / "evidence-1.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "evidence-object/v1",
                "evidence_id": "ev-1",
                "kind": "citation",
                "document_ref": {"sha256": "a" * 64, "doc_key": "document/unknown"},
                "locator": {"page": 1},
                "excerpt": "ok",
            }
        ),
        encoding="utf-8",
    )
    repo = "stranske/Evidence-Sha"
    registry = _registry(
        {
            **_participant(repo),
            "emitted_evidence_policy": vrc.EMITTED_EVIDENCE_POLICY,
            "status": "emitting",
        }
    )
    envelope = _minimal_run_envelope(repo=repo)
    manifest = {
        "schema_version": "artifact-manifest/v1",
        "run_id": envelope["run_id"],
        "artifacts": [
            {
                "artifact_id": "evidence-1",
                "kind": "evidence",
                "name": "evidence-1.json",
                "path": "evidence-1.json",
                "sha256": 12,
            }
        ],
    }
    report = _validate(
        envelope,
        repo=repo,
        registry=registry,
        manifest=manifest,
        run_json=run_dir / "run.json",
    )
    (run_dir / "run.json").write_text("{}", encoding="utf-8")
    report = _validate(
        envelope,
        repo=repo,
        registry=registry,
        manifest=manifest,
        run_json=run_dir / "run.json",
    )
    assert any("sha256 must be a string" in v.message for v in report.violations)


def test_unknown_required_section_and_non_list_manifest_artifacts() -> None:
    repo = "stranske/Unknown-Section"
    registry = _registry(_participant(repo, required_sections=["not_a_real_section", "cost"]))
    report = _validate(
        _minimal_run_envelope(repo=repo, cost={"usd": 1}),
        repo=repo,
        registry=registry,
        manifest={"schema_version": "artifact-manifest/v1", "artifacts": "bad"},
    )
    assert any("unknown required section" in v.message for v in report.violations)


def test_identity_ref_without_colon_fails() -> None:
    repo = "stranske/Bad-Identity"
    report = _validate(
        _minimal_run_envelope(repo=repo, identity_refs=["not-canonical"]),
        repo=repo,
        registry=_registry(_participant(repo)),
    )
    assert any("canonical <type>:<id>" in v.message for v in report.violations)


def test_main_reports_unreadable_run_envelope(tmp_path: Path, capsys) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(_registry()), encoding="utf-8")
    bad = tmp_path / "run.json"
    bad.write_text("{not-json", encoding="utf-8")
    assert (
        vrc.main(
            [
                str(bad),
                "--registry",
                str(registry_path),
                "--repo",
                "stranske/None",
                "--schema-dir",
                str(SCHEMA_DIR),
            ]
        )
        == 2
    )
    assert "cannot load run envelope" in capsys.readouterr().err


def test_self_smoke_notes_missing_fixture_directory(tmp_path: Path, capsys, monkeypatch) -> None:
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    for name in vrc.INGEST_SCHEMA_FILES.values():
        (schema_dir / name).write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                }
            ),
            encoding="utf-8",
        )
    # Also need run-contract schema files that _self_smoke loads by glob
    for name in ("run-contract-v1.schema.json", "artifact-manifest-v1.schema.json"):
        (schema_dir / name).write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                }
            ),
            encoding="utf-8",
        )
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(_registry()), encoding="utf-8")
    monkeypatch.setattr(vrc, "__file__", str(tmp_path / "validate_run_contract.py"))
    assert vrc._self_smoke(schema_dir, registry_path) == 0
    assert "no fixtures found; schema-only self-smoke" in capsys.readouterr().out


def test_standalone_mode_writes_github_output_on_failure(tmp_path: Path) -> None:
    output = tmp_path / "out.txt"
    missing = tmp_path / "missing.json"
    assert (
        vrc.main(
            [
                "--evidence-objects",
                str(missing),
                "--schema-dir",
                str(SCHEMA_DIR),
                "--github-output",
                str(output),
            ]
        )
        == 1
    )
    assert "conformant=false" in output.read_text(encoding="utf-8")
