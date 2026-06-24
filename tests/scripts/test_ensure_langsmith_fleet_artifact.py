import json
from datetime import datetime
from pathlib import Path

from scripts import ensure_langsmith_fleet_artifact, langsmith_fleet

try:
    from datetime import UTC
except ImportError:  # pragma: no cover - Python < 3.11 compatibility
    from datetime import timezone

    UTC = timezone.utc  # noqa: UP017 - fallback for Python < 3.11

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "langsmith_fleet_registry.json"


def test_ensure_artifact_writes_valid_error_record_for_implemented_repo(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"
    now = datetime(2026, 6, 24, 2, 30, tzinfo=UTC)

    result = ensure_langsmith_fleet_artifact.ensure_artifact(
        artifact_path=artifact,
        registry_path=REGISTRY,
        repository="stranske/Pension-Data",
        run_id="28068938440",
        run_attempt="1",
        workflow="CI",
        job="tests",
        python_version="3.12",
        sha="abc123",
        event_name="push",
        now=now,
    )

    assert result["status"] == "created"
    record = json.loads(artifact.read_text(encoding="utf-8"))
    assert record["schema_version"] == langsmith_fleet.SCHEMA_VERSION
    assert record["repo"] == "stranske/Pension-Data"
    assert record["surface"] == "nl-to-sql"
    assert record["operation"] == "sql-generation"
    assert record["status"] == "error"
    assert record["error_category"] == "ci_fleet_artifact_missing"
    assert record["run_id"] == "github-actions:28068938440:1:langsmith-fleet"
    assert record["recorded_at"] == "2026-06-24T02:30:00Z"
    assert record["input_hash"] == "ref:abc123"
    assert record["domain"]["query_category"] == "ci-fallback-no-records"
    assert record["domain"]["sql_validation_status"] == "ci_fallback_no_records"
    assert record["domain"]["read_only_status"] == "ci_fallback_no_records"
    assert record["domain"]["row_count"] == 0
    assert record["domain"]["fallback_reason"] == "ci_fleet_artifact_missing"

    registry = langsmith_fleet.load_registry(REGISTRY)
    schema = langsmith_fleet.load_record_schema()
    assert langsmith_fleet.validate_record(record, registry=registry, schema=schema) == []


def test_ensure_artifact_preserves_existing_repo_records(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"
    artifact.parent.mkdir(parents=True)
    original = '{"schema_version":"langsmith-fleet/v1","repo":"stranske/Pension-Data"}\n'
    artifact.write_text(original, encoding="utf-8")

    result = ensure_langsmith_fleet_artifact.ensure_artifact(
        artifact_path=artifact,
        registry_path=REGISTRY,
        repository="stranske/Pension-Data",
        run_id="28068938440",
        run_attempt="1",
        workflow="CI",
        job="tests",
        python_version="3.12",
        sha="abc123",
        event_name="push",
    )

    assert result["status"] == "existing"
    assert artifact.read_text(encoding="utf-8") == original


def test_ensure_artifact_skips_repos_without_implemented_artifact_rollout(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"

    result = ensure_langsmith_fleet_artifact.ensure_artifact(
        artifact_path=artifact,
        registry_path=REGISTRY,
        repository="stranske/Travel-Plan-Permission",
        run_id="28068938440",
        run_attempt="1",
        workflow="CI",
        job="tests",
        python_version="3.12",
        sha="abc123",
        event_name="push",
    )

    assert result == {
        "status": "skipped",
        "reason": "rollout_status_covered-via-langsmith-direct",
        "artifact_path": str(artifact),
        "repository": "stranske/Travel-Plan-Permission",
    }
    assert not artifact.exists()
