import json
from collections import Counter
from pathlib import Path

import pytest
from scripts import aggregate_agent_metrics


def _write_ndjson(path: Path, entries: list[dict]) -> None:
    lines = [json.dumps(entry, sort_keys=True) for entry in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_build_summary_formats_sections() -> None:
    entries = [
        {
            "pr_number": 101,
            "iteration_count": 3,
            "stop_reason": "tasks-complete",
            "gate_conclusion": "success",
            "timestamp": "2025-01-01T00:00:00Z",
        },
        {
            "pr_number": 202,
            "iteration_count": 4,
            "stop_reason": "max-iterations",
            "gate_conclusion": "success",
        },
        {
            "pr_number": 101,
            "attempt_number": 1,
            "trigger_reason": "mypy",
            "fix_applied": True,
            "gate_result_after": "success",
        },
        {
            "pr_number": 101,
            "run_id": "verify-101",
            "verdict": "pass",
            "issues_created": 0,
            "acceptance_criteria_count": 3,
        },
        {
            "schema": "workflows-terminal-disposition/v1",
            "source_type": "source-issue",
            "source_id": "99",
            "pr_number": 101,
            "run_id": "verify-101",
            "disposition": "follow-up-created",
            "llm_model": "gpt-5.3-codex",
            "model_selection_reason": "default",
            "llm_cli_version": "codex-cli 0.125.0",
            "verifier_mode": "checkbox",
        },
        {
            "schema": "workflows-verifier-followup-ledger/v1",
            "metric_type": "verifier_followup_ledger",
            "pr_number": 101,
            "verification_run_id": "verify-101",
            "verdict": "concerns",
            "disposition": "follow-up",
            "followup_issue_number": 303,
            "needs_human": False,
            "chain_depth": 1,
            "followup_policy": {
                "schema": "workflows-verifier-followup-policy/v1",
                "action": "create-follow-up",
                "trigger": "verifier-concerns",
                "chain_depth": 1,
                "max_chain_depth": 2,
                "next_chain_depth": 2,
                "depth_limit_exceeded": False,
            },
        },
        {
            "schema": "workflows-codex-cli-freshness/v1",
            "package": "@openai/codex",
            "component": "agents-verifier",
            "status": " OUTDATED ",
            "pinned_version": "@openai/codex@0.125.0",
            "latest_version": "v0.127.3\n",
            "version_delta": {"major": 0, "minor": 2, "patch": 3},
            "update_targets": [
                {"path": ".github/workflows/reusable-agents-verifier.yml"},
                {"path": "tests/workflows/test_verifier_terminal_disposition.py"},
            ],
        },
    ]

    summary = aggregate_agent_metrics.build_summary(entries, errors=1)

    assert (
        "Records: 7 (keepalive 2, autofix 1, verifier 1, terminal dispositions 1, "
        "verifier follow-up ledgers 1, codex CLI freshness 1, autopilot 0, unknown 0)"
    ) in summary
    assert "Parse errors: 1" in summary
    assert "Avg iterations: 3.5" in summary
    assert "tasks-complete (1)" in summary
    assert "max-iterations (1)" in summary
    assert "Actions: n/a" in summary
    assert "Fixes applied: 100.0% (1/1)" in summary
    assert "Verdicts: pass (1)" in summary
    assert "Avg acceptance criteria: 3.0" in summary
    assert "Terminal disposition records: 1" in summary
    assert "Terminal dispositions: follow-up-created (1)" in summary
    assert "Terminal disposition sources: source-issue:99 (1)" in summary
    assert "Verifier follow-up ledger records: 1" in summary
    assert "Verifier follow-up ledger dispositions: follow-up (1)" in summary
    assert "Verifier follow-up ledger PRs: 1" in summary
    assert "Verifier follow-up issues linked: 1" in summary
    assert "Verifier follow-up needs-human records: 0" in summary
    assert "Verifier follow-up avg chain depth: 1.0" in summary
    assert "Verifier follow-up max chain depth: 1" in summary
    assert "Verifier follow-up policy records: 1" in summary
    assert "Verifier follow-up policy actions: create-follow-up (1)" in summary
    assert "Verifier follow-up policy triggers: verifier-concerns (1)" in summary
    assert "Verifier follow-up depth-limit records: 0" in summary
    assert "Verifier models: gpt-5.3-codex (1)" in summary
    assert "Verifier CLI versions: codex-cli 0.125.0 (1)" in summary
    assert "Unsupported verifier models: n/a" in summary
    assert "Unsupported model dispositions: n/a" in summary
    assert "Missing verifier model metadata: n/a" in summary
    assert "Legacy missing verifier model metadata: n/a" in summary
    assert "Model selection reasons: default (1)" in summary
    assert "Verifier modes: checkbox (1)" in summary
    assert "Codex CLI Freshness" in summary
    assert "Statuses: outdated (1)" in summary
    assert "Pinned versions: 0.125.0 (1)" in summary
    assert "Latest versions: 0.127.3 (1)" in summary
    assert "Outdated records: 1" in summary
    assert "Max version delta: major 0, minor 2, patch 3" in summary

    contract = aggregate_agent_metrics.build_summary_contract(entries, [])
    verifier_contract = contract["summaries"]["verifier"]
    assert verifier_contract["verifier_models"] == {"gpt-5.3-codex": 1}
    assert verifier_contract["verifier_cli_versions"] == {"codex-cli 0.125.0": 1}
    assert verifier_contract["model_selection_reasons"] == {"default": 1}
    assert verifier_contract["ledger_policy_actions"] == {"create-follow-up": 1}
    assert verifier_contract["ledger_policy_triggers"] == {"verifier-concerns": 1}
    assert verifier_contract["ledger_avg_chain_depth"] == 1.0
    freshness_contract = contract["summaries"]["codex_cli_freshness"]
    assert freshness_contract["statuses"] == {"outdated": 1}
    assert freshness_contract["outdated_records"] == 1
    assert freshness_contract["max_version_delta"] == {"major": 0, "minor": 2, "patch": 3}


def test_autopilot_needs_human_rate_uses_escalations_not_issue_ids() -> None:
    entries = [
        {
            "metric_type": "escalation",
            "escalation_reason": "needs-human-review",
        },
        {
            "metric_type": "escalation",
            "escalation_reason": "rate-limit",
        },
    ]

    summary = aggregate_agent_metrics.build_summary(entries, errors=0)

    assert "Issues: 0" in summary
    assert "Escalations: 2" in summary
    assert "Needs-human escalation rate: 50.0% (1/2)" in summary


def test_main_writes_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    keepalive_path = tmp_path / "keepalive.ndjson"
    autofix_path = tmp_path / "autofix.ndjson"
    output_path = tmp_path / "summary.md"
    output_json_path = tmp_path / "summary.json"

    _write_ndjson(
        keepalive_path,
        [
            {
                "pr_number": 111,
                "iteration_count": 1,
                "stop_reason": "tasks-complete",
                "gate_conclusion": "success",
            }
        ],
    )
    _write_ndjson(
        autofix_path,
        [
            {
                "pr_number": 111,
                "attempt_number": 2,
                "trigger_reason": "pytest",
                "fix_applied": False,
                "gate_result_after": "failure",
            }
        ],
    )

    monkeypatch.setenv("METRICS_PATHS", f"{keepalive_path},{autofix_path}")
    monkeypatch.setenv("OUTPUT_PATH", str(output_path))
    monkeypatch.setenv("OUTPUT_JSON_PATH", str(output_json_path))

    exit_code = aggregate_agent_metrics.main()

    assert exit_code == 0
    assert output_path.exists()
    summary = output_path.read_text(encoding="utf-8")
    assert "Keepalive" in summary
    assert "Autofix" in summary
    summary_json = json.loads(output_json_path.read_text(encoding="utf-8"))
    assert summary_json["schema"] == "workflows-agent-metrics-summary/v1"
    assert summary_json["parse_errors"]["count"] == 0

    monkeypatch.delenv("METRICS_PATHS", raising=False)
    monkeypatch.delenv("OUTPUT_PATH", raising=False)
    monkeypatch.delenv("OUTPUT_JSON_PATH", raising=False)


def test_parse_timestamp_variants() -> None:
    epoch = aggregate_agent_metrics._parse_timestamp(0)
    assert epoch is not None
    assert epoch.tzinfo is not None
    assert aggregate_agent_metrics._parse_timestamp("") is None
    assert aggregate_agent_metrics._parse_timestamp("not-a-date") is None

    naive = aggregate_agent_metrics._parse_timestamp("2025-01-01T00:00:00")
    assert naive is not None
    assert naive.tzinfo is not None

    parsed = aggregate_agent_metrics._parse_timestamp("2025-01-01T12:30:00Z")
    assert parsed is not None
    assert parsed.isoformat().startswith("2025-01-01T12:30:00")

    assert aggregate_agent_metrics._parse_timestamp(object()) is None
    assert aggregate_agent_metrics._parse_timestamp(1e20) is None


def test_gather_metrics_files_prefers_explicit_paths(tmp_path: Path) -> None:
    explicit = [
        str(tmp_path / "a.ndjson"),
        "",
        str(tmp_path / "b.ndjson"),
    ]
    files = aggregate_agent_metrics._gather_metrics_files(explicit, str(tmp_path))
    assert [path.name for path in files] == ["a.ndjson", "b.ndjson"]


def test_gather_metrics_files_falls_back_to_dir(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    first = tmp_path / "nested" / "alpha.ndjson"
    second = tmp_path / "beta.ndjson"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")

    files = aggregate_agent_metrics._gather_metrics_files([], str(tmp_path))
    assert [path.name for path in files] == ["beta.ndjson", "alpha.ndjson"]


def test_gather_metrics_files_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    files = aggregate_agent_metrics._gather_metrics_files([], str(missing))
    assert files == []


def test_read_ndjson_counts_parse_errors(tmp_path: Path) -> None:
    path = tmp_path / "metrics.ndjson"
    path.write_text(
        "\n".join(
            [
                '{"key": "value"}',
                '{"key": "value"',
                "[1, 2, 3]",
                "   ",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    entries, errors = aggregate_agent_metrics._read_ndjson([path])

    assert len(entries) == 1
    assert entries[0]["key"] == "value"
    assert entries[0]["metric_path"] == path.as_posix()
    assert len(errors) == 2
    assert [error.reason for error in errors] == ["invalid-json", "non-object-json"]
    assert errors[0].line == 2


def test_read_ndjson_does_not_buffer_valid_ndjson_for_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "metrics.ndjson"
    path.write_text('{"key": "value"}\n{"other": true}\n', encoding="utf-8")

    calls = 0
    original_loads = aggregate_agent_metrics.json.loads

    def counting_loads(raw: str) -> object:
        nonlocal calls
        calls += 1
        return original_loads(raw)

    monkeypatch.setattr(aggregate_agent_metrics.json, "loads", counting_loads)

    entries, errors = aggregate_agent_metrics._read_ndjson([path])

    assert len(entries) == 2
    assert errors == []
    assert calls == 2


def test_read_ndjson_streams_file_lines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "metrics.ndjson"
    path.write_text('{"key": "value"}\n', encoding="utf-8")

    def fail_read_text(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("read_text should not be used for metrics NDJSON")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    entries, errors = aggregate_agent_metrics._read_ndjson([path])

    assert len(entries) == 1
    assert entries[0]["key"] == "value"
    assert errors == []


def test_read_ndjson_counts_unreadable_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ndjson"
    entries, errors = aggregate_agent_metrics._read_ndjson([missing])
    assert entries == []
    assert len(errors) == 1
    assert errors[0].reason == "unreadable-file"


def test_read_ndjson_attributes_parse_errors_to_artifact_family(tmp_path: Path) -> None:
    metrics_dir = (
        tmp_path / "artifacts" / "review-thread-terminal-disposition-123" / "agent-metrics"
    )
    metrics_dir.mkdir(parents=True)
    path = metrics_dir / "terminal.ndjson"
    path.write_text('{"ok": true}\n{"broken": true\n', encoding="utf-8")

    entries, errors = aggregate_agent_metrics._read_ndjson([path])

    assert len(entries) == 1
    assert entries[0]["ok"] is True
    assert entries[0]["artifact_name"] == "review-thread-terminal-disposition-123"
    assert entries[0]["artifact_family"] == "review-thread-terminal-disposition"
    assert entries[0]["metric_artifact"] == "review-thread-terminal-disposition-123"
    assert entries[0]["metric_artifact_family"] == "review-thread-terminal-disposition"
    assert len(errors) == 1
    assert errors[0].artifact == "review-thread-terminal-disposition-123"
    assert errors[0].artifact_family == "review-thread-terminal-disposition"
    assert errors[0].line == 2

    summary = aggregate_agent_metrics.build_summary(entries, len(errors), errors)
    assert "## Parse Error Details" in summary
    assert "By artifact family: review-thread-terminal-disposition (1)" in summary
    assert "review-thread-terminal-disposition-123" in summary

    contract = aggregate_agent_metrics.build_summary_contract(entries, errors)
    assert contract["parse_errors"]["count"] == 1
    assert contract["parse_errors"]["by_artifact_family"] == {
        "review-thread-terminal-disposition": 1
    }
    assert contract["metric_sources"]["by_artifact_family"] == {
        "review-thread-terminal-disposition": 1
    }
    assert contract["parse_errors"]["details"][0]["reason"] == "invalid-json"
    assert contract["parse_errors"]["details_truncated"] is False
    assert contract["parse_errors"]["omitted_count"] == 0


def test_parse_error_details_escape_markdown_table_cells() -> None:
    details = [
        aggregate_agent_metrics.ParseErrorDetail(
            path="artifact|path\nmetrics.ndjson",
            artifact="artifact|name",
            artifact_family="family\nname",
            line=1,
            reason="invalid|json\npayload",
        )
    ]

    lines = aggregate_agent_metrics._format_parse_error_details(details)

    assert (
        "| family name | artifact\\|name | artifact\\|path metrics.ndjson | 1 | invalid\\|json payload | 1 |"
        in lines
    )


def test_parse_error_contract_truncates_details() -> None:
    details = [
        aggregate_agent_metrics.ParseErrorDetail(
            path=f"metrics-{index}.ndjson",
            artifact="artifact",
            artifact_family="artifact",
            line=index,
            reason="invalid-json",
        )
        for index in range(aggregate_agent_metrics._MAX_PARSE_ERROR_ROWS + 2)
    ]

    contract = aggregate_agent_metrics._parse_error_contract(details)

    assert contract["count"] == aggregate_agent_metrics._MAX_PARSE_ERROR_ROWS + 2
    assert contract["stored_detail_count"] == aggregate_agent_metrics._MAX_PARSE_ERROR_ROWS + 2
    assert len(contract["details"]) == aggregate_agent_metrics._MAX_PARSE_ERROR_ROWS
    assert contract["details_truncated"] is True
    assert contract["omitted_count"] == 2


def test_parse_error_contract_counts_compacted_details() -> None:
    details = [
        aggregate_agent_metrics.ParseErrorDetail(
            path="metrics.ndjson",
            artifact="artifact",
            artifact_family="artifact",
            line=1,
            reason="invalid-json",
            count=3,
        ),
        aggregate_agent_metrics.ParseErrorDetail(
            path="metrics.ndjson",
            artifact="artifact",
            artifact_family="artifact",
            line=None,
            reason="invalid-json",
            count=7,
        ),
    ]

    contract = aggregate_agent_metrics._parse_error_contract(details)
    lines = aggregate_agent_metrics._format_parse_error_details(details)

    assert contract["count"] == 10
    assert contract["stored_detail_count"] == 2
    assert contract["by_artifact_family"] == {"artifact": 10}
    assert contract["by_reason"] == {"invalid-json": 10}
    assert contract["details_truncated"] is False
    assert contract["omitted_count"] == 0
    assert "| artifact | artifact | metrics.ndjson | n/a | invalid-json | 7 |" in lines


def test_append_parse_error_detail_compacts_at_storage_limit() -> None:
    details = [
        aggregate_agent_metrics.ParseErrorDetail(
            path="metrics.ndjson",
            artifact="artifact",
            artifact_family="artifact",
            line=index,
            reason="invalid-json",
        )
        for index in range(aggregate_agent_metrics._MAX_STORED_PARSE_ERROR_DETAILS)
    ]

    aggregate_agent_metrics._append_parse_error_detail(
        details,
        aggregate_agent_metrics.ParseErrorDetail(
            path="metrics.ndjson",
            artifact="artifact",
            artifact_family="artifact",
            line=999,
            reason="invalid-json",
        ),
    )

    assert len(details) == aggregate_agent_metrics._MAX_STORED_PARSE_ERROR_DETAILS
    assert sum(detail.count for detail in details) == (
        aggregate_agent_metrics._MAX_STORED_PARSE_ERROR_DETAILS + 1
    )
    assert details[0].line is None
    assert details[0].count == 2


def test_append_parse_error_detail_caps_stored_details() -> None:
    details: list[aggregate_agent_metrics.ParseErrorDetail] = []

    for index in range(5):
        aggregate_agent_metrics._append_parse_error_detail(
            details,
            aggregate_agent_metrics.ParseErrorDetail(
                path=f"metrics-{index}.ndjson",
                artifact=f"artifact-{index}",
                artifact_family=f"family-{index}",
                line=index + 1,
                reason="invalid-json",
            ),
            detail_limit=3,
        )

    contract = aggregate_agent_metrics._parse_error_contract(details)

    assert len(details) == 3
    assert contract["count"] == 5
    assert contract["stored_detail_count"] == 3
    assert contract["by_reason"]["additional-parse-errors-after-detail-limit"] == 3
    assert details[-1].path == "__multiple__"
    assert details[-1].line is None


def test_parse_error_detail_overflow_does_not_use_incoming_identity() -> None:
    details = [
        aggregate_agent_metrics.ParseErrorDetail(
            path="first.ndjson",
            artifact="first-artifact",
            artifact_family="first-family",
            line=1,
            reason="invalid-json",
        ),
        aggregate_agent_metrics.ParseErrorDetail(
            path="second.ndjson",
            artifact="second-artifact",
            artifact_family="second-family",
            line=2,
            reason="non-object-json",
        ),
    ]

    aggregate_agent_metrics._append_parse_error_detail(
        details,
        aggregate_agent_metrics.ParseErrorDetail(
            path="third.ndjson",
            artifact="third-artifact",
            artifact_family="third-family",
            line=3,
            reason="unreadable-file",
        ),
        detail_limit=2,
    )

    contract = aggregate_agent_metrics._parse_error_contract(details)

    assert len(details) == 2
    assert details[0].path == "first.ndjson"
    assert details[-1].path == "__multiple__"
    assert details[-1].artifact == "__multiple__"
    assert details[-1].artifact_family == "__multiple__"
    assert details[-1].reason == "additional-parse-errors-after-detail-limit"
    assert contract["count"] == 3
    assert contract["by_reason"] == {
        "additional-parse-errors-after-detail-limit": 2,
        "invalid-json": 1,
    }
    assert "third-artifact" not in contract["by_artifact"]


def test_read_ndjson_preserves_artifact_name_with_id_extraction_dir(tmp_path: Path) -> None:
    metrics_dir = (
        tmp_path
        / "artifacts"
        / "review-thread-terminal-disposition-123"
        / "987654321"
        / "agent-metrics"
    )
    metrics_dir.mkdir(parents=True)
    path = metrics_dir / "terminal.ndjson"
    path.write_text('{"schema":"workflows-terminal-disposition/v1"}\n', encoding="utf-8")

    entries, errors = aggregate_agent_metrics._read_ndjson([path])

    assert errors == []
    assert len(entries) == 1
    assert entries[0]["artifact_name"] == "review-thread-terminal-disposition-123"
    assert entries[0]["artifact_family"] == "review-thread-terminal-disposition"
    assert entries[0]["metric_artifact"] == "review-thread-terminal-disposition-123"
    assert entries[0]["metric_artifact_family"] == "review-thread-terminal-disposition"


def test_read_ndjson_accepts_legacy_pretty_json_object(tmp_path: Path) -> None:
    metrics_dir = tmp_path / "artifacts" / "keepalive-metrics"
    metrics_dir.mkdir(parents=True)
    path = metrics_dir / "keepalive-metrics.ndjson"
    path.write_text(
        json.dumps(
            {
                "schema": "workflows-keepalive-metrics/v1",
                "pr_number": 1872,
                "iteration_count": 0,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    entries, errors = aggregate_agent_metrics._read_ndjson([path])

    assert errors == []
    assert len(entries) == 1
    assert entries[0]["schema"] == "workflows-keepalive-metrics/v1"
    assert entries[0]["pr_number"] == 1872
    assert entries[0]["iteration_count"] == 0
    assert entries[0]["artifact_name"] == "keepalive-metrics"


def test_read_ndjson_bounds_legacy_json_fallback_buffer(tmp_path: Path) -> None:
    path = tmp_path / "large-invalid.ndjson"
    path.write_text(
        "\n".join(["{"] * (aggregate_agent_metrics._MAX_LEGACY_JSON_FALLBACK_LINES + 1)) + "\n",
        encoding="utf-8",
    )

    entries, errors = aggregate_agent_metrics._read_ndjson([path])

    assert entries == []
    assert len(errors) <= aggregate_agent_metrics._MAX_STORED_PARSE_ERROR_DETAILS
    assert sum(error.count for error in errors) == (
        aggregate_agent_metrics._MAX_LEGACY_JSON_FALLBACK_LINES + 2
    )
    compacted_invalid_json = next(
        error for error in errors if error.reason == "invalid-json" and error.line is None
    )
    retained_invalid_count = sum(error.count for error in errors if error.reason == "invalid-json")
    assert retained_invalid_count == aggregate_agent_metrics._MAX_LEGACY_JSON_FALLBACK_LINES + 1
    assert compacted_invalid_json.count >= (
        aggregate_agent_metrics._MAX_LEGACY_JSON_FALLBACK_LINES
        + 1
        - aggregate_agent_metrics._MAX_STORED_PARSE_ERROR_DETAILS
    )
    assert errors[-1].line is None
    assert errors[-1].reason == "legacy-json-fallback-buffer-limit"


def test_classify_entry_prefers_explicit_type() -> None:
    assert aggregate_agent_metrics._classify_entry({"metric_type": "Keepalive"}) == "keepalive"
    assert aggregate_agent_metrics._classify_entry({"workflow": "autofix"}) == "autofix"
    assert aggregate_agent_metrics._classify_entry({"type": "Verifier"}) == "verifier"
    assert (
        aggregate_agent_metrics._classify_entry({"schema": "workflows-terminal-disposition/v1"})
        == "terminal_disposition"
    )
    assert (
        aggregate_agent_metrics._classify_entry({"schema": "workflows-verifier-followup-ledger/v1"})
        == "verifier_followup_ledger"
    )
    assert aggregate_agent_metrics._classify_entry({"iteration_count": 1}) == "keepalive"
    assert aggregate_agent_metrics._classify_entry({"trigger_reason": "pytest"}) == "autofix"
    assert aggregate_agent_metrics._classify_entry({"verdict": "pass"}) == "verifier"
    assert aggregate_agent_metrics._classify_entry({"other": "value"}) == "unknown"


def test_safe_number_helpers() -> None:
    assert aggregate_agent_metrics._safe_int("3") == 3
    assert aggregate_agent_metrics._safe_int("bad") is None
    assert aggregate_agent_metrics._safe_float("1.5") == 1.5
    assert aggregate_agent_metrics._safe_float(None) is None
    assert aggregate_agent_metrics._safe_float(object()) is None


def test_summary_helpers_cover_branches() -> None:
    keepalive = aggregate_agent_metrics._summarise_keepalive(
        [
            {
                "stop_reason": "tasks-complete",
                "gate_result": "failure",
                "iteration": "2",
                "pr": "101",
            },
            {
                "stop_reason": None,
                "gate_conclusion": "success",
                "iteration_count": 1,
                "pr_number": 101,
            },
        ]
    )
    assert keepalive["tasks_complete"] == 1
    assert keepalive["stop_reasons"]["tasks-complete"] == 1
    assert keepalive["actions"] == Counter()
    assert keepalive["gate_results"]["failure"] == 1
    assert keepalive["gate_results"]["success"] == 1

    autofix = aggregate_agent_metrics._summarise_autofix(
        [
            {
                "trigger_reason": "pytest",
                "gate_result": "success",
                "pr": 202,
                "fix_applied": "1",
            }
        ]
    )
    assert autofix["fixes_applied"] == 1
    assert autofix["triggers"]["pytest"] == 1
    assert autofix["gate_results"]["success"] == 1

    verifier = aggregate_agent_metrics._summarise_verifier(
        [
            {
                "verdict": "fail",
                "issues_created": "2",
                "acceptance_criteria_count": "3",
                "pr": 303,
            }
        ]
    )
    assert verifier["issues_created"] == 2
    assert verifier["verdicts"]["fail"] == 1
    assert verifier["avg_acceptance"] == 3
    assert verifier["runs"] == 1

    verifier_with_terminal = aggregate_agent_metrics._summarise_verifier(
        [
            {
                "verdict": "pass",
                "run_id": "123",
                "pr_number": 303,
            },
            {
                "schema": "workflows-terminal-disposition/v1",
                "run_id": "123",
                "pr_number": 303,
                "disposition": "follow-up-created",
                "llm_model": "gpt-5.3-codex",
                "model_selection_reason": "fallback-unsupported-chatgpt-codex-model",
                "llm_cli_version": "codex-cli 0.125.0",
                "verifier_mode": " Checkbox ",
            },
            {
                "schema": "workflows-terminal-disposition/v1",
                "run_id": "124",
                "pr_number": 304,
                "disposition": "verified-pass",
                "llm_model": "gpt-5.4",
                "codex_cli_version": "Codex CLI v0.125.0",
                "verifier_mode": "checkbox",
            },
        ]
    )
    assert verifier_with_terminal["runs"] == 1
    assert verifier_with_terminal["terminal_records"] == 2
    assert verifier_with_terminal["verifier_models"]["gpt-5.3-codex"] == 1
    assert verifier_with_terminal["verifier_models"]["gpt-5.4"] == 1
    assert verifier_with_terminal["verifier_cli_versions"]["codex-cli 0.125.0"] == 2
    assert verifier_with_terminal["unsupported_verifier_models"] == Counter()
    assert verifier_with_terminal["missing_verifier_model_metadata"] == Counter()
    assert (
        verifier_with_terminal["model_selection_reasons"][
            "fallback-unsupported-chatgpt-codex-model"
        ]
        == 1
    )
    assert verifier_with_terminal["verifier_modes"]["checkbox"] == 2


def test_summary_contract_exposes_runtime_verifier_model_fallback() -> None:
    entries = [
        {
            "schema": "workflows-terminal-disposition/v1",
            "artifact_family": "verifier-terminal-disposition",
            "run_id": "24959093731",
            "pr_number": 1899,
            "disposition": "verified-pass",
            "llm_model": "gpt-5.4",
            "model_selection_reason": "runtime-fallback-model-unavailable",
            "llm_cli_version": "codex-cli 0.125.0",
            "verifier_mode": "checkbox",
            "timestamp": "2026-04-26T14:58:00Z",
        }
    ]

    contract = aggregate_agent_metrics.build_summary_contract(entries, [])
    verifier = contract["summaries"]["verifier"]

    assert contract["record_buckets"] == {"terminal_disposition": 1}
    assert verifier["terminal_records"] == 1
    assert verifier["verifier_models"] == {"gpt-5.4": 1}
    assert verifier["verifier_cli_versions"] == {"codex-cli 0.125.0": 1}
    assert verifier["model_selection_reasons"] == {"runtime-fallback-model-unavailable": 1}
    assert verifier["verifier_modes"] == {"checkbox": 1}


def test_verifier_summary_counts_unsupported_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNSUPPORTED_VERIFIER_MODELS", "gpt-5.2-codex,custom-bad")

    verifier = aggregate_agent_metrics._summarise_verifier(
        [
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "run_id": "24948023778",
                "pr_number": 1872,
                "disposition": "verifier-error",
                "llm_model": "GPT-5.2-Codex",
            },
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "run_id": "24948023778",
                "pr_number": 1872,
                "disposition": "verifier-error",
                "llm_model": " gpt-5.2-codex ",
            },
            {
                "schema": "workflows-terminal-disposition/v1",
                "run_id": "24948023779",
                "pr_number": 1873,
                "disposition": "verified-pass",
                "llm_model": "GPT-5.3-Codex",
            },
        ]
    )

    assert verifier["verifier_models"]["gpt-5.2-codex"] == 2
    assert verifier["verifier_models"]["gpt-5.3-codex"] == 1
    assert verifier["unsupported_verifier_models"]["gpt-5.2-codex"] == 2
    assert verifier["unsupported_model_dispositions"]["verifier-error"] == 2

    summary = aggregate_agent_metrics.build_summary(
        [
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "run_id": "24948023778",
                "pr_number": 1872,
                "disposition": "verifier-error",
                "llm_model": "gpt-5.2-codex",
            }
        ],
        errors=0,
    )

    assert "Unsupported verifier models: gpt-5.2-codex (1)" in summary
    assert "Unsupported model dispositions: verifier-error (1)" in summary


def test_verifier_summary_accepts_terminal_disposition_unsupported_model_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UNSUPPORTED_VERIFIER_MODELS", raising=False)
    monkeypatch.setenv("TERMINAL_DISPOSITION_UNSUPPORTED_CODEX_MODELS", "alias-bad")

    verifier = aggregate_agent_metrics._summarise_verifier(
        [
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "run_id": "24948023778",
                "pr_number": 1872,
                "disposition": "verifier-error",
                "llm_model": "Alias-Bad",
            },
        ]
    )

    assert verifier["unsupported_verifier_models"]["alias-bad"] == 1


def test_verifier_summary_prefers_specific_unsupported_model_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNSUPPORTED_VERIFIER_MODELS", "primary-bad")
    monkeypatch.setenv("TERMINAL_DISPOSITION_UNSUPPORTED_CODEX_MODELS", "alias-bad")

    verifier = aggregate_agent_metrics._summarise_verifier(
        [
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "run_id": "24948023778",
                "pr_number": 1872,
                "disposition": "verifier-error",
                "llm_model": "primary-bad",
            },
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "run_id": "24948023779",
                "pr_number": 1873,
                "disposition": "verifier-error",
                "llm_model": "alias-bad",
            },
        ]
    )

    assert verifier["unsupported_verifier_models"]["primary-bad"] == 1
    assert verifier["unsupported_verifier_models"]["alias-bad"] == 0


def test_verifier_summary_counts_missing_model_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TERMINAL_DISPOSITION_VERIFIER_MODEL_METADATA_REQUIRED_AFTER",
        "2026-04-26T04:25:00Z",
    )
    summary = aggregate_agent_metrics.build_summary(
        [
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "run_id": "24948023778",
                "pr_number": 1872,
                "disposition": "verifier-error",
                "verifier_mode": "compare",
            },
            {
                "schema": "workflows-terminal-disposition/v1",
                "run_id": "24948023779",
                "pr_number": 1873,
                "disposition": "verified-pass",
                "verifier_mode": "evaluate",
            },
        ],
        errors=0,
    )

    assert "Missing verifier model metadata: verifier-error (1)" in summary


def test_verifier_summary_ignores_missing_model_metadata_for_unknown_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TERMINAL_DISPOSITION_VERIFIER_MODEL_METADATA_REQUIRED_AFTER",
        "2026-04-26T04:25:00Z",
    )

    verifier = aggregate_agent_metrics._summarise_verifier(
        [
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "run_id": "24948023779",
                "pr_number": 1874,
                "disposition": "verifier-error",
            },
        ]
    )

    assert verifier["missing_verifier_model_metadata"] == Counter()


def test_verifier_summary_counts_missing_model_metadata_for_non_evaluate_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TERMINAL_DISPOSITION_VERIFIER_MODEL_METADATA_REQUIRED_AFTER",
        "2026-04-26T04:25:00Z",
    )

    verifier = aggregate_agent_metrics._summarise_verifier(
        [
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "run_id": "24948023779",
                "pr_number": 1874,
                "disposition": "verifier-error",
                "verifier_mode": "compare",
            },
        ]
    )

    assert verifier["missing_verifier_model_metadata"]["verifier-error"] == 1


def test_verifier_summary_suppresses_pre_contract_missing_model_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TERMINAL_DISPOSITION_VERIFIER_MODEL_METADATA_REQUIRED_AFTER",
        "2026-04-26T04:25:00Z",
    )
    summary = aggregate_agent_metrics.build_summary(
        [
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "timestamp": "2026-04-26T04:18:01Z",
                "run_id": "24948023778",
                "pr_number": 1872,
                "disposition": "verifier-error",
                "verifier_mode": "compare",
            },
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "timestamp": "2026-04-26T06:00:00Z",
                "run_id": "24950000000",
                "pr_number": 1877,
                "disposition": "needs-human",
                "verifier_mode": "compare",
            },
        ],
        errors=0,
    )

    assert "Missing verifier model metadata: needs-human (1)" in summary
    assert "Legacy missing verifier model metadata: verifier-error (1)" in summary


def test_verifier_summary_ignores_review_thread_terminal_model_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TERMINAL_DISPOSITION_VERIFIER_MODEL_METADATA_REQUIRED_AFTER",
        "2026-04-26T04:25:00Z",
    )
    summary = aggregate_agent_metrics.build_summary(
        [
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "review-thread-terminal-disposition",
                "source_type": "review-thread",
                "source_id": "1875",
                "pr_number": 1875,
                "disposition": "wrapper-skipped",
            },
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "source_type": "pull-request",
                "source_id": "1872",
                "pr_number": 1872,
                "disposition": "verifier-error",
                "verifier_mode": "compare",
            },
        ],
        errors=0,
    )

    assert "Terminal disposition records: 2" in summary
    assert "verifier-error (1)" in summary
    assert "wrapper-skipped (1)" in summary
    assert "Missing verifier model metadata: verifier-error (1)" in summary
    assert "wrapper-skipped" not in summary.split("Missing verifier model metadata: ", 1)[1]


def test_verifier_summary_does_not_require_model_metadata_by_default() -> None:
    summary = aggregate_agent_metrics.build_summary(
        [
            {
                "schema": "workflows-terminal-disposition/v1",
                "artifact_family": "verifier-terminal-disposition",
                "run_id": "24948023778",
                "pr_number": 1872,
                "disposition": "verifier-error",
                "verifier_mode": "compare",
            }
        ],
        errors=0,
    )

    assert "Missing verifier model metadata: n/a" in summary


def test_format_helpers_and_summary_range() -> None:
    assert aggregate_agent_metrics._format_counter(Counter()) == "n/a"
    assert aggregate_agent_metrics._format_rate(1, 0) == "n/a"

    entries = [
        {
            "metric_type": "keepalive",
            "timestamp": "2025-01-01T00:00:00Z",
            "iteration_count": 1,
            "stop_reason": "tasks-complete",
        },
        {
            "metric_type": "unknown",
            "timestamp": "2025-01-02T00:00:00Z",
        },
    ]
    summary = aggregate_agent_metrics.build_summary(entries, errors=0)
    assert "Range: 2025-01-01T00:00:00Z to 2025-01-02T00:00:00Z" in summary


def test_main_writes_placeholder_when_no_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("METRICS_PATHS", "")
    monkeypatch.setenv("METRICS_DIR", str(tmp_path / "missing"))
    output_path = tmp_path / "summary.md"
    output_json_path = tmp_path / "summary.json"
    monkeypatch.setenv("OUTPUT_PATH", str(output_path))
    monkeypatch.setenv("OUTPUT_JSON_PATH", str(output_json_path))

    exit_code = aggregate_agent_metrics.main()

    assert exit_code == 0
    assert output_path.read_text(encoding="utf-8") == "No metrics files found to aggregate.\n"
    summary_json = json.loads(output_json_path.read_text(encoding="utf-8"))
    assert summary_json["parse_errors"]["count"] == 0


def test_main_includes_artifact_download_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metrics_dir = tmp_path / "artifacts" / "keepalive-metrics" / "42" / "agent-metrics"
    metrics_dir.mkdir(parents=True)
    _write_ndjson(
        metrics_dir / "keepalive.ndjson",
        [
            {
                "metric_type": "keepalive",
                "timestamp": "2026-04-26T01:00:00Z",
                "iteration_count": 1,
            }
        ],
    )
    manifest_path = tmp_path / "download-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "workflows-weekly-metrics-artifact-download-manifest/v1",
                "status": "warning",
                "selection": {
                    "selected_count": 2,
                    "selected_family_counts": {"keepalive-metrics": 1},
                    "priority_family_statuses": [
                        {
                            "family": "codex-cli-freshness",
                            "status": "selected",
                            "candidate_count": 1,
                            "selected_count": 1,
                            "selected_artifact": {
                                "id": 44,
                                "name": "codex-cli-freshness-24965031474",
                            },
                        }
                    ],
                    "latest_candidate_by_family": {
                        "codex-cli-freshness": {
                            "id": 44,
                            "name": "codex-cli-freshness-24965031474",
                        }
                    },
                },
                "stats": {
                    "selected_count": 2,
                    "download_pass_count": 1,
                    "download_failed_count": 1,
                    "unzip_pass_count": 1,
                    "unzip_failed_count": 0,
                    "unzip_skipped_count": 1,
                },
                "artifacts": [
                    {
                        "id": 42,
                        "name": "keepalive-metrics",
                        "family": "keepalive-metrics",
                        "artifact_dir": "artifacts/keepalive-metrics/42",
                        "download": {"status": "pass", "bytes": 256, "error": ""},
                        "unzip": {"status": "pass", "path": "artifacts/keepalive-metrics/42"},
                    },
                    {
                        "id": 43,
                        "name": "review-thread-terminal-disposition-1",
                        "family": "review-thread-terminal-disposition",
                        "artifact_dir": "artifacts/review-thread-terminal-disposition-1/43",
                        "download": {"status": "failed", "error": "download-command-failed"},
                        "unzip": {"status": "skipped", "error": "download-failed"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    output_json_path = tmp_path / "summary.json"

    monkeypatch.setenv("METRICS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OUTPUT_PATH", str(tmp_path / "summary.md"))
    monkeypatch.setenv("OUTPUT_JSON_PATH", str(output_json_path))
    monkeypatch.setenv("METRICS_ARTIFACT_DOWNLOAD_MANIFEST_JSON", str(manifest_path))

    exit_code = aggregate_agent_metrics.main()

    assert exit_code == 0
    summary_json = json.loads(output_json_path.read_text(encoding="utf-8"))
    downloads = summary_json["artifact_downloads"]
    assert downloads["schema"] == "workflows-weekly-metrics-artifact-download-manifest/v1"
    assert downloads["status"] == "warning"
    assert downloads["selection"]["priority_family_statuses"][0]["family"] == (
        "codex-cli-freshness"
    )
    assert downloads["selection"]["priority_family_statuses"][0]["status"] == "selected"
    assert downloads["selection"]["latest_candidate_by_family"]["codex-cli-freshness"]["id"] == 44
    assert downloads["stats"]["download_failed_count"] == 1
    assert downloads["failed_artifacts"] == [
        {
            "id": 43,
            "name": "review-thread-terminal-disposition-1",
            "family": "review-thread-terminal-disposition",
            "artifact_dir": "artifacts/review-thread-terminal-disposition-1/43",
            "download_status": "failed",
            "unzip_status": "skipped",
            "download_error": "download-command-failed",
            "unzip_error": "download-failed",
        }
    ]


def test_autopilot_metrics_summarised() -> None:
    """Auto-pilot step/cycle/escalation records appear in the summary."""
    entries = [
        {
            "metric_type": "step",
            "issue_number": 42,
            "step_name": "format",
            "duration_ms": 5000,
            "success": True,
            "failure_reason": "none",
        },
        {
            "metric_type": "step",
            "issue_number": 42,
            "step_name": "capability-check",
            "duration_ms": 3000,
            "success": True,
            "failure_reason": "none",
        },
        {
            "metric_type": "step",
            "issue_number": 42,
            "step_name": "verify",
            "duration_ms": 12000,
            "success": False,
            "failure_reason": "step-failed",
        },
        {
            "metric_type": "escalation",
            "issue_number": 99,
            "escalation_reason": "needs-human-complexity",
        },
        {
            "metric_type": "cycle",
            "issue_number": 42,
            "cycle_count": 2,
            "steps_attempted": 3,
            "steps_completed": 2,
        },
    ]

    summary = aggregate_agent_metrics.build_summary(entries, errors=0)

    assert "Auto-Pilot Pipeline" in summary
    assert "Records: 5" in summary
    assert "autopilot 5" in summary
    assert "Issues: 2" in summary
    assert "Total step executions: 3" in summary
    assert "Cycle records: 1" in summary
    assert "Cycle count distribution: 2 (1)" in summary
    assert "Cycle step completion: 66.7% (2/3)" in summary
    assert "Escalations: 1" in summary
    assert "Step Average Durations" in summary
    assert "format:" in summary
    assert "capability-check:" in summary
    assert "step-failed (1)" in summary


def test_autopilot_needs_human_rate_does_not_require_issue_denominator() -> None:
    summary = aggregate_agent_metrics.build_summary(
        [
            {
                "metric_type": "escalation",
                "escalation_reason": "needs-human-complexity",
            },
        ],
        errors=0,
    )

    assert "Needs-human escalation rate: 100.0% (1/1)" in summary


def test_keepalive_completion_uses_task_totals_and_actions() -> None:
    entries = [
        {
            "pr_number": 101,
            "iteration": 1,
            "action": "run",
            "tasks_total": 3,
            "tasks_complete": 2,
        },
        {
            "pr_number": 101,
            "iteration": 2,
            "action": "stop",
            "tasks_total": 3,
            "tasks_complete": 3,
        },
    ]

    summary = aggregate_agent_metrics.build_summary(entries, errors=0)

    assert "Actions: run (1), stop (1)" in summary
    assert "Tasks complete rate: 50.0% (1/2)" in summary


def test_summarise_autopilot_counts_cycle_records() -> None:
    summary = aggregate_agent_metrics._summarise_autopilot(
        [
            {
                "metric_type": "cycle",
                "issue_number": 101,
                "cycle_count": 1,
                "steps_attempted": 2,
                "steps_completed": 2,
            },
            {
                "metric_type": "cycle",
                "issue_number": 101,
                "cycle_count": 2,
                "steps_attempted": 3,
                "steps_completed": 1,
            },
        ]
    )

    assert summary["records"] == 2
    assert summary["issues"] == 1
    assert summary["cycle_records"] == 2
    assert summary["cycle_counts"] == Counter({"1": 1, "2": 1})
    assert summary["cycle_steps_attempted"] == 5
    assert summary["cycle_steps_completed"] == 3


def test_classify_autopilot_step_entry() -> None:
    entry = {
        "metric_type": "step",
        "step_name": "optimize",
        "duration_ms": 7000,
        "success": True,
    }
    assert aggregate_agent_metrics._classify_entry(entry) == "autopilot"


def test_classify_autopilot_escalation_entry() -> None:
    entry = {
        "escalation_reason": "needs-human",
    }
    assert aggregate_agent_metrics._classify_entry(entry) == "autopilot"
