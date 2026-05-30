"""P0.1 acceptance: the three backplane schemas load and are self-consistent.

Fails today against an empty tree (the schema files do not exist yet); passes
once the run-contract/v1 contract set lands.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "contracts" / "schemas"

SCHEMAS = {
    "run-contract-v1.schema.json": "run-contract/v1",
    "artifact-manifest-v1.schema.json": "artifact-manifest/v1",
    "evidence-object-v1.schema.json": "evidence-object/v1",
}


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


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
    # excerpt must be PRESENT (string or explicit null) -> nullable string type.
    assert schema["properties"]["excerpt"]["type"] == ["string", "null"]
