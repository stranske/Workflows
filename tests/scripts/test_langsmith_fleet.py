import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from scripts import langsmith_fleet

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "langsmith_fleet_registry.json"
ALLOWLIST = ROOT / "config" / "langsmith_fleet_allowlist.json"
MAINT_68 = ROOT / ".github" / "workflows" / "maint-68-sync-consumer-repos.yml"
AGENT_REGISTRY = ROOT / ".github" / "agents" / "registry.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "langsmith_fleet"


def test_valid_fixture_passes_registry_validation() -> None:
    records, parse_errors = langsmith_fleet.load_ndjson(FIXTURES / "valid.ndjson")
    registry = langsmith_fleet.load_registry(REGISTRY)
    schema = langsmith_fleet.load_record_schema()

    errors = parse_errors + langsmith_fleet.validate_records(
        records, registry=registry, schema=schema
    )

    assert errors == []


def test_valid_fixture_covers_each_registry_repo_surface() -> None:
    records, _ = langsmith_fleet.load_ndjson(FIXTURES / "valid.ndjson")
    registry = langsmith_fleet.load_registry(REGISTRY)

    fixture_pairs = {(record["repo"], record["surface"]) for record in records}
    registry_pairs = {(entry["repo"], entry["surface"]) for entry in registry["repos"]}

    assert fixture_pairs == registry_pairs


def test_invalid_fixture_reports_first_contract_errors() -> None:
    records, parse_errors = langsmith_fleet.load_ndjson(FIXTURES / "invalid.ndjson")
    registry = langsmith_fleet.load_registry(REGISTRY)
    schema = langsmith_fleet.load_record_schema()

    messages = [
        error.message
        for error in parse_errors
        + langsmith_fleet.validate_records(records, registry=registry, schema=schema)
    ]

    assert any(message.startswith("schema violation: input_hash:") for message in messages)
    assert "input_hash must be a hash or artifact reference" in messages
    assert "domain missing required field: planner_action" in messages
    assert "domain missing required field: tool_call_count" in messages
    assert "domain missing required field: fallback_state" in messages


def test_unknown_repo_surface_is_rejected() -> None:
    record = {
        "schema_version": langsmith_fleet.SCHEMA_VERSION,
        "repo": "stranske/unknown",
        "surface": "planner-runtime",
        "operation": "tool-call",
        "run_id": "run-1",
        "status": "success",
        "github_issue": "stranske/unknown#1",
        "domain": {"x": "y"},
    }
    registry = langsmith_fleet.load_registry(REGISTRY)
    schema = langsmith_fleet.load_record_schema()

    errors = langsmith_fleet.validate_record(record, registry=registry, schema=schema)

    assert errors[-1].message == "stranske/unknown/planner-runtime is not in registry"


def test_summary_distinguishes_valid_missing_and_invalid() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    valid_records, _ = langsmith_fleet.load_ndjson(FIXTURES / "valid.ndjson")
    records_without_counter_risk = [
        record
        for record in valid_records
        if not (record["repo"] == "stranske/Counter_Risk" and record["surface"] == "risk-reporting")
    ]
    invalid_record = {
        "schema_version": langsmith_fleet.SCHEMA_VERSION,
        "repo": "stranske/Pension-Data",
        "surface": "nl-to-sql",
        "operation": "validation",
        "run_id": "nl-query-1",
        "status": "success",
        "github_issue": "stranske/Pension-Data#445",
        "recorded_at": "2026-05-24T02:00:00Z",
        "domain": {"query_category": "benefit"},
    }

    summary = langsmith_fleet.summarize_fleet_records(
        [*records_without_counter_risk, invalid_record],
        registry=registry,
        now=datetime(2026, 5, 24, 3, 0, tzinfo=UTC),
    )
    rows = {(row["repo"], row["surface"]): row for row in summary["rows"]}

    assert rows[("stranske/Workflows", "agent-automation")]["status"] == "valid"
    assert rows[("stranske/trip-planner", "planner-runtime")]["status"] == "valid"
    assert rows[("stranske/Pension-Data", "nl-to-sql")]["status"] == "invalid"
    assert rows[("stranske/Counter_Risk", "risk-reporting")]["status"] == "missing"
    assert rows[("stranske/Travel-Plan-Permission", "agent-automation")]["status"] == "direct"
    assert rows[("stranske/Ready", "")]["status"] == "not-applicable"


def test_summary_distinguishes_stale_records() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    records, _ = langsmith_fleet.load_ndjson(FIXTURES / "valid.ndjson")

    summary = langsmith_fleet.summarize_fleet_records(
        records,
        registry=registry,
        now=datetime(2026, 6, 10, 0, 0, tzinfo=UTC),
    )
    rows = {(row["repo"], row["surface"]): row for row in summary["rows"]}

    assert rows[("stranske/Workflows", "agent-automation")]["status"] == "stale"


def test_markdown_summary_contains_dashboard_status_table() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    records, _ = langsmith_fleet.load_ndjson(FIXTURES / "valid.ndjson")
    summary = langsmith_fleet.summarize_fleet_records(records, registry=registry)

    markdown = langsmith_fleet.format_fleet_summary(summary)

    assert "# LangSmith Fleet Artifact Status" in markdown
    assert (
        "| stranske/Workflows | agent-automation | artifact | "
        "stranske/Workflows#2150 |" in markdown
    )
    assert "| stranske/Ready |  | none |  | not-applicable |" in markdown


def test_markdown_summary_renders_mixed_valid_invalid_missing_rows() -> None:
    """The maint-80 dashboard renders this exact markdown section.

    Feeds a mixed fleet (≥1 valid, ≥1 invalid, ≥1 missing) and asserts the
    rendered section text carries both the per-repo status rows and the
    aggregate counts the weekly dashboard surfaces.
    """
    registry = langsmith_fleet.load_registry(REGISTRY)
    valid_records, _ = langsmith_fleet.load_ndjson(FIXTURES / "valid.ndjson")

    # Drop Counter_Risk entirely -> its registry row renders as "missing".
    records_without_counter_risk = [
        record
        for record in valid_records
        if not (record["repo"] == "stranske/Counter_Risk" and record["surface"] == "risk-reporting")
    ]
    # A schema-incomplete Pension-Data record -> its row renders as "invalid".
    invalid_record = {
        "schema_version": langsmith_fleet.SCHEMA_VERSION,
        "repo": "stranske/Pension-Data",
        "surface": "nl-to-sql",
        "operation": "validation",
        "run_id": "nl-query-1",
        "status": "success",
        "github_issue": "stranske/Pension-Data#445",
        "recorded_at": "2026-05-24T02:00:00Z",
        "domain": {"query_category": "benefit"},
    }

    summary = langsmith_fleet.summarize_fleet_records(
        [*records_without_counter_risk, invalid_record],
        registry=registry,
        now=datetime(2026, 5, 24, 3, 0, tzinfo=UTC),
    )
    markdown = langsmith_fleet.format_fleet_summary(summary)

    # Aggregate counts (one registry row per repo; 11 total).
    assert "# LangSmith Fleet Artifact Status" in markdown
    assert f"- Registry entries: {len(registry['repos'])}" in markdown
    assert "- Invalid: 1" in markdown
    assert "- Missing: 1" in markdown
    assert "- Direct evidence: 3" in markdown
    assert "- Not applicable: 3" in markdown

    # Per-repo status rows, one per status flavor.
    assert (
        "| stranske/Workflows | agent-automation | artifact | "
        "stranske/Workflows#2150 | valid |" in markdown
    )
    assert (
        "| stranske/Pension-Data | nl-to-sql | artifact | "
        "stranske/Pension-Data#445 | invalid |" in markdown
    )
    assert (
        "| stranske/Counter_Risk | risk-reporting | artifact | "
        "stranske/Counter_Risk#610 | missing |" in markdown
    )


def test_cli_summary_json_shape(tmp_path: Path, capsys) -> None:
    records, _ = langsmith_fleet.load_ndjson(FIXTURES / "valid.ndjson")
    path = tmp_path / "records.ndjson"
    path.write_text("\n".join(json.dumps(record) for record in records))

    # Exercise the public formatter path without spawning a subprocess.
    registry = langsmith_fleet.load_registry(REGISTRY)
    summary = langsmith_fleet.summarize_fleet_records(records, registry=registry)
    print(json.dumps(summary, sort_keys=True))
    out = capsys.readouterr().out

    assert '"schema_version": "langsmith-fleet/v1"' in out


def test_cli_summary_can_report_invalid_records(capsys) -> None:
    argv = [
        "langsmith_fleet.py",
        str(FIXTURES / "invalid.ndjson"),
        "--summary",
        "--format",
        "json",
    ]

    original_argv = langsmith_fleet.sys.argv
    try:
        langsmith_fleet.sys.argv = argv
        langsmith_fleet.main()
    finally:
        langsmith_fleet.sys.argv = original_argv

    out = capsys.readouterr().out
    summary = json.loads(out)

    assert summary["status_counts"]["invalid"] >= 1


def test_validation_reports_original_ndjson_line_numbers(tmp_path: Path) -> None:
    path = tmp_path / "records.ndjson"
    path.write_text(
        "\n"
        "{not-json}\n"
        "\n"
        + json.dumps(
            {
                "schema_version": langsmith_fleet.SCHEMA_VERSION,
                "repo": "stranske/Workflows",
                "surface": "agent-automation",
                "operation": "verifier",
                "run_id": "run-1",
                "status": "success",
                "github_issue": "stranske/Workflows#2150",
                "input_hash": "",
                "domain": {"workflow": "verify"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    records, parse_errors = langsmith_fleet.load_ndjson(path)

    errors = parse_errors + langsmith_fleet.validate_records(records)

    assert parse_errors[0].line == 2
    assert any(error.line == 4 and "input_hash" in error.message for error in errors)


def test_registry_operation_allowlist_is_enforced() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    record = {
        "schema_version": langsmith_fleet.SCHEMA_VERSION,
        "repo": "stranske/Workflows",
        "surface": "agent-automation",
        "operation": "not-a-real-operation",
        "run_id": "run-1",
        "status": "success",
        "github_issue": "stranske/Workflows#2150",
        "domain": {"workflow": "verify"},
    }

    errors = langsmith_fleet.validate_record(record, registry=registry)

    assert any("operation must be one of registry operations" in error.message for error in errors)


def test_empty_hash_references_are_invalid_when_present() -> None:
    record = {
        "schema_version": langsmith_fleet.SCHEMA_VERSION,
        "repo": "stranske/Workflows",
        "surface": "agent-automation",
        "operation": "verifier",
        "run_id": "run-1",
        "status": "success",
        "github_issue": "stranske/Workflows#2150",
        "input_hash": " ",
        "domain": {"workflow": "verify"},
    }

    errors = langsmith_fleet.validate_record(record)

    assert any(
        error.message == "input_hash must be a hash or artifact reference" for error in errors
    )


def test_schema_rejects_wrong_domain_type() -> None:
    record = {
        "schema_version": langsmith_fleet.SCHEMA_VERSION,
        "repo": "stranske/Workflows",
        "surface": "agent-automation",
        "operation": "verifier",
        "run_id": "run-1",
        "status": "success",
        "github_issue": "stranske/Workflows#2150",
        "domain": "invalid",
    }
    schema = langsmith_fleet.load_record_schema()

    errors = langsmith_fleet.validate_record(record, schema=schema)

    assert any("schema violation: domain:" in error.message for error in errors)


def test_registry_contains_active_repo_issue_mappings() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    by_repo = {entry["repo"]: entry for entry in registry["repos"]}

    expected = {
        "stranske/trip-planner": 1208,
        "stranske/Pension-Data": 445,
        "stranske/Manager-Database": 1048,
        "stranske/Counter_Risk": 610,
        "stranske/Inv-Man-Intake": 438,
        "stranske/Trend_Model_Project": 5311,
        "stranske/Portable-Alpha-Extension-Model": 1802,
    }
    for repo, issue_number in expected.items():
        assert by_repo[repo]["issue_number"] == issue_number
        assert by_repo[repo]["issue"] == f"{repo}#{issue_number}"
        assert by_repo[repo]["parent_issue"] == langsmith_fleet.PARENT_WORKFLOWS_ISSUE


def test_managed_consumers_are_registered_or_explicitly_allowlisted() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    allowlist = langsmith_fleet.load_allowlist(ALLOWLIST)
    registered = {
        entry["repo"] for entry in registry["repos"] if entry["repo"] != "stranske/Workflows"
    }
    allowlisted = {entry["repo"] for entry in allowlist["repos"]}

    source = MAINT_68.read_text(encoding="utf-8")
    block = source.split("REGISTERED_CONSUMER_REPOS: |", 1)[1].split("\n\n", 1)[0]
    maintained = {line.strip() for line in block.splitlines() if line.strip()}

    assert maintained == langsmith_fleet.MANAGED_CONSUMER_REPOS
    assert maintained == registered | allowlisted
    assert not registered & allowlisted


def test_direct_evidence_repos_do_not_require_artifacts() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    summary = langsmith_fleet.summarize_fleet_records([], registry=registry)
    rows = {(row["repo"], row["surface"]): row for row in summary["rows"]}

    for repo in (
        "stranske/Travel-Plan-Permission",
        "stranske/learning-management-system",
        "stranske/Fine-Art-Archive",
    ):
        assert rows[(repo, "agent-automation")]["status"] == "direct"
        assert rows[(repo, "agent-automation")]["record_count"] == 0


def test_registry_rejects_repo_that_is_also_allowlisted() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    allowlist = langsmith_fleet.load_allowlist(ALLOWLIST)
    allowlist["repos"].append(
        {
            "repo": "stranske/trip-planner",
            "status": "not-applicable",
            "reason": "deliberate overlap",
            "registry_activation_condition": "already active",
        }
    )

    with pytest.raises(ValueError, match="both registered and allowlisted"):
        langsmith_fleet.validate_registry(registry, allowlist=allowlist)


def test_registry_rejects_unclassified_managed_consumer() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    allowlist = langsmith_fleet.load_allowlist(ALLOWLIST)
    allowlist["repos"] = [
        entry for entry in allowlist["repos"] if entry["repo"] != "stranske/Ready"
    ]

    with pytest.raises(ValueError, match="stranske/Ready"):
        langsmith_fleet.validate_registry(registry, allowlist=allowlist)


def test_registry_rejects_missing_parent_issue(tmp_path: Path) -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    registry["repos"][1].pop("parent_issue")
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    try:
        langsmith_fleet.load_registry(path)
    except ValueError as exc:
        assert "parent_issue must be a non-empty string" in str(exc)
    else:
        raise AssertionError("expected load_registry to fail for missing parent issue")


def test_load_registry_rejects_mismatched_issue_and_issue_number(tmp_path: Path) -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    registry["repos"][1]["issue_number"] = 9999
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    try:
        langsmith_fleet.load_registry(path)
    except ValueError as exc:
        assert "issue must match repo#issue_number" in str(exc)
    else:
        raise AssertionError("expected load_registry to fail for mismatched issue mapping")


def test_registry_rejects_missing_active_repo_issue_mapping(tmp_path: Path) -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    registry["repos"] = [
        entry for entry in registry["repos"] if entry.get("repo") != "stranske/Inv-Man-Intake"
    ]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    try:
        langsmith_fleet.load_registry(path)
    except ValueError as exc:
        assert "registry missing required active repo issue mappings" in str(exc)
        assert "stranske/Inv-Man-Intake#438" in str(exc)
    else:
        raise AssertionError("expected load_registry to fail for missing active repo issue mapping")


def _load_agent_registry() -> dict[str, object]:
    loaded = yaml.safe_load(AGENT_REGISTRY.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_agent_registry_capacity_blocks_validate() -> None:
    registry = _load_agent_registry()

    langsmith_fleet.validate_registry(registry)

    agents = registry["agents"]
    assert set(agents) >= {"codex", "claude", "cursor", "gemini", "aider"}
    for agent in ("codex", "claude", "cursor", "gemini", "aider"):
        assert agents[agent]["capacity"]["window"] in {"5h", "weekly", "daily"}
        assert isinstance(agents[agent]["capacity"]["limit"], int)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("window", "bogus", "capacity.window must be one of"),
        ("limit", -1, "capacity.limit must be a positive integer"),
    ],
)
def test_agent_registry_capacity_rejects_malformed_values(
    field: str,
    value: object,
    message: str,
) -> None:
    registry = copy.deepcopy(_load_agent_registry())
    registry["agents"]["codex"]["capacity"][field] = value

    with pytest.raises(ValueError, match=message):
        langsmith_fleet.validate_registry(registry)


def test_agent_registry_capacity_is_required() -> None:
    registry = copy.deepcopy(_load_agent_registry())
    del registry["agents"]["codex"]["capacity"]

    with pytest.raises(ValueError, match=r"codex\.capacity must be an object"):
        langsmith_fleet.validate_registry(registry)
