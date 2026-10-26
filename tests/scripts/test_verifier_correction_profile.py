"""Offline source-view goldens. The downloaded authority fixture is never executed."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "correction_profile", ROOT / ".github/scripts/verifier_correction_profile.py"
)
assert SPEC and SPEC.loader
READER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READER)
SOURCE = (ROOT / "tests/fixtures/verifier_correction/core-role-authority.txt").read_text()


def record():
    identity = dict(
        zip(
            READER.IDENTITY_TEXT,
            (
                "synthetic-ordinary",
                "claude",
                "anthropic",
                "fixture-model",
                "high",
                "read-only",
                "fixture-adapter",
                "fixture-prompt",
                "active",
            ),
            strict=True,
        )
    )
    identity.update(
        transport_support=["offload"],
        capacity_pool_ids=["fixture-pool"],
        requires_explicit_selection=False,
    )
    return {
        "schema": READER.SCHEMA,
        "qualification_id": "fixture-qualified",
        "status": "qualified",
        "role": "bounded_classification",
        "profile_identity": identity,
        "profile_identity_sha256": hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest(),
        "transport": "offload",
        "qualified_at": 10,
        "expires_at": 100,
        "evidence_refs": [{"reference": "inert:offline-evidence", "sha256": "e" * 64}],
        "confinement": {
            "data_only": True,
            "tools": False,
            "mcp": False,
            "hooks": False,
            "project_context": False,
            "adapter_build_sha256": "a" * 64,
        },
    }


def source(records):
    tree = ast.parse(SOURCE)
    node = next(
        n
        for n in tree.body
        if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name)
        and n.target.id == "ROLE_QUALIFICATIONS"
    )
    lines = SOURCE.splitlines(keepends=True)
    lines[node.lineno - 1 : node.end_lineno] = [
        f"ROLE_QUALIFICATIONS: dict[str, dict[str, Any]] = {records!r}\n"
    ]
    return "".join(lines)


def view(records, now=50):
    return READER.read_qualification(source(records), "synthetic-ordinary", now)


def test_reviewed_empty_registry_remains_unknown():
    result = READER.read_qualification(SOURCE, "synthetic-ordinary", 50)
    assert result["status"] == "owned_unknown"
    assert "missing or ambiguous" in result["reason"]


def test_literal_record_matches_bounded_role_and_preserves_runtime_limit():
    row = record()
    result = view({row["qualification_id"]: row})
    assert result["status"] == "qualified"
    assert result["record_role"] == "bounded_classification"
    assert result["runtime_execution"] == "not_attested"
    assert result["record"] == row


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(status="revoked"),
        lambda r: r.update(role="strong_criterion_adjudication", named_criterion_only=True),
        lambda r: r.update(qualification_id="different"),
        lambda r: r.update(profile_identity_sha256="b" * 64),
        lambda r: r.update(transport="local"),
        lambda r: r.update(expires_at=50),
        lambda r: r.update(qualified_at=51),
        lambda r: r.update(qualified_at=True),
        lambda r: r.update(evidence_refs=[]),
        lambda r: r["confinement"].update(tools=True),
        lambda r: r["confinement"].pop("hooks"),
        lambda r: r["confinement"].update(adapter_build_sha256="missing"),
        lambda r: r["profile_identity"].update(agent="AIDER"),
        lambda r: r["profile_identity"].update(lifecycle_status="retired"),
        lambda r: r["profile_identity"].update(prompt_version="changed"),
        lambda r: r["profile_identity"].update(transport_support=["local"]),
        lambda r: r["profile_identity"].update(capacity_pool_ids=["dup", "dup"]),
        lambda r: r["profile_identity"].update(requires_explicit_selection=1),
    ],
)
def test_invalid_or_substituted_role_records_never_qualify(mutate):
    row = record()
    mutate(row)
    assert view({"fixture-qualified": row})["status"] == "owned_unknown"


def test_ambiguous_and_malformed_records_are_unknown():
    row = record()
    duplicate = copy.deepcopy(row)
    duplicate["qualification_id"] = "second"
    assert view({"fixture-qualified": row, "second": duplicate})["status"] == "owned_unknown"
    assert view({"fixture-qualified": row, "broken": None})["status"] == "owned_unknown"


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace(
            "ROLE_QUALIFICATIONS: dict[str, dict[str, Any]] = {}", "ROLE_QUALIFICATIONS = dict()"
        ),
        lambda s: s + "\nROLE_QUALIFICATIONS = {}\n",
        lambda s: s.replace('profile["agent"].casefold() == "aider"', "False"),
        lambda s: s + '\nraise RuntimeError("never execute this source")\n',
    ],
)
def test_dynamic_ambiguous_or_changed_reader_source_is_not_executed(change):
    assert (
        READER.read_qualification(change(SOURCE), "synthetic-ordinary", 50)["status"]
        == "owned_unknown"
    )


def test_nonascii_identity_uses_existing_python_reader_digest():
    row = record()
    row["profile_identity"]["prompt_version"] = "fixture-\u00e9"
    row["profile_identity_sha256"] = hashlib.sha256(
        json.dumps(row["profile_identity"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert view({"fixture-qualified": row})["status"] == "qualified"


@pytest.mark.parametrize("now", [-1, True, float("inf"), float("nan"), None])
def test_unknown_observation_time_never_grants_role(now):
    assert view({"fixture-qualified": record()}, now)["status"] == "owned_unknown"


def test_duplicate_literal_keys_cannot_hide_record_revocation():
    row = record()
    text = source({"fixture-qualified": row}).replace(
        "'status': 'qualified'", "'status': 'revoked', 'status': 'qualified'"
    )
    result = READER.read_qualification(text, "synthetic-ordinary", 50)
    assert result["status"] == "owned_unknown"
    assert "duplicate" in result["reason"]


def test_shared_role_reader_goldens():
    fixture = json.loads(
        (ROOT / "tests/fixtures/verifier_correction/role-reader-goldens.json").read_text()
    )
    assert fixture["reader_semantics_sha256"] == READER.READER_SHA256
    for case in fixture["cases"]:
        result = READER.read_qualification(
            source(case["records"]), case["profile"]["profile_id"], case["now"]
        )
        assert (result["status"] == "qualified") == case["qualified"], case["id"]
