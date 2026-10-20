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


@pytest.mark.parametrize(
    ("labels", "branch"),
    [
        ([{"name": "agent:auto"}, {"name": "agent:muse"}], "codex/issue-1"),
        ([{"name": "runner:muse"}], "codex/issue-1"),
        ([], "muse/issue-3955"),
    ],
)
def test_muse_durability_attribution_uses_the_producing_route(labels, branch):
    pr = _pr(10, merged_at="2026-06-10T00:00:00Z")
    pr.update(labels=labels, headRefName=branch, author={"login": "stranske"})
    record = exporter.build_fleet_record(
        "stranske/Example",
        pr,
        {"durability": "durable", "reason": "no_revert_or_reopened_issue_after_grace"},
        now=datetime(2026, 6, 24, 12, 0, tzinfo=UTC),
        grace_days=7,
    )
    assert record["domain"]["agent"] == "muse"


def test_helpers_handle_invalid_metadata_and_reverts_before_the_merge() -> None:
    assert exporter._parse_time("not-a-date") is None
    assert exporter._parse_time(3) is None
    assert exporter._label_names({"labels": ["  keep  ", {"name": " agent:codex "}, None]}) == [
        "keep",
        "agent:codex",
    ]
    assert exporter.infer_agent({"head_ref": "muse-fix"}) == "muse"
    pr = _pr(7, merged_at="2026-06-10T00:00:00Z")
    assert (
        exporter._matching_revert(
            pr, [{"number": 8, "title": "Revert #7", "mergedAt": "2026-06-09T00:00:00Z"}]
        )
        is None
    )
    assert exporter.classify_durability(
        {"number": 0}, revert_prs=[], now=datetime(2026, 6, 24, tzinfo=UTC), grace_days=7
    ) == {"durability": "skipped", "reason": "missing_merged_pr_metadata"}


def test_build_records_skips_invalid_rows_and_can_include_pending() -> None:
    records, summary = exporter.build_records(
        [
            {"repo": "", "prs": []},
            {"repo": "o/r", "prs": [None, _pr(1, merged_at="2026-06-23T00:00:00Z")]},
        ],
        now=datetime(2026, 6, 24, tzinfo=UTC),
        grace_days=7,
        include_pending=True,
    )
    assert len(records) == 1
    assert records[0]["status"] == "skipped"
    assert summary["skipped"] == {"invalid_pr": 1, "missing_repo": 1}


def test_registry_fetch_and_ndjson_helpers_cover_error_and_success_paths(
    tmp_path: Path, monkeypatch
) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        '{"repos":[{"repo":"o/a"},{"repo":"o/a"},{"repo":" o/b "}]}', encoding="utf-8"
    )
    assert exporter.registry_repos(registry) == ["o/a", "o/b"]

    class Result:
        returncode = 1
        stderr = "bad request"
        stdout = ""

    monkeypatch.setattr(exporter.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(RuntimeError, match="bad request"):
        exporter._gh_json(["pr", "list"])

    exporter.write_ndjson([{"z": 1, "a": 2}], tmp_path / "nested" / "out.ndjson")
    assert (tmp_path / "nested" / "out.ndjson").read_text(encoding="utf-8") == '{"a":2,"z":1}\n'


def test_fetch_repo_payload_requests_the_merged_and_revert_views(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_gh_json(args: list[str]) -> list[dict[str, object]]:
        calls.append(args)
        return [{"number": len(calls)}]

    monkeypatch.setattr(exporter, "_gh_json", fake_gh_json)
    payload = exporter.fetch_repo_payload("owner/repo", since="2026-01-01", limit=12)

    assert payload == {"repo": "owner/repo", "prs": [{"number": 1}], "revert_prs": [{"number": 2}]}
    assert calls[0][:5] == ["pr", "list", "-R", "owner/repo", "--state"]
    assert calls[0][calls[0].index("--state") + 1] == "merged"
    assert "agents:keepalive" in calls[0]
    assert "Revert in:title merged:>=2026-01-01" in calls[1]


@pytest.mark.parametrize(
    ("argument", "value"), [("--days", "0"), ("--grace-days", "-1"), ("--limit", "0")]
)
def test_cli_rejects_invalid_numeric_limits(argument: str, value: str) -> None:
    with pytest.raises(SystemExit) as excinfo:
        exporter.main([argument, value])
    assert excinfo.value.code == 2


def test_helpers_cover_timezone_agent_and_closing_edge_cases() -> None:
    naive = exporter._parse_time("2026-06-10T00:00:00")
    assert naive is not None
    assert naive == datetime(2026, 6, 10, tzinfo=UTC)
    assert naive.tzinfo is UTC
    offset = exporter._parse_time("2026-06-10T02:00:00+02:00")
    assert offset == naive
    assert offset.tzinfo is UTC
    assert (
        exporter.infer_agent(
            {"labels": [{"name": "runner:auto"}, {"name": "agent:muse"}], "headRefName": "x"}
        )
        == "muse"
    )
    assert exporter.infer_agent({"labels": [], "headRefName": "feature/x"}) == "unknown"
    assert exporter._matching_revert({"number": 0}, [{"number": 1, "title": "Revert #0"}]) is None
    pr_without_closing = _pr(10, merged_at="2026-06-10T00:00:00Z")
    pr_without_closing["closingIssuesReferences"] = []
    record = exporter.build_fleet_record(
        "stranske/Example",
        pr_without_closing,
        {"durability": "durable", "reason": "no_revert_or_reopened_issue_after_grace"},
        now=datetime(2026, 6, 24, 12, 0, tzinfo=UTC),
        grace_days=7,
    )
    assert "target_issue" not in record["domain"]


def test_gh_json_filters_non_dicts_and_rejects_non_list_payloads(monkeypatch) -> None:
    class Ok:
        returncode = 0
        stderr = ""
        stdout = '[{"n":1},"skip",{"n":2}]'

    monkeypatch.setattr(exporter.subprocess, "run", lambda *args, **kwargs: Ok())
    assert exporter._gh_json(["pr", "list"]) == [{"n": 1}, {"n": 2}]

    class NotList:
        returncode = 0
        stderr = ""
        stdout = '{"not":"list"}'

    monkeypatch.setattr(exporter.subprocess, "run", lambda *args, **kwargs: NotList())
    with pytest.raises(RuntimeError, match="JSON array"):
        exporter._gh_json(["pr", "list"])

    class EmptyFailure:
        returncode = 1
        stderr = ""
        stdout = ""

    monkeypatch.setattr(exporter.subprocess, "run", lambda *args, **kwargs: EmptyFailure())
    with pytest.raises(RuntimeError, match="gh command failed"):
        exporter._gh_json(["pr", "list"])


def test_build_records_skips_explicit_skipped_classifications() -> None:
    records, summary = exporter.build_records(
        [{"repo": "o/r", "prs": [{"number": 0}]}],
        now=datetime(2026, 6, 24, tzinfo=UTC),
        grace_days=7,
    )
    assert records == []
    assert summary["counts"]["skipped"] == 1
    assert summary["skipped"]["missing_merged_pr_metadata"] == 1


def test_cli_human_summary_and_partial_fetch_paths(tmp_path: Path, monkeypatch, capsys) -> None:
    payload = tmp_path / "payload.json"
    payload.write_text(
        json.dumps(
            {
                "repos": [
                    {
                        "repo": "stranske/Example",
                        "prs": [
                            _pr(10, merged_at="2026-06-10T00:00:00Z"),
                            {"number": 0},
                        ],
                        "revert_prs": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "out.ndjson"
    assert (
        exporter.main(
            [
                "--input-json",
                str(payload),
                "--output",
                str(output),
                "--grace-days",
                "7",
            ]
        )
        == 0
    )
    stdout = capsys.readouterr().out
    assert "wrote 1 record(s)" in stdout
    assert "counts:" in stdout
    assert "skipped:" in stdout

    bad_shape = tmp_path / "bad.json"
    bad_shape.write_text('{"repos": {}}', encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        exporter.main(["--input-json", str(bad_shape), "--output", str(tmp_path / "x.ndjson")])
    assert excinfo.value.code == 2

    def fake_fetch(repo: str, *, since: str, limit: int) -> dict:
        if repo == "owner/fail":
            raise RuntimeError("boom")
        return {
            "repo": repo,
            "prs": [_pr(21, merged_at="2026-06-10T00:00:00Z")],
            "revert_prs": [],
        }

    monkeypatch.setattr(exporter, "fetch_repo_payload", fake_fetch)
    monkeypatch.setattr(exporter, "registry_repos", lambda path: ["owner/fail", "owner/ok"])
    partial_out = tmp_path / "partial.ndjson"
    assert exporter.main(["--output", str(partial_out), "--days", "30"]) == 0
    err = capsys.readouterr().err
    assert "fetch_errors" in err
    assert "owner/fail" in err
    partial_records = [json.loads(line) for line in partial_out.read_text().splitlines()]
    assert [record["github_pr"] for record in partial_records] == ["owner/ok#21"]

    ok_out = tmp_path / "ok.ndjson"
    assert exporter.main(["--repo", "owner/ok", "--output", str(ok_out), "--days", "30"]) == 0
    assert ok_out.exists()

    empty_counts = tmp_path / "empty-counts.json"
    empty_counts.write_text('{"repos":[{"repo":"","prs":[]}]}', encoding="utf-8")
    empty_out = tmp_path / "empty.ndjson"
    capsys.readouterr()
    assert (
        exporter.main(
            ["--input-json", str(empty_counts), "--output", str(empty_out), "--grace-days", "7"]
        )
        == 0
    )
    empty_stdout = capsys.readouterr().out
    assert "wrote 0 record(s)" in empty_stdout
    assert "counts:" not in empty_stdout
    assert "skipped:" in empty_stdout
