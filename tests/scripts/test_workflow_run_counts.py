import json
from datetime import datetime
from pathlib import Path

import pytest
from scripts import workflow_run_counts


def _fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / "workflow_runs" / name


def _write_snapshot(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_runs_from_dict() -> None:
    runs = workflow_run_counts.load_runs(_fixture_path("before.json"))
    assert isinstance(runs, list)
    assert {run.get("id") for run in runs} == {1, 2, 3, 4, 5}


def test_load_runs_rejects_invalid_json(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="valid JSON"):
        workflow_run_counts.load_runs(bad_path)


@pytest.mark.parametrize(
    ("run", "expected"),
    [
        ({"workflow": {"name": " Nested Workflow "}}, "Nested Workflow"),
        ({"workflow": {"path": " .github/workflows/nested.yml "}}, ".github/workflows/nested.yml"),
        ({"name": " Top-Level Name "}, "Top-Level Name"),
        ({"workflow_name": " Legacy Field "}, "Legacy Field"),
        ({"path": " .github/workflows/path-only.yml "}, ".github/workflows/path-only.yml"),
        ({"workflow_id": 123456}, "workflow:123456"),
        ({"id": 999}, "unknown"),
    ],
)
def test_workflow_name_fallbacks(run: dict[str, object], expected: str) -> None:
    assert workflow_run_counts._workflow_name(run) == expected


def test_build_counts_filters_workflows() -> None:
    runs = workflow_run_counts.load_runs(_fixture_path("before.json"))
    counts = workflow_run_counts.build_counts(runs, workflow_filters=["Gate"])
    assert counts == {"Gate": 2}


def test_compare_counts_reports_delta() -> None:
    before = workflow_run_counts.build_counts(
        workflow_run_counts.load_runs(_fixture_path("before.json"))
    )
    after = workflow_run_counts.build_counts(
        workflow_run_counts.load_runs(_fixture_path("after.json"))
    )
    comparison = workflow_run_counts.compare_counts(before, after)
    by_name = {entry.name: entry for entry in comparison}
    assert by_name["Gate"].before == 2
    assert by_name["Gate"].after == 1
    assert by_name["Gate"].delta == -1
    assert by_name["Gate"].pct_change == "-50.0%"


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (0, 3, "new"),
        (0, 0, "0.0%"),
    ],
)
def test_workflow_count_pct_change_zero_before_cases(
    before: int, after: int, expected: str
) -> None:
    assert workflow_run_counts.WorkflowCount("Example", before, after).pct_change == expected


def test_table_format_includes_total() -> None:
    before = {"Gate": 2, "Agent PR Meta": 2}
    after = {"Gate": 1, "Agent PR Meta": 1}
    comparison = workflow_run_counts.compare_counts(before, after)
    table = workflow_run_counts._format_table(comparison)
    assert "Workflow" in table
    assert "Total" in table


def test_json_format_includes_timestamp_and_workflow_shape() -> None:
    comparison = [
        workflow_run_counts.WorkflowCount("Gate", before=2, after=1),
        workflow_run_counts.WorkflowCount("New Workflow", before=0, after=2),
    ]

    payload = json.loads(workflow_run_counts._format_json(comparison))

    assert set(payload) == {"generated_at", "workflows"}
    generated_at = datetime.fromisoformat(payload["generated_at"])
    assert generated_at.tzinfo is not None
    assert payload["workflows"] == [
        {
            "name": "Gate",
            "before": 2,
            "after": 1,
            "delta": -1,
            "pct_change": "-50.0%",
        },
        {
            "name": "New Workflow",
            "before": 0,
            "after": 2,
            "delta": 2,
            "pct_change": "new",
        },
    ]


def test_main_writes_json_output_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    before = _write_snapshot(
        tmp_path,
        "before.json",
        {
            "workflow_runs": [
                {"name": "Gate"},
                {"name": "Gate"},
                {"workflow": {"path": ".github/workflows/other.yml"}},
            ]
        },
    )
    after = _write_snapshot(
        tmp_path,
        "after.json",
        {
            "workflow_runs": [
                {"name": "Gate"},
                {"workflow": {"name": "Deploy"}},
            ]
        },
    )
    output = tmp_path / "counts.json"

    result = workflow_run_counts.main(
        [
            "--before",
            str(before),
            "--after",
            str(after),
            "--format",
            "json",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == ""
    assert output.read_text(encoding="utf-8").endswith("\n")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["workflows"] == [
        {
            "name": ".github/workflows/other.yml",
            "before": 1,
            "after": 0,
            "delta": -1,
            "pct_change": "-100.0%",
        },
        {
            "name": "Deploy",
            "before": 0,
            "after": 1,
            "delta": 1,
            "pct_change": "new",
        },
        {
            "name": "Gate",
            "before": 2,
            "after": 1,
            "delta": -1,
            "pct_change": "-50.0%",
        },
    ]


def test_main_returns_2_for_malformed_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad_before = _write_snapshot(tmp_path, "bad-before.json", {"workflow_runs": {"id": 1}})
    after = _write_snapshot(tmp_path, "after.json", {"workflow_runs": []})

    result = workflow_run_counts.main(["--before", str(bad_before), "--after", str(after)])

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert f"Snapshot contains invalid run list: {bad_before}" in captured.err
