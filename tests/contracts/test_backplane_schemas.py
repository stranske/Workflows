"""P0.1 acceptance: backplane schemas load and are self-consistent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "contracts" / "schemas"
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "backplane"

SCHEMAS = {
    "run-contract-v1.schema.json": "run-contract/v1",
    "artifact-manifest-v1.schema.json": "artifact-manifest/v1",
    "evidence-object-v1.schema.json": "evidence-object/v1",
    "tracked-variable-v1.schema.json": "tracked-variable/v1",
    "mosaic-core-v1.schema.json": "mosaic-core/v1",
    "document-mirror-v1.schema.json": "document-mirror/v1",
    "output-substrate-v1.schema.json": "output-substrate/v1",
}


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


def _validator(name: str) -> Draft202012Validator:
    schema = _load(name)
    if name != "tracked-variable-v1.schema.json":
        return Draft202012Validator(schema)
    evidence = _load("evidence-object-v1.schema.json")
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema)),
            (evidence["$id"], Resource.from_contents(evidence)),
        ]
    )
    return Draft202012Validator(schema, registry=registry)


@pytest.mark.parametrize("name,const", SCHEMAS.items())
def test_schema_loads_and_is_valid_draft_2020_12(name: str, const: str) -> None:
    schema = _load(name)
    # Raises SchemaError if the schema itself is malformed.
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith(name)
    assert schema["title"]
    assert schema["properties"]["schema_version"]["const"] == const


def test_run_contract_requires_exact_shared_fields() -> None:
    schema = _load("run-contract-v1.schema.json")
    assert sorted(schema["required"]) == sorted(
        [
            "schema_version",
            "repo",
            "tool",
            "run_id",
            "status",
            "actor",
            "inputs",
            "outputs",
            "provenance",
            "github_issue",
        ]
    )


def test_identity_ref_pattern_is_canonical() -> None:
    schema = _load("run-contract-v1.schema.json")
    pat = schema["properties"]["identity_refs"]["items"]["pattern"]
    assert pat == r"^[a-z0-9_]+:[a-z0-9][a-z0-9_.:-]*$"


def test_manifest_path_rejects_traversal() -> None:
    schema = _load("artifact-manifest-v1.schema.json")
    item = schema["properties"]["artifacts"]["items"]
    assert sorted(item["required"]) == sorted(["artifact_id", "name", "path", "sha256"])
    assert item["properties"]["sha256"]["pattern"] == r"^[a-f0-9]{64}$"


def test_evidence_object_requires_method_and_excerpt_present() -> None:
    schema = _load("evidence-object-v1.schema.json")
    assert "method" in schema["required"]
    assert "excerpt" in schema["required"]
    # excerpt must be PRESENT (string or explicit null) -> nullable string type.
    assert schema["properties"]["excerpt"]["type"] == ["string", "null"]

    validator = Draft202012Validator(schema)
    evidence = {
        "schema_version": "evidence-object/v1",
        "evidence_id": "ev-1",
        "fact_ref": "metric.alpha",
        "source_id": "source-1",
        "method": "computed",
    }
    assert any(error.validator == "required" for error in validator.iter_errors(evidence))
    evidence["excerpt"] = None
    assert not list(validator.iter_errors(evidence))


def test_document_mirror_fixture_validates() -> None:
    """Deliberate-break gate for issue #3373.

    Remove Backstop/SharePoint source object support, empty ``blobs``/``source_refs``,
    or Windows-path rejection from the schema and this test must fail.
    """
    validator = _validator("document-mirror-v1.schema.json")

    valid = json.loads((FIXTURES / "valid_document_mirror.json").read_text())
    assert not list(validator.iter_errors(valid))

    empty = json.loads((FIXTURES / "valid_empty_document_mirror.json").read_text())
    assert not list(validator.iter_errors(empty))

    local_only = json.loads((FIXTURES / "valid_document_mirror.json").read_text())
    assert local_only["blobs"][2]["source_refs"] == []
    assert not list(validator.iter_errors(local_only))

    invalid_source = json.loads((FIXTURES / "valid_document_mirror.json").read_text())
    invalid_source["blobs"][0]["source_refs"] = [{"system": "backstop"}]
    assert list(validator.iter_errors(invalid_source))

    invalid_sharepoint = json.loads((FIXTURES / "valid_document_mirror.json").read_text())
    invalid_sharepoint["blobs"][1]["source_refs"] = [
        {"system": "sharepoint", "driveId": "b!abc", "itemId": "01XYZ"}
    ]
    assert list(validator.iter_errors(invalid_sharepoint))

    for index, field in ((0, "url"), (1, "web_url")):
        for url in (
            "http://example.com/document",
            "file:///tmp/document",
            "mailto:user@example.com",
            "https://",
            "https:///path",
            "https://?q=x",
            "https://user@example.com/path",
        ):
            invalid_resolver = json.loads((FIXTURES / "valid_document_mirror.json").read_text())
            invalid_resolver["blobs"][index]["source_refs"][1][field] = url
            assert list(validator.iter_errors(invalid_resolver)), (field, url)

    invalid_hash = json.loads((FIXTURES / "valid_document_mirror.json").read_text())
    invalid_hash["blobs"][0]["content_sha256"] = "a" * 63
    assert any(
        list(error.absolute_path) == ["blobs", 0, "content_sha256"] and error.validator == "pattern"
        for error in validator.iter_errors(invalid_hash)
    )

    for path in (
        "../escape.pdf",
        "/absolute.pdf",
        "blobs/../../escape.pdf",
        "C:\\Users\\doc.pdf",
        "C:/Users/doc.pdf",
        "\\\\server\\share\\doc.pdf",
        "//server/share/doc.pdf",
        "blobs\\sha256\\abc.pdf",
    ):
        broken = json.loads((FIXTURES / "valid_document_mirror.json").read_text())
        broken["blobs"][0]["blob_path"] = path
        assert list(validator.iter_errors(broken)), path


def test_tracked_variable_fixture_validates() -> None:
    validator = _validator("tracked-variable-v1.schema.json")

    valid = json.loads((FIXTURES / "valid_tracked_variable.json").read_text())
    # Removing the "evidence" key from valid_tracked_variable.json causes this
    # assertion to fail (verified during development).
    assert not list(validator.iter_errors(valid))

    invalid = json.loads((FIXTURES / "invalid_tracked_variable_missing_evidence.json").read_text())
    errors = list(validator.iter_errors(invalid))
    assert errors
    assert any(error.validator == "required" and "evidence" in error.message for error in errors)


@pytest.mark.parametrize("missing", ["document", "mirror"])
def test_tracked_variable_requires_both_provenance_anchors(missing: str) -> None:
    value = json.loads((FIXTURES / "valid_tracked_variable.json").read_text())
    del value["provenance"][missing]
    errors = list(_validator("tracked-variable-v1.schema.json").iter_errors(value))
    assert any(error.validator == "required" and missing in error.message for error in errors)


def test_tracked_variable_validates_embedded_evidence() -> None:
    value = json.loads((FIXTURES / "valid_tracked_variable.json").read_text())
    del value["evidence"]["method"]
    errors = list(_validator("tracked-variable-v1.schema.json").iter_errors(value))
    assert any(error.validator == "required" and "method" in error.message for error in errors)


def _mosaic_fixture(kind: str) -> dict:
    return json.loads((FIXTURES / f"valid_mosaic_{kind}.json").read_text())


def _mosaic_errors(value: dict) -> list:
    return list(_validator("mosaic-core-v1.schema.json").iter_errors(value))


def test_mosaic_core_fixture_validates() -> None:
    for kind in ("fact", "discrepancy", "thesis_claim", "thesis_check"):
        assert not _mosaic_errors(_mosaic_fixture(kind)), kind


@pytest.mark.parametrize(
    "field,value",
    [
        ("fact_key", ""),
        ("entity_ref", "Unscoped Fund"),
        ("schema_version", "mosaic-core/v2"),
        ("record_type", "unknown"),
        ("record_type", "thesis_claim"),
        ("status", "pending"),
        ("primary_evidence_id", ""),
        ("value", None),
        ("value", []),
        ("value", {"min": 1}),
        ("value", {"min": 1, "max": "two"}),
    ],
)
def test_mosaic_rejects_invalid_fact(field: str, value: object) -> None:
    fact = _mosaic_fixture("fact")
    fact[field] = value
    assert _mosaic_errors(fact)


@pytest.mark.parametrize("value", [1.25, "fixed", False, {"min": 1, "max": 2}])
def test_mosaic_fact_accepts_typed_values(value: object) -> None:
    fact = _mosaic_fixture("fact")
    fact["value"] = value
    assert not _mosaic_errors(fact)


@pytest.mark.parametrize("kind", ["fact", "discrepancy", "thesis_claim", "thesis_check"])
def test_mosaic_requires_discriminator_and_all_required_fields(kind: str) -> None:
    record = _mosaic_fixture(kind)
    # The fixtures express the consumer contract independently of the schema:
    # every populated field is required except these documented optional fields.
    optional = {"period", "expected_pattern"}
    for field in record.keys() - optional:
        incomplete = {key: value for key, value in record.items() if key != field}
        assert _mosaic_errors(incomplete), field
    record["consumer_extension"] = {"note": "additive v1 field"}
    assert not _mosaic_errors(record)


@pytest.mark.parametrize("verdict", ["supported", "at_risk", "contradicted"])
def test_mosaic_thesis_verdict_requires_evidence(verdict: str) -> None:
    check = _mosaic_fixture("thesis_check")
    check["verdict"] = verdict
    assert not _mosaic_errors(check)
    check["evidence_ids"] = []
    assert _mosaic_errors(check)
    check["verdict"] = "insufficient_evidence"
    assert not _mosaic_errors(check)
    check["verdict"] = "unknown"
    assert _mosaic_errors(check)


def test_mosaic_thesis_check_timestamp_and_unique_evidence() -> None:
    check = _mosaic_fixture("thesis_check")
    validator = Draft202012Validator(
        _load("mosaic-core-v1.schema.json"), format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    assert not list(validator.iter_errors(check))
    check["checked_at"] = "yesterday"
    assert list(validator.iter_errors(check))
    check = _mosaic_fixture("thesis_check")
    check["evidence_ids"] *= 2
    assert _mosaic_errors(check)


@pytest.mark.parametrize("status", ["accepted_primary", "immaterial", "resolved"])
def test_mosaic_discrepancy_resolution_requires_note(status: str) -> None:
    discrepancy = _mosaic_fixture("discrepancy")
    discrepancy["status"] = status
    assert _mosaic_errors(discrepancy)
    discrepancy["resolution_note"] = ""
    assert _mosaic_errors(discrepancy)
    discrepancy["resolution_note"] = "Analyst checked both primary documents."
    assert not _mosaic_errors(discrepancy)


@pytest.mark.parametrize("kind", ["numeric_delta", "sign_conflict", "narrative_conflict"])
def test_mosaic_conflict_requires_two_distinct_facts(kind: str) -> None:
    discrepancy = _mosaic_fixture("discrepancy")
    discrepancy["discrepancy_kind"] = kind
    assert not _mosaic_errors(discrepancy)
    discrepancy["fact_ids"] = ["fact:one"]
    assert _mosaic_errors(discrepancy)
    discrepancy["fact_ids"] *= 2
    assert _mosaic_errors(discrepancy)
    discrepancy["discrepancy_kind"] = "missing_in_source"
    discrepancy["fact_ids"] = ["fact:one"]
    assert not _mosaic_errors(discrepancy)
    discrepancy["fact_ids"] = []
    assert _mosaic_errors(discrepancy)


@pytest.mark.parametrize("field", ["fact_keys", "evidence_policy", "expected_pattern"])
def test_mosaic_claim_rejects_invalid_criteria(field: str) -> None:
    claim = _mosaic_fixture("thesis_claim")
    claim[field] = [] if field == "fact_keys" else "unknown"
    assert _mosaic_errors(claim)


@pytest.mark.parametrize(
    "kind",
    [
        "data",
        "report",
        "chart",
        "workbook",
        "log",
        "evidence",
        "envelope",
        "other",
        "tracked_variables",
        "mosaic_bundle",
        "output_substrate",
    ],
)
def test_manifest_accepts_existing_and_mosaic_kinds(kind: str) -> None:
    artifact = {
        "artifact_id": "artifact:one",
        "name": "bundle",
        "path": "out/bundle.json",
        "sha256": "a" * 64,
        "kind": kind,
    }
    manifest = {
        "schema_version": "artifact-manifest/v1",
        "run_id": "run:one",
        "tool": "fixture",
        "artifacts": [artifact],
    }
    validator = _validator("artifact-manifest-v1.schema.json")
    assert not list(validator.iter_errors(manifest))
    for path in ("../escape.json", "out/../../escape.json", "/absolute.json"):
        artifact["path"] = path
        assert list(validator.iter_errors(manifest)), path
    artifact["path"] = "out/bundle.json"
    artifact["kind"] = "unknown"
    assert list(validator.iter_errors(manifest))


def test_output_substrate_fixture_validates() -> None:
    validator = _validator("output-substrate-v1.schema.json")
    valid = json.loads((FIXTURES / "valid_output_substrate.json").read_text())
    # Removing the "renderer_profile" key from valid_output_substrate.json causes
    # this assertion to fail (verified during development).
    assert not list(validator.iter_errors(valid))


def test_output_substrate_csv_export_validates() -> None:
    """Deliberate-break gate for issue #3375.

    Set a column ``type`` to an invalid enum value and this test must fail.
    """
    validator = _validator("output-substrate-v1.schema.json")
    valid = json.loads((FIXTURES / "valid_output_substrate_with_csv.json").read_text())
    assert valid["manifest_csv_exports"][0]["columns"][0]["type"] == "string"
    assert valid["manifest_csv_exports"][1]["encoding"] == "utf-16-le"
    assert not list(validator.iter_errors(valid))

    invalid = json.loads((FIXTURES / "valid_output_substrate_with_csv.json").read_text())
    invalid["manifest_csv_exports"][0]["columns"][0]["type"] = "currency"
    errors = list(validator.iter_errors(invalid))
    assert errors
    assert any(
        list(error.absolute_path) == ["manifest_csv_exports", 0, "columns", 0, "type"]
        and error.validator == "enum"
        for error in errors
    )


def test_output_substrate_rejects_missing_renderer_profile() -> None:
    value = json.loads((FIXTURES / "valid_output_substrate.json").read_text())
    del value["renderer_profile"]
    errors = list(_validator("output-substrate-v1.schema.json").iter_errors(value))
    assert errors
    assert any(
        error.validator == "required" and "renderer_profile" in error.message for error in errors
    )


@pytest.mark.parametrize(
    "field,path",
    [
        ("workspace_bundle_ref", r"C:\view\workspace.json"),
        ("workspace_bundle_ref", "C:/view/workspace.json"),
        ("workspace_bundle_ref", r"\\server\share\workspace.json"),
        ("workspace_bundle_ref", "//server/share/workspace.json"),
        ("workspace_bundle_ref", "bundles/workspace/"),
        ("manifest_csv_exports", r"C:\exports\facts.csv"),
    ],
)
def test_output_substrate_rejects_non_posix_relative_paths(field: str, path: str) -> None:
    value = json.loads((FIXTURES / "valid_output_substrate.json").read_text())
    if field == "workspace_bundle_ref":
        value["workspace_bundle_ref"]["path"] = path
    else:
        value["manifest_csv_exports"][0]["filename"] = path
    assert list(_validator("output-substrate-v1.schema.json").iter_errors(value)), path


@pytest.mark.parametrize("path", ["x", "x.csv", "nested/x.csv"])
def test_output_substrate_accepts_nonempty_relative_csv_filenames(path: str) -> None:
    value = json.loads((FIXTURES / "valid_output_substrate.json").read_text())
    value["manifest_csv_exports"][0]["filename"] = path
    assert not list(_validator("output-substrate-v1.schema.json").iter_errors(value)), path


@pytest.mark.parametrize(
    "path", ["", ".", "nested/.", "/x.csv", "../x.csv", "nested/../x.csv", "nested/"]
)
def test_output_substrate_rejects_unsafe_csv_filenames(path: str) -> None:
    value = json.loads((FIXTURES / "valid_output_substrate.json").read_text())
    value["manifest_csv_exports"][0]["filename"] = path
    assert list(_validator("output-substrate-v1.schema.json").iter_errors(value)), path


def test_mosaic_contract_is_delivered_from_root() -> None:
    import yaml

    root = SCHEMA_DIR.parents[2]
    manifest = yaml.safe_load((root / ".github/sync-manifest.yml").read_text())
    entries = [
        entry
        for values in manifest.values()
        if isinstance(values, list)
        for entry in values
        if isinstance(entry, dict)
    ]
    for path in (
        "docs/contracts/mosaic-core-v1.md",
        "docs/contracts/schemas/mosaic-core-v1.schema.json",
        "docs/contracts/document-mirror-v1.md",
        "docs/contracts/schemas/document-mirror-v1.schema.json",
        "docs/contracts/output-substrate-v1.md",
        "docs/contracts/schemas/output-substrate-v1.schema.json",
    ):
        matches = [entry for entry in entries if entry.get("target") == path]
        assert len(matches) == 1
        assert matches[0]["source"] == path
        assert matches[0]["source_tree"] == "root"
        assert (root / path).is_file()
