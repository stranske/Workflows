import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from scripts import langsmith_fleet

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "langsmith_fleet_registry.json"
FLEET_ALLOWLIST = ROOT / "config" / "langsmith_fleet_allowlist.json"
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


def test_paused_registry_entry_requires_governance_metadata() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    broken = copy.deepcopy(registry)
    workflows_entry = next(
        entry for entry in broken["repos"] if entry["repo"] == "stranske/Workflows"
    )
    workflows_entry.pop("pause_owner")

    with pytest.raises(ValueError, match="pause_owner.*when rollout_status is paused"):
        langsmith_fleet.validate_registry(broken)


def test_paused_registry_entry_has_reviewable_resume_contract() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    workflows_entry = next(
        entry for entry in registry["repos"] if entry["repo"] == "stranske/Workflows"
    )

    assert workflows_entry["paused_at"] == "2026-06-13T13:36:33Z"
    assert workflows_entry["pause_owner"] == "stranske/Workflows#2150"
    assert workflows_entry["review_by"] == "2026-09-15"
    assert "cloud LangSmith tracing remains active" in workflows_entry["pause_reason"]
    assert "conformant langsmith-fleet.ndjson" in workflows_entry["resume_condition"]


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
    # Derived from the allowlist rather than pinned: the allowlist is the exemption list and grows
    # when a new consumer is registered without a traced runtime. Its MEMBERSHIP is deliberately
    # pinned in tests/workflows/test_langsmith_metrics_dashboard.py, which is the check that must
    # fail visibly when a repo is exempted; pinning the count here as well only duplicates that
    # guard and breaks on every legitimate registration.
    allowlist = json.loads(FLEET_ALLOWLIST.read_text(encoding="utf-8"))
    assert f"- Not applicable: {len(allowlist['repos'])}" in markdown

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


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"schema_version": "wrong", "repos": []}, "schema_version"),
        ({"schema_version": langsmith_fleet.ALLOWLIST_SCHEMA_VERSION, "repos": []}, "non-empty"),
        (
            {
                "schema_version": langsmith_fleet.ALLOWLIST_SCHEMA_VERSION,
                "repos": ["not-an-object"],
            },
            "must be an object",
        ),
    ],
)
def test_allowlist_validation_rejects_invalid_root_shapes(
    payload: dict[str, object], message: str
) -> None:
    """The exemption list must fail closed before registry coverage is derived."""
    with pytest.raises(ValueError, match=message):
        langsmith_fleet.validate_allowlist(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repo", "", r"repos\[0\]\.repo"),
        ("status", "active", r"repos\[0\]\.status"),
        ("reason", "", r"repos\[0\]\.reason"),
        ("registry_activation_condition", "", r"repos\[0\]\.registry_activation_condition"),
    ],
)
def test_allowlist_validation_rejects_invalid_entries(
    field: str, value: object, message: str
) -> None:
    payload = {
        "schema_version": langsmith_fleet.ALLOWLIST_SCHEMA_VERSION,
        "repos": [
            {
                "repo": "stranske/example",
                "status": "not-applicable",
                "reason": "not deployed",
                "registry_activation_condition": "deployment",
            }
        ],
    }
    payload["repos"][0][field] = value

    with pytest.raises(ValueError, match=message):
        langsmith_fleet.validate_allowlist(payload)


def test_load_ndjson_and_record_helpers_reject_malformed_input(tmp_path: Path) -> None:
    missing_records, missing_errors = langsmith_fleet.load_ndjson(tmp_path / "missing.ndjson")
    assert missing_records == []
    assert "does not exist" in missing_errors[0].message

    fixture = tmp_path / "records.ndjson"
    fixture.write_text("[]\n{bad json}\n\n", encoding="utf-8")
    records, errors = langsmith_fleet.load_ndjson(fixture)
    assert records == []
    assert [error.line for error in errors] == [1, 2]

    assert langsmith_fleet._is_hash_or_ref(None)
    assert not langsmith_fleet._is_hash_or_ref(1)
    assert not langsmith_fleet._is_hash_or_ref(" ")
    assert langsmith_fleet._is_hash_or_ref("ref:artifact")
    assert langsmith_fleet._validate_number({"value": True}, "value", 7)
    assert langsmith_fleet._validate_number({"value": -1}, "value", 7)
    assert langsmith_fleet._validate_recorded_at("not-a-timestamp", 7)


def test_validate_record_reports_optional_field_and_registry_contract_errors() -> None:
    record = {
        "schema_version": "wrong",
        "repo": "",
        "surface": "",
        "operation": "",
        "run_id": "",
        "status": "unknown",
        "github_issue": "",
        "domain": {},
        "latency_ms": True,
        "cost_usd": -1,
        "recorded_at": 2,
        "input_hash": "bad",
        "output_hash": 3,
        "trace_url": 1,
        "trace_id": 2,
    }
    errors = langsmith_fleet.validate_record(record, registry={"repos": []})
    messages = {error.message for error in errors}

    assert "schema_version must be langsmith-fleet/v1" in messages
    assert "latency_ms must be a number when present" in messages
    assert "cost_usd must be non-negative" in messages
    assert "recorded_at must be an ISO timestamp" in messages
    assert "trace_url must be a string when present" in messages
    assert "trace_id must be a string when present" in messages
    assert "input_hash must be a hash or artifact reference" in messages
    assert "output_hash must be a hash or artifact reference" in messages
    assert "/ is not in registry" in messages


def test_registry_surfaces_latest_timestamp_and_cli_error_paths(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    assert langsmith_fleet.registry_surfaces({"repos": [None, {"repo": "x", "surface": ""}]}) == {}

    records = tmp_path / "invalid.ndjson"
    records.write_text("{bad}\n", encoding="utf-8")
    monkeypatch.setattr(
        langsmith_fleet.sys,
        "argv",
        ["langsmith_fleet.py", str(records), "--registry", str(REGISTRY)],
    )
    with pytest.raises(SystemExit) as exc:
        langsmith_fleet.main()
    assert exc.value.code == 1
    assert "invalid JSON" in capsys.readouterr().err

    monkeypatch.setattr(
        langsmith_fleet.sys,
        "argv",
        [
            "langsmith_fleet.py",
            str(FIXTURES / "valid.ndjson"),
            "--registry",
            str(REGISTRY),
            "--summary",
            "--format",
            "markdown",
        ],
    )
    langsmith_fleet.main()
    markdown = capsys.readouterr().out
    assert "# LangSmith Fleet Artifact Status" in markdown
    assert (
        "| stranske/Workflows | agent-automation |" in markdown
        and "stranske/Workflows#2150" in markdown
        and "| 2 | 2026-05-31T02:00:00+00:00 |" in markdown
    )


@pytest.mark.parametrize(
    ("timestamps", "expected"),
    [
        (["bad", None, ""], None),
        (
            ["bad", "2026-01-01T00:00:00Z"],
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
        (["2026-01-01T00:00:00"], datetime(2026, 1, 1, tzinfo=UTC)),
        (
            ["2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"],
            datetime(2026, 1, 2, tzinfo=UTC),
        ),
        (
            ["2026-01-01T23:00:00-02:00", "2026-01-02T00:00:00Z"],
            datetime(2026, 1, 2, 1, tzinfo=UTC),
        ),
    ],
    ids=["invalid", "invalid-then-valid", "naive-utc", "newest-first", "offset-order"],
)
def test_latest_recorded_at_ignores_invalid_and_compares_instants(
    timestamps: list[str | None], expected: datetime | None
) -> None:
    # Keep normalization and ordering observable independently: a later valid
    # timestamp must not hide dropped naive timestamps or reversed comparisons.
    records = [{"recorded_at": timestamp} for timestamp in timestamps]
    assert langsmith_fleet._latest_recorded_at(records) == expected


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("schema", "schema_version"),
        ("stale-type", "stale_after_hours must be an integer"),
        ("stale-value", "stale_after_hours must be positive"),
        ("repos", "repos must be a non-empty list"),
        ("entry", r"repos\[0\] must be an object"),
        ("repo", r"repos\[0\]\.repo"),
        ("surface", r"repos\[0\]\.surface"),
        ("issue-number-type", "issue_number must be an integer"),
        ("issue-number-value", "issue_number must be positive"),
        ("issue", "issue must be a non-empty string"),
        ("issue-mismatch", "issue must match repo#issue_number"),
        ("parent", "parent_issue must be a non-empty string"),
        ("parent-mismatch", "parent_issue must be stranske/Workflows#2150"),
        ("artifact", "artifact_name must be a non-empty string"),
        ("evidence", "evidence_mode must be one of"),
        ("rollout", "rollout_status must be a non-empty string"),
        ("operations", "operations must be a non-empty list"),
        ("operations-item", "operations must contain non-empty strings"),
        ("fields", "required_domain_fields must be a non-empty list"),
        ("fields-item", "required_domain_fields must contain non-empty strings"),
    ],
)
def test_registry_validation_rejects_each_entry_contract(kind: str, message: str) -> None:
    """Every persisted registry field protects a distinct fleet-routing invariant."""
    registry = copy.deepcopy(langsmith_fleet.load_registry(REGISTRY))
    entry = registry["repos"][0]
    if kind == "schema":
        registry["schema_version"] = "wrong"
    elif kind == "stale-type":
        registry["stale_after_hours"] = True
    elif kind == "stale-value":
        registry["stale_after_hours"] = 0
    elif kind == "repos":
        registry["repos"] = []
    elif kind == "entry":
        registry["repos"] = [None]
    elif kind == "repo":
        entry["repo"] = ""
    elif kind == "surface":
        entry["surface"] = ""
    elif kind == "issue-number-type":
        entry["issue_number"] = True
    elif kind == "issue-number-value":
        entry["issue_number"] = 0
    elif kind == "issue":
        entry["issue"] = ""
    elif kind == "issue-mismatch":
        entry["issue"] = "stranske/Workflows#0"
    elif kind == "parent":
        entry["parent_issue"] = ""
    elif kind == "parent-mismatch":
        entry["parent_issue"] = "stranske/Workflows#0"
    elif kind == "artifact":
        entry["artifact_name"] = ""
    elif kind == "evidence":
        entry["evidence_mode"] = "untrusted"
    elif kind == "rollout":
        entry["rollout_status"] = ""
    elif kind == "operations":
        entry["operations"] = []
    elif kind == "operations-item":
        entry["operations"] = [""]
    elif kind == "fields":
        entry["required_domain_fields"] = []
    else:
        entry["required_domain_fields"] = [""]

    with pytest.raises(ValueError, match=message):
        langsmith_fleet.validate_registry(registry)


@pytest.mark.parametrize(
    ("paused_at", "review_by", "message"),
    [
        ("not-a-date", "2026-09-15", "paused_at must be an ISO timestamp"),
        ("2026-06-13T13:36:33", "2026-09-15", "paused_at must include a timezone"),
        ("2026-06-13T13:36:33Z", "not-a-date", "review_by must be an ISO date"),
        ("2026-06-13T13:36:33Z", "2026-01-01", "review_by cannot predate paused_at"),
    ],
)
def test_paused_registry_timestamps_are_governed(
    paused_at: str, review_by: str, message: str
) -> None:
    registry = copy.deepcopy(langsmith_fleet.load_registry(REGISTRY))
    paused = next(entry for entry in registry["repos"] if entry["rollout_status"] == "paused")
    paused["paused_at"] = paused_at
    paused["review_by"] = review_by

    with pytest.raises(ValueError, match=message):
        langsmith_fleet.validate_registry(registry)


def test_module_bootstraps_repo_root_onto_sys_path(monkeypatch) -> None:
    """Import-time bootstrap inserts the repo root when it is absent from sys.path."""
    import importlib
    import sys

    root = str(langsmith_fleet.ROOT)
    monkeypatch.setattr(sys, "path", [entry for entry in sys.path if entry != root])
    reloaded = importlib.reload(langsmith_fleet)
    assert root in sys.path
    # Keep the canonical module object in place for later tests in this process.
    importlib.reload(reloaded)


def test_load_helpers_reject_non_object_json_roots(tmp_path: Path) -> None:
    """Schema/allowlist/registry loaders fail closed on non-object JSON roots."""
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="record schema must be a JSON object"):
        langsmith_fleet.load_record_schema(schema_path)

    allowlist_path = tmp_path / "allowlist.json"
    allowlist_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="allowlist must be a JSON object"):
        langsmith_fleet.load_allowlist(allowlist_path)

    registry_path = tmp_path / "registry.json"
    registry_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="registry must be a JSON object"):
        langsmith_fleet.load_registry(registry_path, allowlist_path=None)


def test_load_registry_skips_missing_allowlist_and_uses_embedded(
    tmp_path: Path,
) -> None:
    """Allowlist loading is optional; embedded _allowlist still validates."""
    registry = copy.deepcopy(langsmith_fleet.load_registry(REGISTRY))
    assert isinstance(registry.get("_allowlist"), dict)
    path = tmp_path / "registry.json"
    # Persist without rewriting allowlist; missing allowlist path must not reload it.
    path.write_text(json.dumps(registry), encoding="utf-8")

    loaded = langsmith_fleet.load_registry(path, allowlist_path=tmp_path / "missing-allowlist.json")
    assert loaded["_allowlist"]["schema_version"] == langsmith_fleet.ALLOWLIST_SCHEMA_VERSION

    # Embedded allowlist is honored when validate_registry receives allowlist=None.
    langsmith_fleet.validate_registry(loaded, allowlist=None)

    # Non-dict embedded allowlist is ignored (false branch of isinstance check).
    broken_embedded = copy.deepcopy(loaded)
    broken_embedded["_allowlist"] = "not-a-mapping"
    with pytest.raises(ValueError, match="managed consumer repos missing"):
        langsmith_fleet.validate_registry(broken_embedded, allowlist=None)


def test_allowlist_rejects_duplicate_repo() -> None:
    payload = {
        "schema_version": langsmith_fleet.ALLOWLIST_SCHEMA_VERSION,
        "repos": [
            {
                "repo": "stranske/example",
                "status": "not-applicable",
                "reason": "not deployed",
                "registry_activation_condition": "deployment",
            },
            {
                "repo": "stranske/example",
                "status": "not-applicable",
                "reason": "also not deployed",
                "registry_activation_condition": "still deployment",
            },
        ],
    }
    with pytest.raises(ValueError, match="duplicate repo stranske/example"):
        langsmith_fleet.validate_allowlist(payload)


def test_registry_rejects_duplicate_surface_and_conflicting_issue_numbers() -> None:
    registry = copy.deepcopy(langsmith_fleet.load_registry(REGISTRY))
    first = copy.deepcopy(registry["repos"][0])
    duplicate_surface = copy.deepcopy(first)
    with pytest.raises(ValueError, match="duplicate repo/surface mapping"):
        langsmith_fleet.validate_registry({**registry, "repos": [first, duplicate_surface]})

    conflict = copy.deepcopy(first)
    # Same repo, different surface, conflicting issue_number.
    conflict["surface"] = f"{first['surface']}-alt"
    conflict["issue_number"] = int(first["issue_number"]) + 1
    conflict["issue"] = f"{first['repo']}#{conflict['issue_number']}"
    with pytest.raises(ValueError, match="conflicting issue_number values"):
        langsmith_fleet.validate_registry({**registry, "repos": [first, conflict]})


@pytest.mark.parametrize(
    ("agents", "message"),
    [
        ({}, "agents must be a non-empty mapping"),
        ({"": {"capacity": {"window": "daily", "limit": 1}}}, "keys must be non-empty strings"),
        ({"codex": "not-an-object"}, "codex must be an object"),
    ],
)
def test_agent_registry_capacity_rejects_root_shapes(
    agents: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        langsmith_fleet.validate_agent_registry_capacity({"agents": agents})


def test_validate_record_reports_missing_required_field_and_bad_operation() -> None:
    registry = langsmith_fleet.load_registry(REGISTRY)
    entry = next(
        item
        for item in registry["repos"]
        if item["repo"] == "stranske/Pension-Data" and item["surface"] == "nl-to-sql"
    )
    record = {
        "schema_version": langsmith_fleet.SCHEMA_VERSION,
        "repo": entry["repo"],
        "surface": entry["surface"],
        "operation": "not-a-registered-operation",
        "run_id": "run-1",
        "status": "success",
        "github_issue": entry["issue"],
        "domain": {"query_category": "benefit"},
    }
    # Drop a required shared field entirely (distinct from empty-string checks).
    del record["run_id"]

    messages = {
        error.message for error in langsmith_fleet.validate_record(record, registry=registry)
    }
    assert "missing required field: run_id" in messages
    assert any("operation must be one of registry operations" in message for message in messages)

    # Registered entry with a non-dict domain skips operation/domain-field checks.
    non_dict_domain = {
        "schema_version": langsmith_fleet.SCHEMA_VERSION,
        "repo": entry["repo"],
        "surface": entry["surface"],
        "operation": "not-a-registered-operation",
        "run_id": "run-2",
        "status": "success",
        "github_issue": entry["issue"],
        "domain": "not-an-object",
    }
    domain_messages = {
        error.message
        for error in langsmith_fleet.validate_record(non_dict_domain, registry=registry)
    }
    assert "domain must be a non-empty object" in domain_messages
    assert not any(
        "operation must be one of registry operations" in message for message in domain_messages
    )


def test_cli_success_prints_validated_count(tmp_path: Path, monkeypatch, capsys) -> None:
    """Non-summary success path reports how many records validated."""
    monkeypatch.setattr(
        langsmith_fleet.sys,
        "argv",
        [
            "langsmith_fleet.py",
            str(FIXTURES / "valid.ndjson"),
            "--registry",
            str(REGISTRY),
        ],
    )
    langsmith_fleet.main()
    out = capsys.readouterr().out
    # Count fixture lines independently so a loader that drops records cannot
    # supply both the implementation and this test with the same wrong count.
    expected_count = len((FIXTURES / "valid.ndjson").read_text().splitlines())
    assert out == f"Validated {expected_count} {langsmith_fleet.SCHEMA_VERSION} record(s)\n"
