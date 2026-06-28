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


def _write_registry(tmp_path: Path, repos: list[dict]) -> Path:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"repos": repos}), encoding="utf-8")
    return registry_path


def _ensure_kwargs(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "run_id": "28068938440",
        "run_attempt": "1",
        "workflow": "CI",
        "job": "tests",
        "python_version": "3.12",
        "sha": "abc123",
        "event_name": "push",
    }
    defaults.update(overrides)
    return defaults


def _contract_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "repo": "stranske/example-repo",
        "issue": "stranske/example-repo#1",
        "surface": "example-surface",
        "operations": ["example-operation"],
        "artifact_name": "langsmith-fleet.ndjson",
        "rollout_status": "implemented",
        "required_domain_fields": ["example_status"],
    }
    entry.update(overrides)
    return entry


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


def test_ensure_artifact_skips_ambiguous_registry_contract(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "repos": [
                    {
                        "repo": "stranske/Pension-Data",
                        "issue": "stranske/Pension-Data#445",
                        "surface": "nl-to-sql",
                        "operations": ["sql-generation"],
                        "artifact_name": "langsmith-fleet.ndjson",
                        "rollout_status": "implemented",
                        "required_domain_fields": ["query_category"],
                    },
                    {
                        "repo": "stranske/Pension-Data",
                        "issue": "stranske/Pension-Data#446",
                        "surface": "benefits-summary",
                        "operations": ["summary-generation"],
                        "artifact_name": "langsmith-fleet.ndjson",
                        "rollout_status": "implemented",
                        "required_domain_fields": ["summary_status"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = ensure_langsmith_fleet_artifact.ensure_artifact(
        artifact_path=artifact,
        registry_path=registry_path,
        repository="stranske/Pension-Data",
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
        "reason": "repository_langsmith_artifact_contract_ambiguous",
        "artifact_path": str(artifact),
        "repository": "stranske/Pension-Data",
    }
    assert not artifact.exists()


def test_main_notice_uses_github_actions_annotation_prefix(tmp_path: Path, capsys) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"

    rc = ensure_langsmith_fleet_artifact.main(
        [
            "--artifact-path",
            str(artifact),
            "--registry",
            str(REGISTRY),
            "--repository",
            "stranske/Pension-Data",
            "--run-id",
            "28068938440",
            "--run-attempt",
            "1",
            "--workflow",
            "CI",
            "--job",
            "tests",
            "--python-version",
            "3.12",
            "--sha",
            "abc123",
            "--event-name",
            "push",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "::notice::Created LangSmith fleet fallback artifact" in captured.out
    assert "::notice ::" not in captured.out


def test_ensure_artifact_treats_empty_artifact_file_as_missing(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("", encoding="utf-8")
    registry_path = _write_registry(tmp_path, [_contract_entry()])

    result = ensure_langsmith_fleet_artifact.ensure_artifact(
        artifact_path=artifact,
        registry_path=registry_path,
        repository="stranske/example-repo",
        **_ensure_kwargs(),
    )

    assert result["status"] == "created"
    assert result["reason"] == "ci_fleet_artifact_missing"
    assert json.loads(artifact.read_text(encoding="utf-8"))["repo"] == "stranske/example-repo"


def test_ensure_artifact_treats_whitespace_only_artifact_as_missing(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("   \n\n  \n", encoding="utf-8")
    registry_path = _write_registry(tmp_path, [_contract_entry()])

    result = ensure_langsmith_fleet_artifact.ensure_artifact(
        artifact_path=artifact,
        registry_path=registry_path,
        repository="stranske/example-repo",
        **_ensure_kwargs(),
    )

    assert result["status"] == "created"
    assert result["reason"] == "ci_fleet_artifact_missing"


def test_ensure_artifact_preserves_malformed_nonempty_artifact_lines(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"
    artifact.parent.mkdir(parents=True)
    original = "{not-valid-json\n"
    artifact.write_text(original, encoding="utf-8")

    result = ensure_langsmith_fleet_artifact.ensure_artifact(
        artifact_path=artifact,
        registry_path=REGISTRY,
        repository="stranske/Pension-Data",
        **_ensure_kwargs(),
    )

    assert result == {
        "status": "existing",
        "artifact_path": str(artifact),
        "repository": "stranske/Pension-Data",
    }
    assert artifact.read_text(encoding="utf-8") == original


def test_ensure_artifact_skips_repository_not_in_registry(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"
    registry_path = _write_registry(tmp_path, [_contract_entry()])

    result = ensure_langsmith_fleet_artifact.ensure_artifact(
        artifact_path=artifact,
        registry_path=registry_path,
        repository="stranske/unknown-repo",
        **_ensure_kwargs(),
    )

    assert result == {
        "status": "skipped",
        "reason": "repository_not_in_registry",
        "artifact_path": str(artifact),
        "repository": "stranske/unknown-repo",
    }
    assert not artifact.exists()


def test_ensure_artifact_skips_when_artifact_alias_is_absent(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"
    registry_path = _write_registry(
        tmp_path,
        [
            _contract_entry(
                artifact_name="legacy-fleet-alias.ndjson",
            )
        ],
    )

    result = ensure_langsmith_fleet_artifact.ensure_artifact(
        artifact_path=artifact,
        registry_path=registry_path,
        repository="stranske/example-repo",
        **_ensure_kwargs(),
    )

    assert result == {
        "status": "skipped",
        "reason": "repository_missing_langsmith_artifact_contract",
        "artifact_path": str(artifact),
        "repository": "stranske/example-repo",
    }
    assert not artifact.exists()


def test_main_emits_structured_skip_for_missing_repository_row(tmp_path: Path, capsys) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"
    registry_path = _write_registry(tmp_path, [_contract_entry()])

    rc = ensure_langsmith_fleet_artifact.main(
        [
            "--artifact-path",
            str(artifact),
            "--registry",
            str(registry_path),
            "--repository",
            "stranske/unknown-repo",
            "--run-id",
            "28068938440",
            "--run-attempt",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == json.dumps(
        {
            "artifact_path": str(artifact),
            "reason": "repository_not_in_registry",
            "repository": "stranske/unknown-repo",
            "status": "skipped",
        },
        sort_keys=True,
    )
    assert "::notice::" not in captured.out


def test_main_uses_project_root_fallback_artifact_path(tmp_path: Path, capsys) -> None:
    registry_path = _write_registry(tmp_path, [_contract_entry()])
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"

    rc = ensure_langsmith_fleet_artifact.main(
        [
            "--project-root",
            str(tmp_path),
            "--registry",
            str(registry_path),
            "--repository",
            "stranske/example-repo",
            "--run-id",
            "28068938440",
            "--run-attempt",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    result = json.loads(captured.out.splitlines()[0])
    assert result["status"] == "created"
    assert result["artifact_path"] == str(artifact)
    assert artifact.exists()
    assert "::notice::Created LangSmith fleet fallback artifact" in captured.out


def test_main_emits_structured_ensure_failed_for_malformed_registry(tmp_path: Path, capsys) -> None:
    artifact = tmp_path / "artifacts" / "langsmith" / "langsmith-fleet.ndjson"
    registry_path = tmp_path / "registry.json"
    registry_path.write_text("{", encoding="utf-8")

    rc = ensure_langsmith_fleet_artifact.main(
        [
            "--artifact-path",
            str(artifact),
            "--registry",
            str(registry_path),
            "--repository",
            "stranske/example-repo",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    result = json.loads(captured.out.strip())
    assert result["status"] == "skipped"
    assert result["reason"] == "ensure_failed"
    assert result["artifact_path"] == str(artifact)
    assert result["repository"] == "stranske/example-repo"
    assert "Expecting property name enclosed in double quotes" in result["error"]
    assert "::warning::LangSmith fleet fallback artifact ensure failed" in captured.err
