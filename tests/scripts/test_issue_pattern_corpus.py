import json
from datetime import UTC
from pathlib import Path

import pytest
from scripts import issue_pattern_corpus as corpus


def _write_ndjson(path: Path, records: list[dict]) -> None:
    payload = "\n".join(json.dumps(record) for record in records) + "\n"
    path.write_text(payload, encoding="utf-8")


def test_build_corpus_filters_successful(tmp_path: Path) -> None:
    issues = [
        {
            "issue_number": 10,
            "pr_number": 101,
            "title": "Issue A",
            "body": "## Tasks\n- [ ] One\n## Acceptance Criteria\n- [ ] Done",
        },
        {
            "issue_number": 11,
            "pr_number": 102,
            "title": "Issue B",
            "body": "## Tasks\n- [ ] Two\n## Acceptance Criteria\n- [ ] Done",
        },
    ]
    metrics = [
        {
            "metric_type": "post-merge",
            "pr_number": 101,
            "completion_rate": 1.0,
            "human_interventions": 0,
            "tasks_total": 2,
            "iteration_count": 2,
        },
        {
            "metric_type": "post-merge",
            "pr_number": 102,
            "completion_rate": 0.5,
            "human_interventions": 0,
            "tasks_total": 2,
            "iteration_count": 3,
        },
    ]

    issues_path = tmp_path / "issues.ndjson"
    metrics_path = tmp_path / "metrics.ndjson"
    _write_ndjson(issues_path, issues)
    _write_ndjson(metrics_path, metrics)

    criteria = corpus.CorpusCriteria(
        min_completion_rate=1.0, max_human_interventions=None, min_tasks_total=None
    )
    issue_entries, _ = corpus._read_json_or_ndjson(issues_path)
    metric_entries, _ = corpus._read_json_or_ndjson(metrics_path)
    result = corpus.build_corpus(issue_entries, metric_entries, criteria)

    assert len(result["successful_issues"]) == 1
    assert result["successful_issues"][0]["issue_number"] == 10


def test_build_corpus_groups_patterns() -> None:
    issues = [
        {
            "issue_number": 20,
            "pr_number": 201,
            "title": "Issue C",
            "body": "## Tasks\n- [ ] One\n- [ ] Two\n## Acceptance Criteria\n- [ ] Done",
        },
        {
            "issue_number": 21,
            "pr_number": 202,
            "title": "Issue D",
            "body": "## Tasks\n- [ ] Three\n- [ ] Four\n## Acceptance Criteria\n- [ ] Done",
        },
    ]
    metrics = [
        {
            "metric_type": "post-merge",
            "pr_number": 201,
            "completion_rate": 1.0,
            "human_interventions": 0,
            "tasks_total": 2,
            "iteration_count": 1,
        },
        {
            "metric_type": "post-merge",
            "pr_number": 202,
            "completion_rate": 1.0,
            "human_interventions": 0,
            "tasks_total": 2,
            "iteration_count": 1,
        },
    ]

    criteria = corpus.CorpusCriteria(
        min_completion_rate=1.0, max_human_interventions=0, min_tasks_total=1
    )
    result = corpus.build_corpus(issues, metrics, criteria)

    assert len(result["successful_issues"]) == 2
    assert len(result["patterns"]) == 1
    assert result["patterns"][0]["count"] == 2


def test_safe_float_accepts_finite_numbers_and_rejects_invalid_values() -> None:
    assert corpus._safe_float(" 0.75 ") == 0.75
    assert corpus._safe_float(2) == 2.0

    for invalid in (None, "", True, "not-a-number", "nan", "inf", float("-inf"), object()):
        assert corpus._safe_float(invalid) is None


def test_safe_int_accepts_integral_values_without_lossy_coercion() -> None:
    assert corpus._safe_int("42") == 42
    assert corpus._safe_int(42.0) == 42

    for invalid in (None, "", True, False, 3.5, "3.5", float("inf"), object()):
        assert corpus._safe_int(invalid) is None


def test_parse_timestamp_normalizes_z_suffix_and_rejects_invalid_values() -> None:
    parsed = corpus._parse_timestamp("2026-08-31T10:11:12Z")

    assert parsed is not None
    assert parsed.tzinfo is UTC
    assert parsed.isoformat() == "2026-08-31T10:11:12+00:00"
    assert corpus._parse_timestamp(" ") is None
    assert corpus._parse_timestamp("not-a-time") is None
    assert corpus._parse_timestamp(123) is None


def test_read_json_document_filters_non_object_entries(tmp_path: Path) -> None:
    path = tmp_path / "issues.json"
    path.write_text(json.dumps([{"number": 1}, "bad", 3]), encoding="utf-8")

    entries, errors = corpus._read_json_or_ndjson(path)

    assert entries == [{"number": 1}]
    assert errors == 2


def test_read_json_document_accepts_one_object_and_rejects_scalar(tmp_path: Path) -> None:
    path = tmp_path / "issues.json"
    path.write_text('{"number": 2}', encoding="utf-8")
    assert corpus._read_json_or_ndjson(path) == ([{"number": 2}], 0)

    path.write_text("42", encoding="utf-8")
    assert corpus._read_json_or_ndjson(path) == ([], 1)


def test_read_ndjson_keeps_objects_and_counts_each_bad_record(tmp_path: Path) -> None:
    path = tmp_path / "issues.ndjson"
    path.write_text(
        "\n".join(['{"number": 1}', "", "not-json", "[1, 2]", '{"number": 2}']) + "\n",
        encoding="utf-8",
    )

    entries, errors = corpus._read_json_or_ndjson(path)

    assert entries == [{"number": 1}, {"number": 2}]
    assert errors == 2


def test_read_json_or_ndjson_distinguishes_empty_and_unreadable_files(tmp_path: Path) -> None:
    empty = tmp_path / "empty.ndjson"
    empty.write_text(" \n", encoding="utf-8")

    assert corpus._read_json_or_ndjson(empty) == ([], 0)
    assert corpus._read_json_or_ndjson(tmp_path / "missing.ndjson") == ([], 1)


def test_extract_pr_number_uses_aliases_and_nested_payload() -> None:
    assert corpus._extract_pr_number({"pr_number": "", "pr": "17"}) == 17
    assert corpus._extract_pr_number({"pull_request_number": 18}) == 18
    assert corpus._extract_pr_number({"pull_request": {"number": "19"}}) == 19
    assert corpus._extract_pr_number({"pull_request": "19"}) is None


def test_extract_pr_number_rejects_boolean_and_fractional_identifiers() -> None:
    assert corpus._extract_pr_number({"pr_number": True}) is None
    assert corpus._extract_pr_number({"pr_number": 101.9}) is None


def test_index_post_merge_ignores_irrelevant_records_and_keeps_newest() -> None:
    records = [
        {"metric_type": "pre-merge", "pr_number": 7, "timestamp": "2026-09-02T09:00:00Z"},
        {"metric_type": "post-merge", "timestamp": "2026-09-02T09:00:00Z"},
        {
            "metric_type": "POST-MERGE",
            "pr_number": "7",
            "timestamp": "2026-09-02T08:00:00Z",
            "iteration_count": 1,
        },
        {
            "metric_type": "post-merge",
            "pr_number": 7,
            "timestamp": "2026-09-02T10:00:00Z",
            "iteration_count": 2,
        },
    ]

    indexed = corpus._index_post_merge(records)

    assert list(indexed) == [7]
    assert indexed[7]["iteration_count"] == 2


def test_index_post_merge_replaces_untimestamped_record_only_with_valid_timestamp() -> None:
    first = {"metric_type": "post-merge", "pr_number": 8, "iteration_count": 1}
    valid = {
        "metric_type": "post-merge",
        "pr_number": 8,
        "timestamp": "2026-09-02T10:00:00Z",
        "iteration_count": 2,
    }
    invalid = {
        "metric_type": "post-merge",
        "pr_number": 8,
        "timestamp": "invalid",
        "iteration_count": 3,
    }

    assert corpus._index_post_merge([first, valid, invalid])[8]["iteration_count"] == 2
    assert corpus._index_post_merge([first, invalid])[8]["iteration_count"] == 1


def test_split_sections_and_content_flags_use_canonical_headers() -> None:
    sections = corpus._split_sections(
        "preamble ignored\n"
        "## Why\nBecause.\n"
        "## Scope\n_Not provided._\n"
        "## Tasks\n- [ ] Task\n"
        "## Acceptance Criteria\n- [x] Done\n"
        "## Implementation Notes\nUse parser.\n"
    )

    assert sections["why"] == ["Because."]
    assert sections["tasks"] == ["- [ ] Task"]
    assert sections["acceptance"] == ["- [x] Done"]
    assert corpus._section_has_content("why", sections["why"]) is True
    assert corpus._section_has_content("scope", sections["scope"]) is False
    assert corpus._section_has_content("non_goals", []) is False


def test_count_checklist_items_requires_a_canonical_checkbox_marker() -> None:
    lines = [
        "- [ ] open",
        "  - [x] done",
        "- [X] also done",
        "- [ malformed",
        "- [Documentation](https://example.invalid)",
        "- [x]missing-space",
        "- plain",
    ]

    assert corpus._count_checklist_items(lines) == 3


def test_count_checklist_items_treats_placeholder_as_empty_section() -> None:
    assert corpus._count_checklist_items([corpus.SUCCESS_PLACEHOLDERS["tasks"]]) == 0
    assert corpus._count_checklist_items([corpus.SUCCESS_PLACEHOLDERS["acceptance"]]) == 0


def test_bucket_count_pins_every_boundary() -> None:
    assert [corpus._bucket_count(value) for value in (-1, 0, 1, 2, 3, 5, 6, 10, 11)] == [
        "0",
        "0",
        "1-2",
        "1-2",
        "3-5",
        "3-5",
        "6-10",
        "6-10",
        "11+",
    ]


def test_pattern_key_uses_fixed_section_order_and_none_fallback() -> None:
    assert corpus._pattern_key(2, 6, {"implementation": True, "why": True}) == (
        "tasks=1-2|acceptance=6-10|sections=why,implementation"
    )
    assert corpus._pattern_key(0, 0, {}) == "tasks=0|acceptance=0|sections=none"


def test_success_criteria_rejects_missing_below_threshold_and_nonfinite_completion() -> None:
    criteria = corpus.CorpusCriteria(0.9, None, None)

    assert corpus._meets_success_criteria({"completion_rate": 0.9}, criteria) is True
    assert corpus._meets_success_criteria({}, criteria) is False
    assert corpus._meets_success_criteria({"completion_rate": 0.89}, criteria) is False
    assert corpus._meets_success_criteria({"completion_rate": "nan"}, criteria) is False


def test_success_criteria_enforces_optional_filters_in_both_directions() -> None:
    criteria = corpus.CorpusCriteria(1.0, max_human_interventions=1, min_tasks_total=3)
    passing = {"completion_rate": "1.0", "human_interventions": "1", "tasks_total": "3"}

    assert corpus._meets_success_criteria(passing, criteria) is True
    assert corpus._meets_success_criteria({**passing, "human_interventions": 2}, criteria) is False
    assert (
        corpus._meets_success_criteria({**passing, "human_interventions": None}, criteria) is False
    )
    assert corpus._meets_success_criteria({**passing, "tasks_total": 2}, criteria) is False
    assert corpus._meets_success_criteria({**passing, "tasks_total": None}, criteria) is False


def test_build_issue_pattern_reads_aliases_and_optional_formatted_body() -> None:
    issue = {
        "number": 30,
        "pull_request": {"number": 300},
        "issue_title": "Aliased title",
        "issue_body": (
            "## Why\nNeeded\n## Scope\nParser\n## Non-Goals\nNo network\n"
            "## Tasks\n- [ ] One\n- [x] Two\n"
            "## Acceptance Criteria\n- [ ] Done\n"
            "## Implementation Notes\nPure logic"
        ),
    }
    metrics = {"completion_rate": 1.0, "iteration_count": 4, "human_interventions": 0}

    pattern = corpus._build_issue_pattern(issue, metrics, include_formatted=True)

    assert pattern["issue_number"] == 30
    assert pattern["pr_number"] == 300
    assert pattern["title"] == "Aliased title"
    assert pattern["task_count"] == 2
    assert pattern["acceptance_count"] == 1
    assert pattern["sections"] == {
        "why": True,
        "scope": True,
        "non_goals": True,
        "implementation": True,
    }
    assert pattern["completion_rate"] == 1.0
    assert pattern["iteration_count"] == 4
    assert "formatted_body" in pattern
    assert "## Tasks\n- [ ] One\n- [x] Two" in pattern["formatted_body"]


def test_build_issue_pattern_preserves_sections_after_user_details() -> None:
    issue = {
        "issue_number": 31,
        "pr_number": 301,
        "body": (
            "## Why\nNeeded.\n\n"
            "<details>\n<summary>Supporting evidence</summary>\nExtra context\n</details>\n\n"
            "## Scope\nParser only.\n\n"
            "## Tasks\n- [ ] Preserve task counts\n\n"
            "## Acceptance Criteria\n- [ ] Count one task"
        ),
    }

    pattern = corpus._build_issue_pattern(issue, {"completion_rate": 1.0}, include_formatted=True)

    assert pattern["task_count"] == 1
    assert pattern["acceptance_count"] == 1
    assert pattern["sections"]["scope"] is True
    assert "<summary>Supporting evidence</summary>" in pattern["formatted_body"]


def test_build_issue_pattern_omits_formatted_body_by_default() -> None:
    pattern = corpus._build_issue_pattern(
        {"issue_number": 31, "pr_number": 301, "body": "## Scope\nSmall"},
        {"completion_rate": 1.0},
        include_formatted=False,
    )

    assert "formatted_body" not in pattern


def test_build_corpus_does_not_join_fractional_pr_to_integer_metrics() -> None:
    result = corpus.build_corpus(
        [{"issue_number": 40, "pr_number": 400.9, "body": "## Tasks\n- [ ] Wrong join"}],
        [{"metric_type": "post-merge", "pr_number": 400, "completion_rate": 1.0}],
        corpus.CorpusCriteria(1.0, None, None),
    )

    assert result["successful_issues"] == []
    assert result["patterns"] == []


def test_build_corpus_sorts_groups_and_computes_averages() -> None:
    issues = [
        {
            "issue_number": 50,
            "pr_number": 501,
            "body": "## Tasks\n- [ ] One\n## Acceptance Criteria\n- [ ] A",
        },
        {
            "issue_number": 51,
            "pr_number": 502,
            "body": "## Tasks\n- [ ] Two\n- [ ] Three\n## Acceptance Criteria\n- [ ] B",
        },
        {
            "issue_number": 52,
            "pr_number": 503,
            "body": (
                "## Tasks\n- [ ] One\n- [ ] Two\n- [ ] Three\n"
                "## Acceptance Criteria\n- [ ] A\n- [ ] B\n- [ ] C"
            ),
        },
    ]
    metrics = [
        {"metric_type": "post-merge", "pr_number": number, "completion_rate": 1.0}
        for number in (501, 502, 503)
    ]

    result = corpus.build_corpus(issues, metrics, corpus.CorpusCriteria(1.0, None, None))

    assert [group["count"] for group in result["patterns"]] == [2, 1]
    assert result["patterns"][0]["issue_numbers"] == [50, 51]
    assert result["patterns"][0]["avg_task_count"] == 1.5
    assert result["patterns"][0]["avg_acceptance_count"] == 1.0
    assert result["criteria"] == {
        "min_completion_rate": 1.0,
        "max_human_interventions": None,
        "min_tasks_total": None,
    }
    assert corpus._parse_timestamp(result["generated_at"]) is not None


def test_main_writes_nested_output_and_includes_formatted_body(tmp_path: Path) -> None:
    issues_path = tmp_path / "issues.json"
    metrics_path = tmp_path / "metrics.ndjson"
    output_path = tmp_path / "nested" / "corpus.json"
    issues_path.write_text(
        json.dumps(
            {
                "issue_number": 60,
                "pr_number": 600,
                "body": "## Tasks\n- [ ] One\n## Acceptance Criteria\n- [ ] Done",
            }
        ),
        encoding="utf-8",
    )
    _write_ndjson(
        metrics_path,
        [
            {
                "metric_type": "post-merge",
                "pr_number": 600,
                "completion_rate": 1.0,
                "human_interventions": 0,
                "tasks_total": 1,
            }
        ],
    )

    exit_code = corpus.main(
        [
            "--issues-path",
            str(issues_path),
            "--metrics-path",
            str(metrics_path),
            "--output",
            str(output_path),
            "--max-human-interventions",
            "0",
            "--min-tasks-total",
            "1",
            "--include-formatted-body",
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["successful_issues"][0]["issue_number"] == 60
    assert "formatted_body" in payload["successful_issues"][0]


def test_main_reports_parse_errors_after_writing_valid_records(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    issues_path = tmp_path / "issues.ndjson"
    metrics_path = tmp_path / "metrics.ndjson"
    output_path = tmp_path / "corpus.json"
    issues_path.write_text(
        '{"issue_number": 70, "pr_number": 700, "body": "## Tasks\\n- [ ] One"}\n' "not-json\n",
        encoding="utf-8",
    )
    _write_ndjson(
        metrics_path,
        [{"metric_type": "post-merge", "pr_number": 700, "completion_rate": 1.0}],
    )

    exit_code = corpus.main(
        [
            "--issues-path",
            str(issues_path),
            "--metrics-path",
            str(metrics_path),
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert captured.err.strip() == "issue_pattern_corpus: parse errors (issues=1, metrics=0)"
    assert [entry["issue_number"] for entry in payload["successful_issues"]] == [70]
