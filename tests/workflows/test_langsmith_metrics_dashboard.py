from pathlib import Path

WORKFLOW = Path(".github/workflows/maint-80-langsmith-metrics-dashboard.yml")


def test_fleet_artifact_lookup_does_not_mix_slurp_with_jq() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "--paginate --slurp --method GET" in source
    assert "--arg artifact_name" in source
    assert "select(.name == $artifact_name and .expired == false)" in source
    assert "--slurp --method GET \\\n" in source
    assert '--jq "[.[].artifacts' not in source


def test_dashboard_issue_uses_existing_labels() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert '--label "metrics,automated"' in source
    assert "metrics,langsmith,automated" not in source
    assert "labels 'metrics,automated'" in source


def test_fleet_status_is_warning_only_and_appended_to_report() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "::warning title=LangSmith fleet artifacts incomplete::" in source
    assert "cat .metrics-tmp/fleet/fleet-status.md" in source
    assert "if [ -f .metrics-tmp/fleet/fleet-status.md ]; then" in source


def test_fleet_rollup_and_publication_paths_are_wired() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    # Fleet rollup is generated from combined records via the validator summary output.
    assert "python scripts/langsmith_fleet.py .metrics-tmp/fleet/combined-fleet.ndjson" in source
    assert '--registry "$REGISTRY" --summary --format markdown' in source
    assert '--registry "$REGISTRY" --summary --format json' in source

    # The same report payload feeds both issue body and committed dashboard file.
    assert "REPORT=$(cat .metrics-tmp/report.md)" in source
    assert "$REPORT" in source
    assert "$(cat .metrics-tmp/report.md)" in source
