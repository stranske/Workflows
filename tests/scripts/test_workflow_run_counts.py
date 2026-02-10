from pathlib import Path

import pytest
from scripts import workflow_run_counts


def _fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / "workflow_runs" / name


def test_load_runs_from_dict() -> None:
    runs = workflow_run_counts.load_runs(_fixture_path("before.json"))
    assert isinstance(runs, list)
    assert {run.get("id") for run in runs} == {1, 2, 3, 4, 5}


def test_load_runs_rejects_invalid_json(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="valid JSON"):
        workflow_run_counts.load_runs(bad_path)


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


def test_table_format_includes_total() -> None:
    before = {"Gate": 2, "Agent PR Meta": 2}
    after = {"Gate": 1, "Agent PR Meta": 1}
    comparison = workflow_run_counts.compare_counts(before, after)
    table = workflow_run_counts._format_table(comparison)
    assert "Workflow" in table
    assert "Total" in table
