"""Regression checks for the source and bootstrap coverage-guard selectors."""

from pathlib import Path

import pytest
import yaml


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
    assert workflow.count("Coverage verification could not proceed: ${missingPairReason}.") == 1
    assert workflow.count("no gate-coverage artifacts were published") == 1
    assert workflow.count("published coverage artifact names did not match") == 1
    assert workflow.count("coverage payloads were published without ${trendArtifactName}") == 1
    assert '"coverage_artifacts/payload/gate-coverage.json"' in workflow


@pytest.mark.parametrize(
    "workflow_path",
    [
        ".github/workflows/maint-coverage-guard.yml",
        "templates/consumer-repo/.github/workflows/maint-coverage-guard.yml",
    ],
)
def test_recovery_cache_survives_producer_runs_and_saves_after_guard(workflow_path: str) -> None:
    steps = yaml.safe_load(Path(workflow_path).read_text())["jobs"]["guard"]["steps"]
    restore = next(s for s in steps if s.get("id") == "coverage-trend-history-cache")
    guard = next(s for s in steps if s.get("name") == "Run coverage guard")
    save = next(s for s in steps if s.get("name") == "Save coverage recovery history")
    assert steps.index(restore) < steps.index(guard) < steps.index(save)
    assert restore["uses"].startswith("actions/cache/restore@")
    assert save["uses"].startswith("actions/cache/save@")
    assert restore["with"]["path"] == save["with"]["path"] == "coverage_artifacts/history"
    assert "github.repository" in restore["with"]["key"]
    assert "github.run_id" in restore["with"]["key"]
    assert "github.run_attempt" in restore["with"]["key"]
    assert "discover.outputs.run_id" not in restore["with"]["key"]
    prefix = restore["with"]["restore-keys"].strip()
    assert "github.repository" in prefix and "run_id" not in prefix
    assert restore["with"]["key"].startswith(prefix)
    assert 'HISTORY_PATH="coverage_artifacts/history/coverage-trend-history.ndjson"' in guard["run"]
    assert "cache-primary-key" in save["with"]["key"]
    assert "hashFiles('coverage_artifacts/history/coverage-trend-history.ndjson')" in save["if"]
