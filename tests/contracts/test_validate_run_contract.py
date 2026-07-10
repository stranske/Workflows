"""P0.2/P0.3 acceptance: validate_run_contract.py behavior over fixtures.

Asserts the valid fixtures pass, each invalid fixture fails, the opt-in skip
(absent / candidate participant) returns success, and the consumer role
validates only its ingested schema. Fails today against an empty tree.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_DIR = ROOT / "docs" / "contracts" / "schemas"
FIXTURES = ROOT / "tests" / "fixtures" / "backplane"
REGISTRY = ROOT / "config" / "backplane_participants.json"
VALIDATOR = ROOT / "scripts" / "validate_run_contract.py"

PRODUCER_REPO = "stranske/Pension-Data"


def _import_validator():
    name = "validate_run_contract"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, VALIDATOR)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass annotation resolution can find the module
    # via cls.__module__ (otherwise sys.modules.get(...) is None at decoration).
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _registry() -> dict:
    return json.loads(REGISTRY.read_text())


def _validate(name: str, *, repo: str = PRODUCER_REPO, manifest: str | None = None):
    mod = _import_validator()
    envelope = json.loads((FIXTURES / name).read_text())
    manifest_obj = json.loads((FIXTURES / manifest).read_text()) if manifest else None
    return mod.validate_envelope(
        envelope=envelope,
        schema_dir=SCHEMA_DIR,
        registry=_registry(),
        repo=repo,
        manifest=manifest_obj,
    )


def test_valid_run_with_manifest_conforms() -> None:
    report = _validate("valid_run.json", manifest="valid_manifest.json")
    assert report.conformant, [v.message for v in report.violations]
    assert not report.skipped
    assert report.role == "producer"


@pytest.mark.parametrize(
    "name,manifest",
    [
        ("missing_cost.json", None),
        ("unsafe_rows_inline.json", None),
        ("artifact_not_in_manifest.json", "valid_manifest.json"),
        ("bad_identity_ref.json", None),
    ],
)
def test_invalid_fixtures_fail(name: str, manifest: str | None) -> None:
    report = _validate(name, manifest=manifest)
    assert not report.conformant, f"{name} unexpectedly passed"
    assert not report.skipped


def test_absent_repo_is_optin_skip() -> None:
    # A repo with no registry entry is a no-op success (opt-in respected).
    report = _validate("valid_run.json", repo="stranske/not-a-participant")
    assert report.skipped
    assert report.conformant


def test_candidate_status_repo_is_skipped() -> None:
    # learning-management-system is a candidate consumer -> gate is a no-op.
    report = _validate("valid_run.json", repo="stranske/learning-management-system")
    assert report.skipped
    assert report.conformant


def test_cli_exit_codes(tmp_path, capsys) -> None:
    mod = _import_validator()
    # Valid -> exit 0.
    rc = mod.main(
        [
            str(FIXTURES / "valid_run.json"),
            "--manifest",
            str(FIXTURES / "valid_manifest.json"),
            "--registry",
            str(REGISTRY),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--repo",
            PRODUCER_REPO,
        ]
    )
    assert rc == 0
    # Invalid (missing required cost) -> exit 1 under strict.
    rc = mod.main(
        [
            str(FIXTURES / "missing_cost.json"),
            "--registry",
            str(REGISTRY),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--repo",
            PRODUCER_REPO,
        ]
    )
    assert rc == 1
    # Same invalid envelope under --warn-only -> exit 0.
    rc = mod.main(
        [
            str(FIXTURES / "missing_cost.json"),
            "--registry",
            str(REGISTRY),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--repo",
            PRODUCER_REPO,
            "--warn-only",
        ]
    )
    assert rc == 0

    # Bad/missing manifests are load errors, not traceback crashes.
    missing_manifest = tmp_path / "missing-manifest.json"
    rc = mod.main(
        [
            str(FIXTURES / "valid_run.json"),
            "--manifest",
            str(missing_manifest),
            "--registry",
            str(REGISTRY),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--repo",
            PRODUCER_REPO,
        ]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert f"ERROR: cannot load artifact manifest {missing_manifest}:" in captured.err

    bad_manifest = tmp_path / "bad-manifest.json"
    bad_manifest.write_text("{not json", encoding="utf-8")
    rc = mod.main(
        [
            str(FIXTURES / "valid_run.json"),
            "--manifest",
            str(bad_manifest),
            "--registry",
            str(REGISTRY),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--repo",
            PRODUCER_REPO,
        ]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert f"ERROR: cannot load artifact manifest {bad_manifest}:" in captured.err


def test_missing_envelope_skips_for_candidate_and_planned_and_absent(tmp_path) -> None:
    # A missing run.json must be an opt-in SKIP (exit 0) for a candidate
    # consumer (LMS), a not-yet-emitting "planned" producer (Trend), and
    # an absent repo -- the caller's emit-reference-run job legitimately
    # produces nothing until an emitter is wired. Regression guard for the
    # "cannot load run envelope -> exit 2" crash that gated every PR.
    mod = _import_validator()
    missing = tmp_path / "does-not-exist" / "run.json"
    for repo in (
        "stranske/learning-management-system",  # candidate consumer
        "stranske/Trend_Model_Project",  # planned producer
        "stranske/not-a-participant",  # absent
    ):
        rc = mod.main(
            [
                str(missing),
                "--registry",
                str(REGISTRY),
                "--schema-dir",
                str(SCHEMA_DIR),
                "--repo",
                repo,
            ]
        )
        assert rc == 0, f"missing envelope should skip (exit 0) for {repo}, got {rc}"


def test_missing_envelope_decision_by_status() -> None:
    # The pure helper: any active participant fails on a missing envelope;
    # everyone else (planned/candidate/none/absent) skips.
    mod = _import_validator()
    run_json = Path("artifacts/reference/run.json")

    def reg(role: str, status: str) -> dict:
        return {"participants": [{"repo": "stranske/X", "role": role, "status": status}]}

    # Actively emitting -> a vanished envelope/input is a real regression -> fail.
    for role, status in (
        ("producer", "emitting"),
        ("producer", "conformant"),
        ("bridge", "emitting"),
        ("consumer", "conformant"),
    ):
        report = mod.missing_envelope_report(reg(role, status), "stranske/X", run_json)
        assert not report.skipped and not report.conformant, (role, status)
        assert f"role='{role}'" in report.violations[0].message

    # Not-yet-emitting / opt-out -> skip.
    for role, status in (
        ("producer", "planned"),
        ("consumer", "candidate"),
        ("producer", "none"),
        ("bridge", "planned"),
    ):
        report = mod.missing_envelope_report(reg(role, status), "stranske/X", run_json)
        assert report.skipped and report.conformant, (role, status)

    # Absent repo -> skip.
    report = mod.missing_envelope_report({"participants": []}, "stranske/Y", run_json)
    assert report.skipped and report.conformant


def test_consumer_convention_only_ingest_passes_without_schema_validation() -> None:
    """Convention-only ingests declare a surface but skip JSON Schema validation."""
    mod = _import_validator()
    document = {"note": "not a run envelope or evidence object"}
    registry = {
        "participants": [
            {
                "repo": "stranske/Identity-Consumer",
                "role": "consumer",
                "status": "conformant",
                "ingests": ["identity-map-conventions"],
            }
        ]
    }

    report = mod.validate_envelope(
        envelope=document,
        schema_dir=SCHEMA_DIR,
        registry=registry,
        repo="stranske/Identity-Consumer",
        manifest=None,
    )

    assert report.conformant
    assert not report.violations
    assert report.role == "consumer"


def test_consumer_reports_closest_schema_errors_when_no_ingest_matches() -> None:
    """When none of several declared schemas match, surface the fewest-error schema."""
    mod = _import_validator()
    document = {
        "schema_version": "evidence-object/v1",
        "evidence_id": "ev-1",
        "fact_ref": "metric.alpha",
        "source_id": "source-1",
        "method": "not-a-valid-method",
    }
    registry = {
        "participants": [
            {
                "repo": "stranske/Consumer",
                "role": "consumer",
                "status": "conformant",
                "ingests": ["evidence-object/v1", "artifact-manifest/v1"],
            }
        ]
    }

    report = mod.validate_envelope(
        envelope=document,
        schema_dir=SCHEMA_DIR,
        registry=registry,
        repo="stranske/Consumer",
        manifest=None,
    )

    assert not report.conformant
    assert len(report.violations) == 1
    assert report.violations[0].message.startswith("ingested-as-evidence-object/v1:")
    assert "not-a-valid-method" in report.violations[0].message


def test_unsafe_raw_payload_fields_rejected_via_cli(tmp_path, capsys) -> None:
    """Acceptance: CLI main path rejects unsafe raw payload fields in strict mode (exit 1) and warns in warn-only mode (exit 0)."""
    mod = _import_validator()

    # Create a temporary run envelope with an unsafe raw payload field (prompt)
    unsafe_envelope = {
        "schema_version": "run-contract/v1",
        "repo": "stranske/Pension-Data",
        "tool": "test-tool",
        "run_id": "sha256:test123",
        "status": "success",
        "actor": {"kind": "ci", "id": "test", "intent": "test"},
        "inputs": {"prompt": "sensitive data that should not be inlined"},
        "outputs": {"manifest_ref": "artifact:manifest.json", "summary": {}, "artifact_ids": []},
        "provenance": {"tool_version": "0.1.0"},
        "cost": {"usd": None, "input_tokens": 0, "output_tokens": 0},
        "latency": {"wall_ms": 12.0},
        "warnings": [],
        "data_quality": {"overall_status": "ok"},
        "evidence_refs": [],
        "identity_refs": [],
    }

    run_json = tmp_path / "unsafe_run.json"
    run_json.write_text(json.dumps(unsafe_envelope))

    # Test strict mode: should exit 1 and report unsafe field
    rc = mod.main(
        [
            str(run_json),
            "--registry",
            str(REGISTRY),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--repo",
            PRODUCER_REPO,
        ]
    )
    assert rc == 1, f"Expected exit 1 in strict mode, got {rc}"
    captured = capsys.readouterr()
    assert "unsafe raw payload field 'prompt' inlined" in captured.err
    # Report only the unsafe field name; raw prompt content must not leak.
    assert "sensitive data that should not be inlined" not in captured.err

    # Test warn-only mode: same unsafe envelope should exit 0
    rc = mod.main(
        [
            str(run_json),
            "--registry",
            str(REGISTRY),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--repo",
            PRODUCER_REPO,
            "--warn-only",
        ]
    )
    assert rc == 0, f"Expected exit 0 in warn-only mode, got {rc}"
    captured = capsys.readouterr()
    assert "unsafe raw payload field 'prompt' inlined" in captured.err
    # Report only the unsafe field name; raw prompt content must not leak.
    assert "sensitive data that should not be inlined" not in captured.err


def test_unsafe_raw_payload_validation_direct() -> None:
    """Acceptance: validate_envelope rejects multiple unsafe raw payload fields and identifies them by name only."""
    mod = _import_validator()

    # Test envelope with multiple unsafe fields
    unsafe_envelope = {
        "schema_version": "run-contract/v1",
        "repo": "stranske/Pension-Data",
        "tool": "test-tool",
        "run_id": "sha256:test456",
        "status": "success",
        "actor": {"kind": "ci", "id": "test", "intent": "test"},
        "inputs": {"prompt": "sensitive prompt data"},
        "outputs": {
            "manifest_ref": "artifact:manifest.json",
            "summary": {"model_output": "sensitive model output"},
            "artifact_ids": [],
        },
        "provenance": {"tool_version": "0.1.0"},
        "cost": {"usd": None, "input_tokens": 0, "output_tokens": 0},
        "latency": {"wall_ms": 12.0},
        "warnings": [],
        "data_quality": {"overall_status": "ok"},
        "evidence_refs": [],
        "identity_refs": [],
    }

    report = mod.validate_envelope(
        envelope=unsafe_envelope,
        schema_dir=SCHEMA_DIR,
        registry=_registry(),
        repo=PRODUCER_REPO,
        manifest=None,
    )

    assert not report.conformant
    assert not report.skipped

    # Check that both unsafe fields are identified by name
    violation_messages = [v.message for v in report.violations]
    assert any("unsafe raw payload field 'prompt' inlined" in msg for msg in violation_messages)
    assert any(
        "unsafe raw payload field 'model_output' inlined" in msg for msg in violation_messages
    )

    # Ensure raw payload content is not echoed in any violation message
    for msg in violation_messages:
        assert "sensitive prompt data" not in msg
        assert "sensitive model output" not in msg


def test_consumer_mixed_unknown_ingest_token_fails() -> None:
    """Unknown ingest tokens are invalid even when another declared token matches."""
    mod = _import_validator()
    evidence = {
        "schema_version": "evidence-object/v1",
        "evidence_id": "ev-1",
        "fact_ref": "metric.alpha",
        "source_id": "source-1",
        "method": "computed",
    }
    registry = {
        "participants": [
            {
                "repo": "stranske/Consumer",
                "role": "consumer",
                "status": "conformant",
                "ingests": ["evidence-object/v1", "typo-object/v1"],
            }
        ]
    }

    report = mod.validate_envelope(
        envelope=evidence,
        schema_dir=SCHEMA_DIR,
        registry=registry,
        repo="stranske/Consumer",
        manifest=None,
    )

    assert not report.conformant
    assert any(
        v.message == "unknown ingest schema token 'typo-object/v1'" for v in report.violations
    )


def test_find_participant_helper() -> None:
    """Test _find_participant helper independently."""
    mod = _import_validator()
    registry = _registry()

    # Existing participant
    entry = mod._find_participant(registry, "stranske/Pension-Data")
    assert entry is not None
    assert entry["repo"] == "stranske/Pension-Data"
    assert entry["role"] == "producer"

    # Absent participant
    entry = mod._find_participant(registry, "stranske/not-a-participant")
    assert entry is None


def test_is_missing_envelope_a_failure_helper() -> None:
    """Test _is_missing_envelope_a_failure helper independently."""
    mod = _import_validator()

    # Emitting producer -> should fail
    entry = {"repo": "stranske/X", "role": "producer", "status": "emitting"}
    assert mod._is_missing_envelope_a_failure(entry) is True

    # Conformant producer -> should fail
    entry = {"repo": "stranske/X", "role": "producer", "status": "conformant"}
    assert mod._is_missing_envelope_a_failure(entry) is True

    # Emitting bridge -> should fail
    entry = {"repo": "stranske/X", "role": "bridge", "status": "emitting"}
    assert mod._is_missing_envelope_a_failure(entry) is True

    # Conformant consumer -> should fail
    entry = {"repo": "stranske/X", "role": "consumer", "status": "conformant"}
    assert mod._is_missing_envelope_a_failure(entry) is True

    # Planned producer -> should skip (not fail)
    entry = {"repo": "stranske/X", "role": "producer", "status": "planned"}
    assert mod._is_missing_envelope_a_failure(entry) is False

    # Candidate consumer -> should skip
    entry = {"repo": "stranske/X", "role": "consumer", "status": "candidate"}
    assert mod._is_missing_envelope_a_failure(entry) is False

    # None status -> should skip
    entry = {"repo": "stranske/X", "role": "producer", "status": "none"}
    assert mod._is_missing_envelope_a_failure(entry) is False

    # Planned bridge -> should skip
    entry = {"repo": "stranske/X", "role": "bridge", "status": "planned"}
    assert mod._is_missing_envelope_a_failure(entry) is False

    # Absent participant (None) -> should skip
    assert mod._is_missing_envelope_a_failure(None) is False


def test_registry_shape_meta() -> None:
    reg = _registry()
    investment_repos = {
        "stranske/Pension-Data",
        "stranske/Trend_Model_Project",
        "stranske/Counter_Risk",
        "stranske/Portable-Alpha-Extension-Model",
        "stranske/Manager-Database",
        "stranske/Inv-Man-Intake",
    }
    producers = [p for p in reg["participants"] if p.get("role") == "producer"]
    assert {p["repo"] for p in producers} == investment_repos
    for p in reg["participants"]:
        assert p["contract_version"] == "run-contract/v1"
        assert p["role"] in {"producer", "consumer", "bridge"}
        assert p["status"] in {"planned", "emitting", "conformant", "candidate", "none"}
    # LMS appears as a candidate consumer AND in the producer exclusion list.
    lms = [p for p in reg["participants"] if p["repo"] == "stranske/learning-management-system"]
    assert len(lms) == 1
    assert lms[0]["role"] == "consumer"
    assert lms[0]["status"] == "candidate"
    excluded = {e["repo"]: e for e in reg["excluded"]}
    for repo in (
        "stranske/trip-planner",
        "stranske/Travel-Plan-Permission",
        "stranske/learning-management-system",
        "stranske/Workflows",
    ):
        assert repo in excluded
        assert excluded[repo]["reason"].strip()
