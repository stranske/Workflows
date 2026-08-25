"""Regression checks for the source and bootstrap coverage-guard selectors."""

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "workflow_path",
    [
        ".github/workflows/maint-coverage-guard.yml",
        "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml",
    ],
)
def test_coverage_guard_selects_only_runs_with_payload_and_trend(workflow_path: str) -> None:
    workflow = Path(workflow_path).read_text(encoding="utf-8")

    assert (
        workflow.count("const hasTrend = availableCoverageArtifactNames.has(trendArtifactName);")
        == 1
    )
    assert workflow.count("if (payloadName && hasTrend)") == 1
    assert workflow.count("coverage payload and trend on a successful Gate run") == 1
