"""Shape tests for the metrics-retention workflow (workflow_dispatch + pull_request only)."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/maint-metrics-retention.yml")
RETENTION_DOCS = (
    Path("docs/agent-automation.md"),
    Path("docs/ci/WORKFLOW_SYSTEM.md"),
)


def _load_workflow() -> dict:
    assert WORKFLOW_PATH.is_file(), f"missing workflow file: {WORKFLOW_PATH}"
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_workflow_has_required_triggers() -> None:
    data = _load_workflow()
    # PyYAML parses the `on:` key as the Python literal `True` because of the YAML 1.1
    # boolean rules used by `yaml.safe_load`.
    triggers = data.get(True) or data.get("on")
    assert triggers is not None, "workflow must declare triggers"
    # The nightly `schedule:` cron was removed: with no artifact-restore step it
    # only ever produced a no-op summary (see issue #2276). The workflow remains a
    # PR-path / manual smoke test of metrics_retention.py and must NOT reintroduce
    # the scheduled no-op run.
    assert "schedule" not in triggers, "no-op nightly schedule must not be reintroduced"
    assert "workflow_dispatch" in triggers, "must support manual workflow_dispatch"
    assert "pull_request" in triggers, "must trigger on pull_request for dry-run validation"


def test_retention_docs_do_not_advertise_removed_nightly_schedule() -> None:
    for path in RETENTION_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "runs `scripts/metrics_retention.py` nightly" not in text
        assert "The nightly schedule is implemented" not in text


def test_workflow_invokes_retention_script_with_dry_run_branch() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    data = _load_workflow()
    triggers = data.get(True) or data.get("on")
    dry_run_input = triggers["workflow_dispatch"]["inputs"]["dry_run"]
    assert dry_run_input["type"] == "boolean"
    assert dry_run_input["default"] is False
    assert "scripts/metrics_retention.py" in text, "workflow must invoke the retention script"
    assert (
        "--config config/retention-policy.json" in text
    ), "workflow must pass the canonical retention policy config"
    assert "--dry-run" in text, "workflow must support a dry-run code path"
    assert (
        "github.event_name" in text and "pull_request" in text
    ), "workflow must branch on pull_request to activate --dry-run mode"


def test_workflow_uploads_retention_log_artifact() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "actions/upload-artifact" in text, "must upload the retention log as an artifact"
    assert (
        "metrics-retention-log" in text
    ), "artifact name must be metrics-retention-log per design doc"
    assert "metrics-retention.ndjson" in text, "must upload the DEFAULT_RETENTION_LOG path"


def test_workflow_emits_reduction_percent_to_step_summary() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "GITHUB_STEP_SUMMARY" in text, "workflow must write to $GITHUB_STEP_SUMMARY"
    assert (
        "reduction_percent" in text or "Storage reduction" in text
    ), "step summary must surface the storage reduction percentage from the retention run"
