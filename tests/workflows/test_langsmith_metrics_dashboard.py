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
