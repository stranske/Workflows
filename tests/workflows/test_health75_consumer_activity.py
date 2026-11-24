"""Protect the optional consumer runner and the independent current report."""

from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github/workflows/health-75-api-rate-diagnostic.yml"
)


def test_health75_starts_consumer_job_only_for_manual_opt_in():
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    consumer = jobs["check-consumer-repos"]
    report = jobs["generate-report"]

    manual_opt_in = consumer["env"]["RUN_CONSUMER_CHECKS"]
    assert manual_opt_in == (
        "${{ github.event_name == 'workflow_dispatch' && inputs.include_consumer_repos != false }}"
    )
    assert consumer[
        "if"
    ] == "${{ inputs.report_mode != 'historical' && " + manual_opt_in.removeprefix("${{ ")
    assert report["needs"] == ["collect-rate-limits", "check-consumer-repos"]
    assert report["if"] == "${{ always() && inputs.report_mode != 'historical' }}"
