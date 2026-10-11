"""Tests for capture obligation manifest derivation."""

from __future__ import annotations

import json

from tools.verifier_capture_obligation_manifest import (
    SCHEMA,
    build_capture_obligation_manifest,
    parse_context_source_coverage,
)


def _context_block(coverage: dict) -> str:
    return "## Context source coverage\n\n```json\n" + json.dumps(coverage) + "\n```\n\n## CI Information\n"


def test_parse_context_source_coverage_extracts_json_block() -> None:
    coverage = {"schema": "verifier-context-source-coverage/v1", "changed_code_sources": []}
    text = _context_block(coverage)
    assert parse_context_source_coverage(text) == coverage


def test_manifest_marks_truncated_changed_code_insufficient() -> None:
    coverage = {
        "schema": "verifier-context-source-coverage/v1",
        "changed_code_sources": [
            {
                "source": "src/a.py",
                "status": "truncated",
                "included_chars": 10,
                "total_chars": 100,
            }
        ],
        "acceptance_evidence_sources": [],
        "full_diff_artifact": {"source": "verifier-pr-diff.patch", "chars": 100, "status": "included"},
    }
    manifest = build_capture_obligation_manifest(_context_block(coverage))
    assert manifest["schema"] == SCHEMA
    assert manifest["sufficient"] is False
    assert "changed_code:src/a.py:truncated" in manifest["gaps"]


def test_manifest_passes_when_all_required_sources_included() -> None:
    coverage = {
        "schema": "verifier-context-source-coverage/v1",
        "acceptance_source_discovery": {"required": True, "status": "included"},
        "changed_code_sources": [
            {"source": "src/a.py", "status": "included", "included_chars": 100, "total_chars": 100}
        ],
        "acceptance_evidence_sources": [
            {"source": "comments", "status": "included", "included_chars": 50, "total_chars": 50}
        ],
        "full_diff_artifact": {"source": "verifier-pr-diff.patch", "chars": 100, "status": "included"},
    }
    manifest = build_capture_obligation_manifest(_context_block(coverage))
    assert manifest["sufficient"] is True
    assert manifest["gaps"] == []
