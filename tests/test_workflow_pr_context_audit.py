from pathlib import Path

from scripts.workflow_pr_context_audit import (
    audit_workflows,
    detect_pr_context_markers,
    normalize_triggers,
)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_normalize_triggers_handles_common_shapes() -> None:
    assert normalize_triggers("pull_request") == ("pull_request",)
    assert normalize_triggers(["pull_request", "workflow_dispatch"]) == (
        "pull_request",
        "workflow_dispatch",
    )
    assert normalize_triggers({"pull_request": {}, "workflow_run": {}}) == (
        "pull_request",
        "workflow_run",
    )


def test_detect_pr_context_markers_from_text() -> None:
    text = """
    if (context.payload.pull_request) {
      console.log(github.event.pull_request.number);
    }
    """
    markers = detect_pr_context_markers(text)
    assert "context.payload.pull_request" in markers
    assert "github.event.pull_request" in markers


def test_audit_workflows_reports_pr_context(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()

    _write(
        workflows_dir / "with-pr.yml",
        """
name: With PR
on:
  pull_request:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.event.pull_request.number }}"
""",
    )
    _write(
        workflows_dir / "without-pr.yml",
        """
name: Without PR
on: workflow_dispatch
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo "hi"
""",
    )

    results = audit_workflows(workflows_dir)
    by_name = {item.path.name: item for item in results}

    assert by_name["with-pr.yml"].valid is True
    assert "pull_request" in by_name["with-pr.yml"].triggers
    assert "github.event.pull_request" in by_name["with-pr.yml"].pr_context_markers

    assert by_name["without-pr.yml"].valid is True
    assert by_name["without-pr.yml"].pr_context_markers == ()
