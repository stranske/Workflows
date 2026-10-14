"""Tests for capture obligation manifest derivation."""

from __future__ import annotations

import copy
import hashlib
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


def _verified_truncated_patch_coverage() -> tuple[dict, bytes]:
    patch = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -0,0 +1 @@\n"
        "+complete 😀 changed code\n"
    )
    raw_patch = patch.encode("utf-8")
    canonical_patch = patch[:-1]
    coverage = _complete_coverage()
    coverage["changed_code_sources"] = [
        {
            "source": "src/a.py",
            "from_path": "src/a.py",
            "status": "truncated",
            "included_chars": 20,
            "total_chars": len(canonical_patch),
            "start": 0,
            "end": len(canonical_patch.encode("utf-8")),
            "sha256": hashlib.sha256(canonical_patch.encode("utf-8")).hexdigest(),
        }
    ]
    coverage["full_diff_artifact"] = {
        "source": "verifier-pr-diff.patch",
        "status": "included",
        "chars": len(canonical_patch),
        "bytes": len(raw_patch),
        "sha256": hashlib.sha256(raw_patch).hexdigest(),
        "encoding": "utf-8",
    }
    return coverage, raw_patch


def test_verified_raw_full_patch_satisfies_truncated_changed_code() -> None:
    coverage, raw_patch = _verified_truncated_patch_coverage()
    manifest = build_capture_obligation_manifest(
        _context_block(coverage), full_diff_bytes=raw_patch
    )
    assert manifest["sufficient"] is True
    assert manifest["gaps"] == []
    assert manifest["obligations"][0]["status"] == "truncated"


@pytest.mark.parametrize("damage", ["raw", "artifact_hash", "span_hash", "span_range"])
def test_truncated_changed_code_needs_exact_raw_patch_span_binding(damage: str) -> None:
    coverage, raw_patch = _verified_truncated_patch_coverage()
    candidate = raw_patch
    if damage == "raw":
        candidate = raw_patch.replace(b"complete", b"tamperd!")
    elif damage == "artifact_hash":
        coverage["full_diff_artifact"]["sha256"] = "0" * 64
    elif damage == "span_hash":
        coverage["changed_code_sources"][0]["sha256"] = "0" * 64
    else:
        coverage["changed_code_sources"][0]["end"] = len(raw_patch)
    manifest = build_capture_obligation_manifest(
        _context_block(coverage), full_diff_bytes=candidate
    )
    assert manifest["sufficient"] is False
    assert any(
        gap.startswith(("full_diff_artifact:", "changed_code:src/a.py:"))
        for gap in manifest["gaps"]
    )
    assert "changed_code:src/a.py:truncated" in manifest["gaps"]


def test_recovery_rejects_malformed_changed_code_record_without_crashing() -> None:
    coverage, raw_patch = _verified_truncated_patch_coverage()
    coverage["changed_code_sources"].append([])
    manifest = build_capture_obligation_manifest(
        _context_block(coverage), full_diff_bytes=raw_patch
    )
    assert manifest["sufficient"] is False
    assert "changed_code:full_patch_record_count_mismatch" in manifest["gaps"]


def test_full_patch_recovery_requires_every_exact_file_identity_once() -> None:
    first = (
        "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n" "@@ -0,0 +1 @@\n+one\n"
    )
    second = (
        "diff --git a/src/b.py b/src/b.py\n--- a/src/b.py\n+++ b/src/b.py\n" "@@ -0,0 +1 @@\n+two\n"
    )
    patch = first + second
    raw_patch = patch.encode("utf-8")
    canonical_patch = patch[:-1]
    coverage = _complete_coverage()
    coverage["changed_code_sources"] = [
        {
            "source": "src/a.py",
            "from_path": "src/a.py",
            "status": "truncated",
            "included_chars": 1,
            "total_chars": len(first),
            "start": 0,
            "end": len(first.encode("utf-8")),
            "sha256": hashlib.sha256(first.encode("utf-8")).hexdigest(),
        },
        {
            "source": "src/b.py",
            "from_path": "src/b.py",
            "status": "omitted",
            "included_chars": 0,
            "total_chars": len(second),
            "start": len(first.encode("utf-8")),
            "end": len(canonical_patch.encode("utf-8")),
            "sha256": hashlib.sha256(second[:-1].encode("utf-8")).hexdigest(),
        },
    ]
    coverage["full_diff_artifact"] = {
        "source": "verifier-pr-diff.patch",
        "status": "included",
        "chars": len(canonical_patch),
        "bytes": len(raw_patch),
        "sha256": hashlib.sha256(raw_patch).hexdigest(),
        "encoding": "utf-8",
    }
    assert build_capture_obligation_manifest(_context_block(coverage), full_diff_bytes=raw_patch)[
        "sufficient"
    ]
    for mutation in ("header_only", "absent_source", "duplicate_span", "missing_file"):
        candidate = copy.deepcopy(coverage)
        records = candidate["changed_code_sources"]
        if mutation == "header_only":
            records[0]["end"] = len(b"diff --git ")
            records[0]["sha256"] = hashlib.sha256(b"diff --git ").hexdigest()
        elif mutation == "absent_source":
            records[0]["source"] = "src/not-in-patch.py"
        elif mutation == "duplicate_span":
            records[1] = copy.deepcopy(records[0])
            records[1]["source"] = "src/b.py"
            records[1]["from_path"] = "src/b.py"
        else:
            records.pop()
        manifest = build_capture_obligation_manifest(
            _context_block(candidate), full_diff_bytes=raw_patch
        )
        assert manifest["sufficient"] is False, mutation
        assert any("full_patch_" in gap for gap in manifest["gaps"]), mutation


def test_full_patch_recovery_rejects_header_only_section_even_with_matching_record() -> None:
    from tools.verifier_capture_obligation_manifest import _full_patch_file_records

    header = b"diff --git a/a.py b/a.py\n"
    assert _full_patch_file_records(header) is None
    assert _full_patch_file_records(header + b"index 123..456 100644\n") is None
    assert _full_patch_file_records(header + b"@@ -1 +1 @@\n") is None
    assert _full_patch_file_records(header + b"@@ -1 +1 @@\n-old\n+new\n") is not None
    assert _full_patch_file_records(header + b"old mode 100644\nnew mode 100755\n") is not None
    assert (
        _full_patch_file_records(
            b"diff --git a/a.py b/b.py\nsimilarity index 100%\nrename from a.py\nrename to b.py\n"
        )
        is not None
    )


def test_full_patch_recovery_rejects_metadata_identity_not_in_diff_header() -> None:
    from tools.verifier_capture_obligation_manifest import _full_patch_file_records

    forged = (
        b"diff --git a/src/actual.py b/src/actual.py\n"
        b"--- a/src/forged.py\n+++ b/src/forged.py\n@@ -0,0 +1 @@\n+proof\n"
    )
    assert _full_patch_file_records(forged) is None


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
        "acceptance_source_discovery": {"required": False, "status": "included"},
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


def test_normalized_equivalent_line_endings_are_not_the_same_capture(tmp_path):
    from tools.verifier_capture_obligation_manifest import record_capture_obligations

    context = tmp_path / "context.md"
    diff = tmp_path / "diff.patch"
    context.write_bytes(b"context\r\n")
    diff.write_bytes(b"diff\r\n")
    with pytest.raises(ValueError, match="loaded context changed"):
        record_capture_obligations(
            context, context_text="context\n", diff_path=diff, diff_text="diff\r\n"
        )
    with pytest.raises(ValueError, match="loaded diff changed"):
        record_capture_obligations(
            context, context_text="context\r\n", diff_path=diff, diff_text="diff\n"
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


def test_record_admits_truncated_changed_code_only_from_verified_full_patch(tmp_path) -> None:
    from tools.verifier_capture_obligation_manifest import record_capture_obligations

    coverage, raw_patch = _verified_truncated_patch_coverage()
    context = tmp_path / "verifier-context.md"
    context.write_text(_context_block(coverage), encoding="utf-8")
    diff = tmp_path / "verifier-pr-diff.patch"
    diff.write_bytes(raw_patch)
    manifest = record_capture_obligations(context, diff_path=diff)
    inventory = json.loads((tmp_path / "verifier-capture-byte-inventory.json").read_text())
    diff_item = next(item for item in inventory["inputs"] if item["input"] == "diff")
    assert manifest["sufficient"] is True
    assert manifest["gaps"] == []
    assert diff_item["bytes"] == len(raw_patch)
    assert diff_item["sha256"] == hashlib.sha256(raw_patch).hexdigest()


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


def test_recorded_contract_binds_all_obligations_gaps_and_raw_ranges(tmp_path):
    from tools.verifier_capture_obligation_manifest import record_capture_obligations

    coverage = _complete_coverage()
    coverage["acceptance_evidence_sources"] = [
        {
            "source": "original-proof",
            "status": "truncated",
            "included_chars": 7,
            "total_chars": None,
        },
        {"source": "artifacts", "status": "unavailable", "reason": "archive_entry_limit"},
    ]
    context = tmp_path / "context.md"
    raw = _context_block(coverage).replace("\n", "\r\n").encode() + b"x" * 70000
    context.write_bytes(raw)
    diff = tmp_path / "diff.patch"
    diff.write_bytes("diff proof \u03bb\r\n".encode())
    manifest = record_capture_obligations(context, diff_path=diff)
    contract_path = tmp_path / "verifier-capture-reassembly-contract.json"
    contract = json.loads(contract_path.read_text())
    inventory = json.loads((tmp_path / "verifier-capture-byte-inventory.json").read_text())
    expected_ranges = [r["id"] for item in inventory["inputs"] for r in item["ranges"]]
    assert contract["dependency_policy"] == "all-captured-inputs"
    assert contract["required_range_ids"] == expected_ranges
    assert contract["sufficient"] is False
    assert [entry["value"] for entry in contract["obligations"]] == manifest["obligations"]
    assert [entry["value"] for entry in contract["gaps"]] == manifest["gaps"]
    identities = [entry["id"] for field in ("obligations", "gaps") for entry in contract[field]]
    assert len(identities) == len(set(identities))
    record_capture_obligations(context, diff_path=diff)
    assert json.loads(contract_path.read_text()) == contract
    assert context.read_bytes() == raw
    assert diff.read_bytes() == "diff proof \u03bb\r\n".encode()


@pytest.mark.parametrize(
    "change", ["gap", "obligation", "range", "capture", "sufficient", "identity"]
)
def test_conflicting_reassembly_contract_is_never_rewritten(tmp_path, change):
    import hashlib

    from tools.verifier_capture_obligation_manifest import record_capture_obligations

    context = tmp_path / "context.md"
    context.write_text(_context_block(_complete_coverage()))
    snapshot = tmp_path / "verifier-input-manifest.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema": "workflows-verifier-input-snapshot/v1",
                "context_sha256": hashlib.sha256(context.read_bytes()).hexdigest(),
            }
        )
    )
    record_capture_obligations(context)
    payload = json.loads(snapshot.read_text())
    contract = payload["capture_reassembly_contract"]
    if change == "gap":
        contract["gaps"].append({"id": "invented", "value": "invented"})
    elif change == "obligation":
        contract["obligations"].pop()
    elif change == "range":
        contract["required_range_ids"].clear()
    elif change == "capture":
        contract["byte_inventory_sha256"] = "0" * 64
    elif change == "sufficient":
        contract["sufficient"] = 1  # JSON bool/int must remain distinct.
    else:
        contract["obligations"][0]["id"] = "stale"
    snapshot.write_text(json.dumps(payload))
    paths = [
        snapshot,
        context,
        tmp_path / "verifier-capture-reassembly-contract.json",
        tmp_path / "verifier-capture-byte-inventory.json",
        tmp_path / "verifier-capture-obligation-manifest.json",
    ]
    before = {path: path.read_bytes() for path in paths}
    with pytest.raises(ValueError, match="reassembly contract"):
        record_capture_obligations(context)
    assert {path: path.read_bytes() for path in paths} == before


def test_reassembly_identity_changes_for_any_capture_or_gap_revision():
    from tools.verifier_capture_obligation_manifest import (
        build_capture_byte_inventory,
        build_capture_reassembly_contract,
    )

    manifest = build_capture_obligation_manifest(_context_block(_complete_coverage()))
    inventory = build_capture_byte_inventory({"context": b"governing source", "diff": b"code"})
    original = build_capture_reassembly_contract(manifest, inventory)
    changed_inputs = build_capture_byte_inventory({"context": b"governing source", "diff": b"Code"})
    changed_manifest = copy.deepcopy(manifest)
    changed_manifest["gaps"].append("acceptance_evidence:original-proof:unavailable")
    changed_manifest["sufficient"] = False
    for candidate in (
        build_capture_reassembly_contract(manifest, changed_inputs),
        build_capture_reassembly_contract(changed_manifest, inventory),
    ):
        assert candidate["id"] != original["id"]
        assert {entry["id"] for entry in candidate["obligations"]}.isdisjoint(
            entry["id"] for entry in original["obligations"]
        )


@pytest.mark.parametrize(
    "discovery",
    [
        None,
        {},
        False,
        [],
        {"required": False},
        {"required": True},
        {"required": 0, "status": "included"},
        {"required": "false", "status": "included"},
        {"required": False, "status": "unavailable"},
        {"required": False, "status": "truncated"},
        {"required": False, "status": "future"},
    ],
)
def test_missing_or_invalid_discovery_cannot_establish_complete_capture(discovery):
    coverage = _complete_coverage()
    if discovery is None:
        del coverage["acceptance_source_discovery"]
    else:
        coverage["acceptance_source_discovery"] = discovery
    manifest = build_capture_obligation_manifest(_context_block(coverage))
    assert manifest["sufficient"] is False
    assert any("acceptance_source_discovery" in gap for gap in manifest["gaps"])


@pytest.mark.parametrize("required", [False, True])
def test_explicit_complete_discovery_retains_valid_capture(required):
    coverage = _complete_coverage()
    coverage["acceptance_source_discovery"] = {"required": required, "status": "included"}
    assert build_capture_obligation_manifest(_context_block(coverage))["sufficient"] is True
