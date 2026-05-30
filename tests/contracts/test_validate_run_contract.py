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


def test_cli_exit_codes(tmp_path) -> None:
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
