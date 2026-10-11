"""Tests for capture obligation manifest derivation."""

from __future__ import annotations

import copy
import json

import pytest
from tools.verifier_capture_obligation_manifest import (
    SCHEMA,
    build_capture_obligation_manifest,
    parse_context_source_coverage,
)


def _context_block(coverage: dict) -> str:
    return (
        "## Context source coverage\n\n```json\n"
        + json.dumps(coverage)
        + "\n```\n\n## CI Information\n"
    )


def test_parse_context_source_coverage_extracts_json_block() -> None:
    coverage = {"schema": "verifier-context-source-coverage/v1", "changed_code_sources": []}
    text = _context_block(coverage)
    assert parse_context_source_coverage(text) == coverage


def test_manifest_marks_truncated_changed_code_insufficient() -> None:
    coverage = {
        "schema": "verifier-context-source-coverage/v1",
        "stage": "generated-context",
        "acceptance_sources": [
            {"source": "issue:3820", "status": "included", "included_chars": 12, "total_chars": 12}
        ],
        "changed_code_sources": [
            {
                "source": "src/a.py",
                "status": "truncated",
                "included_chars": 10,
                "total_chars": 100,
            }
        ],
        "acceptance_evidence_sources": [],
        "full_diff_artifact": {
            "source": "verifier-pr-diff.patch",
            "chars": 100,
            "status": "included",
        },
    }
    manifest = build_capture_obligation_manifest(_context_block(coverage))
    assert manifest["schema"] == SCHEMA
    assert manifest["sufficient"] is False
    assert "changed_code:src/a.py:truncated" in manifest["gaps"]


def test_manifest_passes_when_all_required_sources_included() -> None:
    coverage = {
        "schema": "verifier-context-source-coverage/v1",
        "stage": "generated-context",
        "acceptance_sources": [
            {"source": "issue:3820", "status": "included", "included_chars": 12, "total_chars": 12}
        ],
        "acceptance_source_discovery": {"required": True, "status": "included"},
        "changed_code_sources": [
            {"source": "src/a.py", "status": "included", "included_chars": 100, "total_chars": 100}
        ],
        "acceptance_evidence_sources": [
            {"source": "comments", "status": "included", "included_chars": 50, "total_chars": 50}
        ],
        "full_diff_artifact": {
            "source": "verifier-pr-diff.patch",
            "chars": 100,
            "status": "included",
        },
    }
    manifest = build_capture_obligation_manifest(_context_block(coverage))
    assert manifest["sufficient"] is True
    assert manifest["gaps"] == []


def _complete_coverage() -> dict:
    return {
        "schema": "verifier-context-source-coverage/v1",
        "stage": "generated-context",
        "changed_code_sources": [
            {"source": "a.py", "status": "included", "included_chars": 10, "total_chars": 10}
        ],
        "acceptance_sources": [
            {"source": "issue:3820", "status": "included", "included_chars": 10, "total_chars": 10}
        ],
        "acceptance_evidence_sources": [],
        "full_diff_artifact": {
            "source": "verifier-pr-diff.patch",
            "chars": 10,
            "status": "included",
        },
    }


def test_real_builder_prose_is_parsed() -> None:
    coverage = _complete_coverage()
    text = _context_block(coverage).replace(
        "## Context source coverage\n\n",
        "## Context source coverage\n\nComputed before model invocation. Status and character counts describe sources retained in this generated context.\n\n",
    )
    assert parse_context_source_coverage(text) == coverage
    assert build_capture_obligation_manifest(text)["sufficient"] is True


@pytest.mark.parametrize("prefix", ["## CI Information\n", "#", "quoted: "])
def test_untrusted_or_unanchored_inventory_is_rejected(prefix: str) -> None:
    text = prefix + _context_block(_complete_coverage())
    assert parse_context_source_coverage(text) is None
    assert build_capture_obligation_manifest(text)["sufficient"] is False


@pytest.mark.parametrize(
    "field",
    [
        "schema",
        "stage",
        "changed_code_sources",
        "acceptance_sources",
        "acceptance_evidence_sources",
        "full_diff_artifact",
    ],
)
def test_missing_required_inventory_field_is_insufficient(field: str) -> None:
    coverage = _complete_coverage()
    del coverage[field]
    assert build_capture_obligation_manifest(_context_block(coverage))["sufficient"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "future/v2"),
        ("stage", "post-model"),
        ("changed_code_sources", []),
        ("acceptance_sources", []),
        ("acceptance_evidence_sources", {}),
        ("full_diff_artifact", {}),
    ],
)
def test_invalid_inventory_is_insufficient(field: str, value: object) -> None:
    coverage = _complete_coverage()
    coverage[field] = value
    assert build_capture_obligation_manifest(_context_block(coverage))["sufficient"] is False


@pytest.mark.parametrize(
    "kind", ["changed_code_sources", "acceptance_sources", "acceptance_evidence_sources"]
)
@pytest.mark.parametrize(
    "change",
    [
        {"source": ""},
        {"source": None},
        {"status": "error"},
        {"status": []},
        {"included_chars": 1},
        {"included_chars": -1},
        {"included_chars": True},
        {"included_chars": "10"},
        {"total_chars": None},
        {"total_chars": False},
    ],
)
def test_invalid_record_cannot_authorize_capture(kind: str, change: dict) -> None:
    coverage = _complete_coverage()
    record = copy.deepcopy(coverage["changed_code_sources"][0])
    record.update(change)
    coverage[kind] = [record]
    assert build_capture_obligation_manifest(_context_block(coverage))["sufficient"] is False


def test_required_acceptance_source_gap_is_retained() -> None:
    coverage = _complete_coverage()
    coverage["acceptance_sources"][0]["status"] = "unavailable"
    manifest = build_capture_obligation_manifest(_context_block(coverage))
    assert manifest["sufficient"] is False
    assert "acceptance_source:issue:3820:unavailable" in manifest["gaps"]


def test_unknown_total_and_aggregate_unavailability_remain_gaps() -> None:
    coverage = _complete_coverage()
    coverage["acceptance_evidence_sources"] = [
        {"source": "artifact:1", "status": "truncated", "included_chars": 10, "total_chars": None},
        {"source": "artifacts", "status": "unavailable", "reason": "extraction_incomplete"},
    ]
    manifest = build_capture_obligation_manifest(_context_block(coverage))
    assert manifest["sufficient"] is False
    assert len(manifest["obligations"]) == 5
    assert "acceptance_evidence:artifact:1:truncated" in manifest["gaps"]
    assert "acceptance_evidence:artifacts:unavailable" in manifest["gaps"]


def test_duplicate_json_keys_and_duplicate_inventories_are_rejected() -> None:
    text = _context_block(_complete_coverage())
    assert parse_context_source_coverage(text + text) is not None  # second is after CI boundary
    assert (
        parse_context_source_coverage(text.replace('"stage":', '"schema":"wrong", "stage":'))
        is None
    )
    preamble = text.split("## CI Information")[0]
    assert parse_context_source_coverage(preamble + preamble) is None


def test_duplicate_source_identity_is_insufficient() -> None:
    coverage = _complete_coverage()
    coverage["changed_code_sources"] *= 2
    assert build_capture_obligation_manifest(_context_block(coverage))["sufficient"] is False


def test_missing_trust_boundary_is_insufficient() -> None:
    text = _context_block(_complete_coverage()).split("## CI Information")[0]
    assert parse_context_source_coverage(text) is None
    assert build_capture_obligation_manifest(text)["sufficient"] is False


def test_loaded_diff_change_is_rejected_without_snapshot_rebinding(tmp_path):
    from tools.verifier_capture_obligation_manifest import record_capture_obligations

    context = tmp_path / "context.md"
    context.write_text("context")
    diff = tmp_path / "diff.patch"
    diff.write_text("changed after load")
    with pytest.raises(ValueError, match="loaded diff changed"):
        record_capture_obligations(
            context, context_text="context", diff_path=diff, diff_text="original loaded view"
        )
    assert not (tmp_path / "verifier-capture-obligation-manifest.json").exists()


@pytest.mark.parametrize("size", [0, 1, 65535, 65536, 65537, 131079])
def test_raw_byte_inventory_reassembles_every_byte(size):
    from tools.verifier_capture_obligation_manifest import build_capture_byte_inventory

    # Slice through UTF-8 code points and retain CRLF/whitespace exactly.
    raw = ("é\r\n ".encode() * (size + 1))[:size]
    inventory = build_capture_byte_inventory({"context": raw, "diff": b"diff\r\n"})
    assert inventory["schema"] == "workflows-verifier-capture-byte-inventory/v1"
    for item in inventory["inputs"]:
        original = {"context": raw, "diff": b"diff\r\n"}[item["input"]]
        chunks = [original[r["start"] : r["end"]] for r in item["ranges"]]
        assert b"".join(chunks) == original
        assert all(len(chunk) <= 65536 for chunk in chunks)
        assert item["bytes"] == len(original)
        assert len({r["id"] for r in item["ranges"]}) == len(chunks)
    assert inventory == build_capture_byte_inventory({"diff": b"diff\r\n", "context": raw})


@pytest.mark.parametrize("damage", ["drop", "duplicate", "hash", "offset", "identity", "unknown"])
def test_byte_inventory_rejects_incomplete_or_conflicting_ranges(damage):
    from tools.verifier_capture_obligation_manifest import (
        build_capture_byte_inventory,
        validate_capture_byte_inventory,
    )

    inputs = {"context": b"first\r\n" + b"x" * 70000, "diff": b"late proof"}
    inventory = build_capture_byte_inventory(inputs)
    validate_capture_byte_inventory(inventory, inputs)
    ranges = inventory["inputs"][0]["ranges"]
    if damage == "drop":
        ranges.pop()
    elif damage == "duplicate":
        ranges.append(copy.deepcopy(ranges[0]))
    elif damage == "hash":
        ranges[0]["sha256"] = "0" * 64
    elif damage == "offset":
        ranges[0]["start"] = 1
    elif damage == "identity":
        ranges[0]["id"] = "substituted"
    else:
        inventory["schema"] = "unknown"
    with pytest.raises(ValueError, match="byte inventory"):
        validate_capture_byte_inventory(inventory, inputs)


def test_record_binds_raw_ranges_and_rejects_tampered_snapshot(tmp_path):
    import hashlib

    from tools.verifier_capture_obligation_manifest import record_capture_obligations

    raw = _context_block(_complete_coverage()).replace("\n", "\r\n").encode()
    context = tmp_path / "context.md"
    context.write_bytes(raw)
    diff = tmp_path / "diff.patch"
    diff.write_bytes(b"proof\r\n")
    snapshot_path = tmp_path / "verifier-input-manifest.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "schema": "workflows-verifier-input-snapshot/v1",
                "context_sha256": hashlib.sha256(raw).hexdigest(),
                "diff_sha256": hashlib.sha256(diff.read_bytes()).hexdigest(),
            }
        )
    )
    record_capture_obligations(context, diff_path=diff)
    snapshot = json.loads(snapshot_path.read_text())
    assert (
        snapshot["capture_byte_inventory"]["inputs"][0]["sha256"] == hashlib.sha256(raw).hexdigest()
    )
    snapshot["capture_byte_inventory"]["inputs"][1]["ranges"].clear()
    snapshot_path.write_text(json.dumps(snapshot))
    before = snapshot_path.read_bytes()
    with pytest.raises(ValueError, match="byte inventory"):
        record_capture_obligations(context, diff_path=diff)
    assert snapshot_path.read_bytes() == before
    assert context.read_bytes() == raw
    assert diff.read_bytes() == b"proof\r\n"


def test_incomplete_evidence_remains_insufficient_with_complete_raw_ranges(tmp_path):
    from tools.verifier_capture_obligation_manifest import record_capture_obligations

    coverage = _complete_coverage()
    coverage["acceptance_evidence_sources"] = [{"source": "late-proof", "status": "unavailable"}]
    context = tmp_path / "context.md"
    context.write_text(_context_block(coverage))
    result = record_capture_obligations(context)
    assert result["sufficient"] is False
    assert "acceptance_evidence:late-proof:unavailable" in result["gaps"]
    byte_inventory = json.loads((tmp_path / "verifier-capture-byte-inventory.json").read_text())
    assert byte_inventory["inputs"][0]["bytes"] == len(context.read_bytes())
