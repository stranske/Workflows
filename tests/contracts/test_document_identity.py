"""Document identity contract coverage for direct and embedded evidence."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from scripts.validate_run_contract import validate_evidence_objects, validate_tracked_variables

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "docs" / "contracts" / "schemas"
FIXTURES = ROOT / "tests" / "fixtures" / "backplane"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _errors(document: dict) -> list[str]:
    schema = json.loads((SCHEMAS / "evidence-object-v1.schema.json").read_text())
    return [error.message for error in Draft202012Validator(schema).iter_errors(document)]


def test_native_and_ocr_evidence_fixtures_validate_in_contract_gate() -> None:
    paths = [
        FIXTURES / "valid_native_document_evidence.json",
        FIXTURES / "valid_ocr_document_evidence.json",
    ]
    report = validate_evidence_objects(paths=paths, schema_dir=SCHEMAS)
    assert report.conformant, [violation.message for violation in report.violations]


def test_legacy_evidence_without_document_ref_remains_valid() -> None:
    legacy = _fixture("valid_tracked_variable.json")["evidence"]
    assert legacy["excerpt"] and "document_ref" not in legacy
    assert not _errors(legacy)


def test_quote_requires_document_page() -> None:
    document = _fixture("valid_native_document_evidence.json")
    del document["document_ref"]["page"]
    assert any("page" in error for error in _errors(document))


def test_undeclared_doc_type_is_rejected() -> None:
    document = _fixture("valid_native_document_evidence.json")
    document["document_ref"]["doc_type"] = "spreadsheet"
    assert any("doc_type" in error or "spreadsheet" in error for error in _errors(document))


def test_doc_key_requires_entity_type_and_as_of() -> None:
    document = _fixture("valid_native_document_evidence.json")
    document["document_ref"]["doc_key"] = "renamed-letter.pdf"
    assert _errors(document)


def test_document_text_coverage_requires_explicit_text_basis() -> None:
    document = _fixture("valid_ocr_document_evidence.json")
    del document["document_ref"]["text_basis"]
    assert any("text_basis" in error for error in _errors(document))
    document["document_ref"]["text_basis"] = ""
    assert _errors(document)
    del document["document_ref"]
    assert any("document_ref" in error for error in _errors(document))


def test_supersession_requires_mechanism_evidence() -> None:
    document = _fixture("valid_ocr_document_evidence.json")
    del document["document_ref"]["supersession_evidence"]
    assert any("supersession_evidence" in error for error in _errors(document))


def test_duplicate_page_conflict_rejected_by_validator(tmp_path: Path) -> None:
    document = _fixture("valid_native_document_evidence.json")
    document["locator"]["page"] = 1
    path = tmp_path / "conflict.json"
    path.write_text(json.dumps(document))
    report = validate_evidence_objects(paths=[path], schema_dir=SCHEMAS)
    assert not report.conformant
    assert any("conflicts" in violation.message for violation in report.violations)


def test_embedded_tracked_variable_gets_same_document_page_check(tmp_path: Path) -> None:
    variable = _fixture("valid_tracked_variable.json")
    variable["evidence"]["document_ref"] = copy.deepcopy(
        _fixture("valid_native_document_evidence.json")["document_ref"]
    )
    variable["evidence"]["document_ref"]["page"] = 0
    path = tmp_path / "variable.json"
    path.write_text(json.dumps(variable))
    report = validate_tracked_variables(paths=[path], schema_dir=SCHEMAS)
    assert not report.conformant
    assert any("conflicts" in violation.message for violation in report.violations)
