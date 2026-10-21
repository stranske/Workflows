import json
import sys
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
    # Derived: one per allowlisted repo. Pinned at 3 until a 14th consumer was allowlisted.
    # Membership itself is pinned deliberately in test_langsmith_metrics_dashboard.py; this count
    # is incidental, so deriving it stops the 15th consumer breaking it again.
    import json as _json

    _allow = _json.loads(
        (
            Path(__file__).resolve().parents[2] / "config" / "langsmith_fleet_allowlist.json"
        ).read_text(encoding="utf-8")
    )
    assert report["status_counts"]["not-applicable"] == len(_allow["repos"])


def test_conformance_handles_empty_unknown_and_malformed_summary_rows(
    tmp_path: Path, monkeypatch
) -> None:
    registry = {
        "repos": [
            {"repo": "acme/empty", "surface": "s", "issue": 1, "artifact_name": "a.ndjson"},
            {"repo": "acme/unknown", "surface": "s", "issue": 2, "artifact_name": "b.ndjson"},
        ]
    }
    empty, unknown = tmp_path / "empty.ndjson", tmp_path / "unknown.ndjson"
    empty.write_text("")
    unknown.write_text('{"schema_version":"x"}\n')
    monkeypatch.setattr(langsmith_fleet, "load_record_schema", lambda: {})
    monkeypatch.setattr(langsmith_fleet, "validate_records", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        langsmith_fleet,
        "summarize_fleet_records",
        lambda records, **kwargs: {
            "rows": [
                {
                    "repo": "acme/unknown",
                    "surface": "s",
                    "status": "surprise",
                    "latest_recorded_at": "not-a-date",
                }
            ]
        },
    )
    report = langsmith_fleet_conformance.build_conformance_report(
        {"acme/empty": empty, "acme/unknown": unknown}, registry=registry
    )
    rows = {row["repo"]: row for row in report["rows"]}
    assert rows["acme/empty"]["status"] == "invalid"
    assert rows["acme/unknown"]["status"] == "invalid"
    assert rows["acme/unknown"]["first_error"] == "summary row returned unknown status"


def test_row_from_summary_skips_non_list_and_non_dict_rows() -> None:
    assert (
        langsmith_fleet_conformance.row_from_summary(
            {"rows": "not-a-list"}, repo="acme/r", surface="s"
        )
        is None
    )
    assert (
        langsmith_fleet_conformance.row_from_summary(
            {"rows": ["skip-me", {"repo": "acme/r", "surface": "s", "status": "ok"}]},
            repo="acme/r",
            surface="s",
        )["status"]
        == "ok"
    )


def test_conformance_format_and_main_json_and_markdown(tmp_path: Path, monkeypatch, capsys) -> None:
    report = {
        "total_registry_entries": 1,
        "total_allowlisted_repos": 0,
        "status_counts": {},
        "rows": [],
    }
    assert "Registry entries: 1" in langsmith_fleet_conformance.format_conformance_markdown(report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tool",
            "--registry",
            str(REGISTRY),
            "--records-root",
            str(tmp_path),
            "--format",
            "markdown",
        ],
    )
    langsmith_fleet_conformance.main()
    assert "LangSmith Fleet Conformance" in capsys.readouterr().out

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tool",
            "--registry",
            str(REGISTRY),
            "--records-root",
            str(tmp_path),
            "--format",
            "json",
        ],
    )
    langsmith_fleet_conformance.main()
    payload = json.loads(capsys.readouterr().out)
    assert "rows" in payload
    assert "status_counts" in payload
