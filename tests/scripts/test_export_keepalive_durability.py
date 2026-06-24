import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts import export_keepalive_durability as exporter
from scripts import langsmith_fleet

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "langsmith_fleet_registry.json"


def _pr(number: int, *, merged_at: str, labels=None, closing=None, title: str | None = None):
    return {
        "number": number,
        "title": title or f"Implement issue {number}",
        "mergedAt": merged_at,
        "headRefName": "codex/issue-123",
        "labels": labels or [{"name": "agents:keepalive"}, {"name": "agent:codex"}],
        "closingIssuesReferences": closing or [{"number": 123, "state": "CLOSED"}],
    }


def test_build_records_exports_durable_reverted_and_reopened_records() -> None:
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    payloads = [
        {
            "repo": "stranske/Example",
            "prs": [
                _pr(10, merged_at="2026-06-10T00:00:00Z"),
                _pr(
                    11, merged_at="2026-06-10T00:00:00Z", closing=[{"number": 111, "state": "OPEN"}]
                ),
                _pr(12, merged_at="2026-06-10T00:00:00Z"),
                _pr(13, merged_at="2026-06-23T00:00:00Z"),
            ],
            "revert_prs": [
                {
                    "number": 99,
                    "title": 'Revert "Implement issue 12" (#12)',
                    "body": "",
                    "mergedAt": "2026-06-15T00:00:00Z",
                }
            ],
        }
    ]

    records, summary = exporter.build_records(payloads, now=now, grace_days=7)

    assert summary["counts"] == {"durable": 1, "pending": 1, "reopened": 1, "reverted": 1}
    assert summary["skipped"] == {"pending_grace": 1}
    by_pr = {record["github_pr"]: record for record in records}
    assert by_pr["stranske/Example#10"]["domain"]["durability"] == "durable"
    assert by_pr["stranske/Example#11"]["domain"]["durability"] == "reopened"
    assert by_pr["stranske/Example#12"]["domain"]["durability"] == "reverted"
    assert by_pr["stranske/Example#12"]["domain"]["evidence_pr"] == 99
    assert "stranske/Example#13" not in by_pr


def test_fleet_record_uses_workflows_surface_and_target_pr_bridge() -> None:
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    record = exporter.build_fleet_record(
        "stranske/Example",
        _pr(10, merged_at="2026-06-10T00:00:00Z"),
        {"durability": "durable", "reason": "no_revert_or_reopened_issue_after_grace"},
        now=now,
        grace_days=7,
    )

    assert record["repo"] == "stranske/Workflows"
    assert record["surface"] == "agent-automation"
    assert record["operation"] == "durability"
    assert record["github_pr"] == "stranske/Example#10"
    assert record["domain"]["agent"] == "codex"
    assert record["domain"]["target_repo"] == "stranske/Example"

    registry = langsmith_fleet.load_registry(REGISTRY)
    schema = langsmith_fleet.load_record_schema()
    assert langsmith_fleet.validate_record(record, registry=registry, schema=schema) == []


def test_pending_fleet_record_uses_skipped_status() -> None:
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    record = exporter.build_fleet_record(
        "stranske/Example",
        _pr(13, merged_at="2026-06-23T00:00:00Z"),
        {"durability": "pending", "reason": "inside_grace_window", "age_days": 1},
        now=now,
        grace_days=7,
    )

    assert record["status"] == "skipped"
    assert record["domain"]["durability"] == "pending"


def test_cli_writes_ndjson_from_input_payload(tmp_path: Path, capsys) -> None:
    payload = {
        "repos": [
            {
                "repo": "stranske/Example",
                "prs": [_pr(10, merged_at="2026-06-10T00:00:00Z")],
                "revert_prs": [],
            }
        ]
    }
    input_path = tmp_path / "payload.json"
    output_path = tmp_path / "langsmith-fleet.ndjson"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = exporter.main(
        [
            "--input-json",
            str(input_path),
            "--output",
            str(output_path),
            "--grace-days",
            "7",
            "--json",
        ]
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["records"] == 1
    line = output_path.read_text(encoding="utf-8").strip()
    assert json.loads(line)["operation"] == "durability"


def test_cli_rejects_unreadable_input_json(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(SystemExit) as excinfo:
        exporter.main(["--input-json", str(missing_path)])

    assert excinfo.value.code == 2


def test_cli_returns_failure_when_all_live_fetches_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "langsmith-fleet.ndjson"

    def fail_fetch(repo: str, *, since: str, limit: int) -> dict[str, object]:
        raise RuntimeError(f"{repo} unavailable")

    monkeypatch.setattr(exporter, "fetch_repo_payload", fail_fetch)

    exit_code = exporter.main(
        ["--repo", "stranske/Example", "--output", str(output_path), "--days", "1"]
    )

    assert exit_code == 1
    assert not output_path.exists()
