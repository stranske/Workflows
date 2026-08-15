import json
from datetime import UTC, datetime
from pathlib import Path

from scripts import langsmith_fleet, langsmith_fleet_conformance

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "langsmith_fleet_registry.json"


def test_conformance_report_marks_uploaded_malformed_pa_artifact_invalid(tmp_path: Path) -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    artifact = tmp_path / "pa.ndjson"
    artifact.write_text(
        json.dumps(
            {
                "schema": "legacy-pa-shape",
                "generated_at": "2026-05-30T00:00:00Z",
                "repo": "stranske/Portable-Alpha-Extension-Model",
                "status": "success",
                "domain": {"scenario_id": "base"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = langsmith_fleet_conformance.build_conformance_report(
        {"stranske/Portable-Alpha-Extension-Model": artifact},
        registry=registry,
        now=datetime(2026, 5, 30, 1, 0, tzinfo=UTC),
    )
    rows = {(row["repo"], row["surface"]): row for row in report["rows"]}
    pa_row = rows[("stranske/Portable-Alpha-Extension-Model", "scenario-analysis")]

    assert pa_row["status"] == "invalid"
    assert pa_row["record_count"] == 1
    assert pa_row["first_error"]
    assert "schema violation" in pa_row["first_error"]


def test_conformance_report_marks_conformant_artifact_valid(tmp_path: Path) -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    artifact = tmp_path / "pa.ndjson"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": langsmith_fleet.SCHEMA_VERSION,
                "repo": "stranske/Portable-Alpha-Extension-Model",
                "surface": "scenario-analysis",
                "operation": "scenario-run",
                "run_id": "pa-run-1",
                "status": "success",
                "github_issue": "stranske/Portable-Alpha-Extension-Model#1802",
                "recorded_at": "2026-05-30T00:00:00Z",
                "domain": {
                    "scenario_id": "base",
                    "config_hash": "sha256:abc",
                    "seed": 7,
                    "metric_delta": 0.1,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = langsmith_fleet_conformance.build_conformance_report(
        {"stranske/Portable-Alpha-Extension-Model": artifact},
        registry=registry,
        now=datetime(2026, 5, 30, 1, 0, tzinfo=UTC),
    )
    rows = {(row["repo"], row["surface"]): row for row in report["rows"]}

    assert (
        rows[("stranske/Portable-Alpha-Extension-Model", "scenario-analysis")]["status"] == "valid"
    )


def test_artifact_paths_from_root_uses_registry_artifact_names(tmp_path: Path) -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)

    paths = langsmith_fleet_conformance.artifact_paths_from_root(tmp_path, registry)

    assert paths["stranske/Portable-Alpha-Extension-Model"] == (
        tmp_path / "stranske__Portable-Alpha-Extension-Model" / "langsmith-fleet.ndjson"
    )
    assert "stranske/Travel-Plan-Permission" not in paths


def test_conformance_reports_direct_and_not_applicable_without_artifacts(tmp_path: Path) -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)

    report = langsmith_fleet_conformance.build_conformance_report(
        {},
        registry=registry,
        now=datetime(2026, 5, 30, 1, 0, tzinfo=UTC),
    )
    rows = {(row["repo"], row["surface"]): row for row in report["rows"]}

    assert rows[("stranske/Travel-Plan-Permission", "agent-automation")]["status"] == "direct"
    assert rows[("stranske/Ready", "")]["status"] == "not-applicable"
    assert report["status_counts"]["direct"] == 3
    assert report["status_counts"]["not-applicable"] == 3
