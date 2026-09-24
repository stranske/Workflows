"""P0.2/P0.3 acceptance: validate_run_contract.py behavior over fixtures.

Asserts the valid fixtures pass, each invalid fixture fails, the opt-in skip
(absent / candidate participant) returns success, and the consumer role
validates only its ingested schema. Fails today against an empty tree.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

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


def test_cli_enforces_opt_in_manifest_evidence_closure(tmp_path: Path, capsys) -> None:
    """The CLI supplies run_json context required by the evidence-file policy."""
    mod = _import_validator()
    evidence = {
        "schema_version": "evidence-object/v1",
        "evidence_id": "ev-cli",
        "fact_ref": "metric.alpha",
        "source_id": "source-1",
        "method": "computed",
        "excerpt": "Computed from source-1.",
    }
    evidence_path = tmp_path / "evidence-cli.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    envelope = json.loads((FIXTURES / "valid_run.json").read_text())
    envelope["repo"] = "stranske/Cli-Evidence"
    envelope["evidence_refs"] = ["ev-cli", "ev-dangling"]
    run_json = tmp_path / "run.json"
    run_json.write_text(json.dumps(envelope), encoding="utf-8")
    manifest = {
        "schema_version": "artifact-manifest/v1",
        "run_id": envelope["run_id"],
        "tool": envelope["tool"],
        "artifacts": [
            {
                "artifact_id": "evidence-cli",
                "name": "evidence-cli.json",
                "kind": "evidence",
                "path": "evidence-cli.json",
                "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "participants": [
                    {
                        "repo": envelope["repo"],
                        "role": "producer",
                        "status": "emitting",
                        "emitted_evidence_policy": "manifest-evidence-closure/v1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert (
        mod.main(
            [
                str(run_json),
                "--manifest",
                str(manifest_path),
                "--registry",
                str(registry_path),
                "--schema-dir",
                str(SCHEMA_DIR),
                "--repo",
                envelope["repo"],
            ]
        )
        == 1
    )
    err = capsys.readouterr().err
    assert "ev-dangling' has no emitted evidence artifact" in err
    assert "ev-cli' has no emitted evidence artifact" not in err


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


@pytest.mark.parametrize(
    "fixture,expected",
    [("valid_tracked_variable.json", 0), ("invalid_tracked_variable_missing_evidence.json", 1)],
)
def test_tracked_variable_cli_needs_no_participant_context(fixture, expected, capsys) -> None:
    mod = _import_validator()
    assert (
        mod.main(["--tracked-variables", str(FIXTURES / fixture), "--schema-dir", str(SCHEMA_DIR)])
        == expected
    )
    output = capsys.readouterr()
    if expected:
        assert "evidence" in output.err
    else:
        assert "1 file(s) conform" in output.out


@pytest.mark.parametrize(
    "fixture,expected",
    [
        ("valid_document_mirror.json", 0),
        ("valid_empty_document_mirror.json", 0),
        ("invalid_document_mirror_bad_blob_path.json", 1),
        ("invalid_document_mirror_bad_urls.json", 1),
    ],
)
@pytest.mark.parametrize("schema_args", [[], ["--schema-dir", str(SCHEMA_DIR)]])
def test_mirror_manifest_cli_needs_no_participant_context(
    fixture, expected, capsys, schema_args
) -> None:
    mod = _import_validator()
    assert mod.main(["--mirror-manifest", str(FIXTURES / fixture), *schema_args]) == expected
    output = capsys.readouterr()
    if expected:
        assert output.err
    else:
        assert "1 file(s) conform" in output.out


def test_mirror_manifest_cli_reports_missing_and_invalid_json(tmp_path, capsys) -> None:
    mod = _import_validator()
    missing = tmp_path / "missing-mirror.json"
    assert mod.main(["--mirror-manifest", str(missing), "--schema-dir", str(SCHEMA_DIR)]) == 1
    assert f"cannot load mirror manifest {missing}" in capsys.readouterr().err

    bad_json = tmp_path / "bad-mirror.json"
    bad_json.write_text("{not json", encoding="utf-8")
    assert mod.main(["--mirror-manifest", str(bad_json), "--schema-dir", str(SCHEMA_DIR)]) == 1
    assert f"cannot load mirror manifest {bad_json}" in capsys.readouterr().err


def test_mirror_manifest_cli_reports_invalid_utf8(tmp_path, capsys) -> None:
    mod = _import_validator()
    path = tmp_path / "invalid-utf8.json"
    path.write_bytes(b"\xff")
    assert mod.main(["--mirror-manifest", str(path), "--schema-dir", str(SCHEMA_DIR)]) == 1
    assert f"cannot load mirror manifest {path}" in capsys.readouterr().err


def test_mirror_manifest_schema_violations_identify_each_input_file() -> None:
    mod = _import_validator()
    paths = [
        FIXTURES / "invalid_document_mirror_bad_blob_path.json",
        FIXTURES / "invalid_document_mirror_bad_urls.json",
    ]
    report = mod.validate_mirror_manifests(paths=paths, schema_dir=SCHEMA_DIR)
    assert not report.conformant
    assert all(
        any(violation.path.startswith(f"{path}:/") for violation in report.violations)
        for path in paths
    )


def test_tracked_variables_and_mirror_manifest_are_mutually_exclusive(capsys) -> None:
    mod = _import_validator()
    with pytest.raises(SystemExit) as exc:
        mod.main(
            [
                "--tracked-variables",
                str(FIXTURES / "valid_tracked_variable.json"),
                "--mirror-manifest",
                str(FIXTURES / "valid_document_mirror.json"),
                "--schema-dir",
                str(SCHEMA_DIR),
            ]
        )
    assert exc.value.code == 2
    assert "mutually exclusive" in capsys.readouterr().err


def test_self_smoke_and_mirror_manifest_are_mutually_exclusive(capsys) -> None:
    mod = _import_validator()
    with pytest.raises(SystemExit) as exc:
        mod.main(
            [
                "--self-smoke",
                "--mirror-manifest",
                str(FIXTURES / "invalid_document_mirror_bad_urls.json"),
                "--registry",
                str(REGISTRY),
                "--repo",
                PRODUCER_REPO,
                "--schema-dir",
                str(SCHEMA_DIR),
            ]
        )
    assert exc.value.code == 2
    assert "mutually exclusive" in capsys.readouterr().err


def test_self_smoke_and_tracked_variables_are_mutually_exclusive(capsys) -> None:
    mod = _import_validator()
    with pytest.raises(SystemExit) as exc:
        mod.main(
            [
                "--self-smoke",
                "--tracked-variables",
                str(FIXTURES / "valid_tracked_variable.json"),
                "--schema-dir",
                str(SCHEMA_DIR),
            ]
        )
    assert exc.value.code == 2
    assert "mutually exclusive" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("schema_name", "missing_format"),
    [
        ("mosaic-core-v1.schema.json", "date-time"),
        ("document-mirror-v1.schema.json", "uri"),
    ],
)
def test_required_format_checker_fails_closed_when_provider_is_unavailable(
    monkeypatch, schema_name: str, missing_format: str
) -> None:
    mod = _import_validator()
    checkers = dict(mod.FormatChecker.checkers)
    checkers.pop(missing_format)
    monkeypatch.setattr(mod.FormatChecker, "checkers", checkers)
    with pytest.raises(
        RuntimeError, match="install jsonschema rfc3339-validator rfc3986-validator"
    ):
        mod._validator_for_schema(SCHEMA_DIR, schema_name)


@pytest.mark.parametrize("format_name", ["date-time", "uri"])
def test_required_format_checker_rejects_registered_but_ineffective_provider(
    monkeypatch, format_name: str
) -> None:
    mod = _import_validator()
    checkers = dict(mod.FormatChecker.checkers)
    checkers[format_name] = (lambda value: True, ())
    monkeypatch.setattr(mod.FormatChecker, "checkers", checkers)
    with pytest.raises(RuntimeError, match=f"format checker.*ineffective: {format_name}"):
        mod._required_format_checker(format_name)


@pytest.mark.parametrize(
    ("schema_name", "missing_format", "blocked_imports"),
    [
        ("mosaic-core-v1.schema.json", "date-time", ("rfc3339_validator",)),
        (
            "document-mirror-v1.schema.json",
            "uri",
            ("rfc3986_validator", "rfc3987"),
        ),
    ],
)
def test_required_format_checker_fails_closed_without_optional_provider_import(
    schema_name: str, missing_format: str, blocked_imports: tuple[str, ...]
) -> None:
    """Exercise jsonschema registration in a fresh process without the provider."""
    code = f"""
import builtins
from pathlib import Path
real_import = builtins.__import__
blocked = {blocked_imports!r}
def without_provider(name, *args, **kwargs):
    if name in blocked:
        raise ImportError(name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = without_provider
from scripts.validate_run_contract import _validator_for_schema
try:
    _validator_for_schema(Path('docs/contracts/schemas'), {schema_name!r})
except RuntimeError as exc:
    assert {missing_format!r} in str(exc), str(exc)
else:
    raise AssertionError('missing format provider did not fail closed')
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("mode", [[str(FIXTURES / "valid_run.json")], ["--self-smoke"]])
@pytest.mark.parametrize("missing", ["--registry", "--repo"])
def test_run_contract_modes_still_require_participant_context(mode, missing, capsys) -> None:
    mod = _import_validator()
    args = [*mode, "--schema-dir", str(SCHEMA_DIR)]
    if missing != "--registry":
        args += ["--registry", str(REGISTRY)]
    if missing != "--repo":
        args += ["--repo", PRODUCER_REPO]
    with pytest.raises(SystemExit) as exc:
        mod.main(args)
    assert exc.value.code == 2
    assert missing in capsys.readouterr().err


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
        "excerpt": "The metric record has an invalid validation method.",
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


def test_self_smoke_loads_every_bundled_schema(capsys) -> None:
    """Self-smoke must discover schemas, not name a hardcoded subset.

    A hardcoded triple silently skipped tracked-variable-v1 and
    capability-bundle-v1, so a malformed schema added to the directory would
    have passed the gate.
    """
    mod = _import_validator()
    rc = mod._self_smoke(SCHEMA_DIR, REGISTRY)
    assert rc == 0
    out = capsys.readouterr().out
    on_disk = sorted(path.name for path in SCHEMA_DIR.glob("*.schema.json"))
    assert on_disk, "no schemas on disk; fixture assumption broken"
    for name in on_disk:
        assert f"PASS schema loads + valid Draft202012: {name}" in out, name


def test_self_smoke_fails_on_an_empty_schema_dir(tmp_path, capsys) -> None:
    """An empty schema dir must fail loudly, not report a vacuous pass."""
    mod = _import_validator()
    empty = tmp_path / "schemas"
    empty.mkdir()
    rc = mod._self_smoke(empty, REGISTRY)
    assert rc == 1
    assert "no *.schema.json files found" in capsys.readouterr().out


def test_self_smoke_fails_when_a_registered_schema_is_missing(tmp_path, capsys) -> None:
    mod = _import_validator()
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "run-contract-v1.schema.json").write_text(
        (SCHEMA_DIR / "run-contract-v1.schema.json").read_text()
    )
    assert mod._self_smoke(schema_dir, REGISTRY) == 1
    assert "missing registered schemas" in capsys.readouterr().out


def test_self_smoke_rejects_draft2020_invalid_schema_in_schema_dir(tmp_path) -> None:
    """JSON-valid but Draft-2020-12-invalid schemas must fail via glob discovery."""
    mod = _import_validator()
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    for src in SCHEMA_DIR.glob("*.schema.json"):
        (schema_dir / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    bad_name = "zzz-invalid-meta.schema.json"
    bad_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "integer",
        "exclusiveMinimum": "not-a-number",
    }
    (schema_dir / bad_name).write_text(json.dumps(bad_schema), encoding="utf-8")
    discovered = sorted(path.name for path in schema_dir.glob("*.schema.json"))
    assert bad_name in discovered

    with pytest.raises(SchemaError):
        Draft202012Validator.check_schema(bad_schema)

    with pytest.raises(SchemaError):
        mod._self_smoke(schema_dir, REGISTRY)


def _valid_capability_bundle(**overrides):
    bundle = {
        "schema_version": "capability-bundle/v1",
        "capability_id": "keepalive/test-bundle",
        "version": "1.0.0",
        "content_hash": "sha256:" + ("a" * 64),
        "selector": {"repo": "stranske/Workflows", "agent": "codex"},
        "owner": "stranske/Workflows",
        "fragments": {
            "task": "Exercise the declared gate before claiming parity.",
            "acceptance": "Report the gate ID and the offline assertion.",
        },
        "gates": ["frontend_verify@1"],
        "rollback": "Remove the bundle from the registry and rerun keepalive.",
        **overrides,
    }
    return bundle


def test_capability_bundle_is_a_schema_validated_ingest_token() -> None:
    """capability-bundle/v1 has a schema on disk and is enforced for consumers."""
    mod = _import_validator()
    assert mod.INGEST_SCHEMA_FILES["capability-bundle/v1"] == "capability-bundle-v1.schema.json"
    assert (SCHEMA_DIR / "capability-bundle-v1.schema.json").is_file()
    for token, filename in mod.INGEST_SCHEMA_FILES.items():
        assert (SCHEMA_DIR / filename).is_file(), token

    registry = {
        "participants": [
            {
                "repo": "stranske/Capability-Consumer",
                "role": "consumer",
                "status": "conformant",
                "ingests": ["capability-bundle/v1"],
            }
        ]
    }
    report = mod.validate_envelope(
        envelope=_valid_capability_bundle(),
        schema_dir=SCHEMA_DIR,
        registry=registry,
        repo="stranske/Capability-Consumer",
        manifest=None,
    )
    assert report.conformant
    assert report.role == "consumer"

    report_bad = mod.validate_envelope(
        envelope=_valid_capability_bundle(gates=[]),
        schema_dir=SCHEMA_DIR,
        registry=registry,
        repo="stranske/Capability-Consumer",
        manifest=None,
    )
    assert not report_bad.conformant
    assert any("capability-bundle/v1" in v.message for v in report_bad.violations)


def _validate_mosaic_consumer(record: dict):
    return _import_validator().validate_envelope(
        envelope=record,
        schema_dir=SCHEMA_DIR,
        registry={
            "participants": [
                {
                    "repo": "stranske/Mosaic-Consumer",
                    "role": "consumer",
                    "status": "conformant",
                    "ingests": ["mosaic-core/v1"],
                }
            ]
        },
        repo="stranske/Mosaic-Consumer",
        manifest=None,
    )


@pytest.mark.parametrize("kind", ["fact", "discrepancy", "thesis_claim", "thesis_check"])
def test_mosaic_consumer_validates_fixture(kind: str) -> None:
    record = json.loads((FIXTURES / f"valid_mosaic_{kind}.json").read_text())
    report = _validate_mosaic_consumer(record)
    assert report.conformant, [v.message for v in report.violations]
    assert report.role == "consumer"
    assert not report.skipped


def test_mosaic_consumer_rejects_malformed_fact() -> None:
    record = json.loads((FIXTURES / "valid_mosaic_fact.json").read_text())
    record["fact_key"] = ""
    report = _validate_mosaic_consumer(record)
    assert not report.conformant
    assert any("ingested-as-mosaic-core/v1" in v.message for v in report.violations)


@pytest.mark.parametrize("checked_at", ["yesterday", "2026-02-30T12:00:00Z", "2026-09-19T12:00:00"])
def test_mosaic_consumer_rejects_invalid_timestamp(checked_at: str) -> None:
    record = json.loads((FIXTURES / "valid_mosaic_thesis_check.json").read_text())
    record["checked_at"] = checked_at
    report = _validate_mosaic_consumer(record)
    assert not report.conformant
    assert any("ingested-as-mosaic-core/v1" in v.message for v in report.violations)


def test_output_substrate_is_a_schema_validated_ingest_token() -> None:
    """output-substrate/v1 has a schema on disk and is enforced for consumers."""
    mod = _import_validator()
    assert mod.INGEST_SCHEMA_FILES["output-substrate/v1"] == "output-substrate-v1.schema.json"
    assert (SCHEMA_DIR / "output-substrate-v1.schema.json").is_file()

    registry = {
        "participants": [
            {
                "repo": "stranske/Output-Substrate-Consumer",
                "role": "consumer",
                "status": "conformant",
                "ingests": ["output-substrate/v1"],
            }
        ]
    }
    report = mod.validate_envelope(
        envelope=json.loads((FIXTURES / "valid_output_substrate.json").read_text()),
        schema_dir=SCHEMA_DIR,
        registry=registry,
        repo="stranske/Output-Substrate-Consumer",
        manifest=None,
    )
    assert report.conformant
    assert report.role == "consumer"


def _validate_output_substrate_consumer(record: dict):
    return _import_validator().validate_envelope(
        envelope=record,
        schema_dir=SCHEMA_DIR,
        registry={
            "participants": [
                {
                    "repo": "stranske/Output-Substrate-Consumer",
                    "role": "consumer",
                    "status": "conformant",
                    "ingests": ["output-substrate/v1"],
                }
            ]
        },
        repo="stranske/Output-Substrate-Consumer",
        manifest=None,
    )


def test_output_substrate_consumer_validates_fixture() -> None:
    record = json.loads((FIXTURES / "valid_output_substrate.json").read_text())
    report = _validate_output_substrate_consumer(record)
    assert report.conformant, [v.message for v in report.violations]
    assert report.role == "consumer"
    assert not report.skipped


def test_output_substrate_consumer_rejects_missing_renderer_profile() -> None:
    record = json.loads((FIXTURES / "valid_output_substrate.json").read_text())
    del record["renderer_profile"]
    report = _validate_output_substrate_consumer(record)
    assert not report.conformant
    assert any("ingested-as-output-substrate/v1" in v.message for v in report.violations)


def _validate_mirror_consumer(catalog: dict):
    return _import_validator().validate_envelope(
        envelope=catalog,
        schema_dir=SCHEMA_DIR,
        registry={
            "participants": [
                {
                    "repo": "stranske/Mirror-Consumer",
                    "role": "consumer",
                    "status": "conformant",
                    "ingests": ["document-mirror/v1"],
                }
            ]
        },
        repo="stranske/Mirror-Consumer",
        manifest=None,
    )


def test_document_mirror_consumer_validates_fixture() -> None:
    catalog = json.loads((FIXTURES / "valid_document_mirror.json").read_text())
    report = _validate_mirror_consumer(catalog)
    assert report.conformant, [v.message for v in report.violations]
    assert report.role == "consumer"
    assert not report.skipped


def test_document_mirror_consumer_rejects_invalid_urls_and_created_at() -> None:
    catalog = json.loads((FIXTURES / "invalid_document_mirror_bad_urls.json").read_text())
    report = _validate_mirror_consumer(catalog)
    assert not report.conformant
    assert any("ingested-as-document-mirror/v1" in v.message for v in report.violations)
