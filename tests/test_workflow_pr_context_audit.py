from pathlib import Path

from scripts.workflow_pr_context_audit import (
    audit_workflows,
    detect_pr_context_markers,
    load_workflow,
    normalize_triggers,
    summarize_by_triggers,
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
    if (context?.payload?.pull_request) {
      console.log(github?.event?.pull_request.number);
    }
    """
    markers = detect_pr_context_markers(text)
    assert "context.payload.pull_request" in markers
    assert "github.event.pull_request" in markers


def test_detect_pr_context_markers_from_issue_payload() -> None:
    text = """
    if (context.payload?.issue?.pull_request) {
      console.log("PR comment");
    }
    if (github.event.issue?.number) {
      console.log("Issue number");
    }
    if (context?.payload?.issue?.number) {
      console.log("Issue number payload");
    }
    """
    markers = detect_pr_context_markers(text)
    assert "context.payload.issue.pull_request" in markers
    assert "github.event.issue.number" in markers
    assert "context.payload.issue.number" in markers


def test_detect_pr_context_markers_from_workflow_run_payload() -> None:
    text = """
    if (context.payload?.workflow_run?.pull_requests) {
      console.log("workflow run PRs");
    }
    if (github.event.workflow_run?.pull_requests?.length) {
      console.log("workflow run PRs count");
    }
    """
    markers = detect_pr_context_markers(text)
    assert "workflow_run.pull_requests" in markers


def test_load_workflow_accepts_inline_text(tmp_path: Path) -> None:
    path = tmp_path / "missing.yml"
    data = load_workflow(
        path,
        text="""
name: Inline
on: workflow_dispatch
""",
    )

    assert data is not None
    assert data["name"] == "Inline"


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


def test_audit_workflows_handles_unreadable_paths(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()

    bad_path = workflows_dir / "bad.yml"
    bad_path.mkdir()

    results = audit_workflows(workflows_dir)
    by_name = {item.path.name: item for item in results}

    assert by_name["bad.yml"].valid is False
    assert by_name["bad.yml"].triggers == ()
    assert by_name["bad.yml"].pr_context_markers == ()
    assert by_name["bad.yml"].error == "unreadable"


def test_audit_workflows_reports_invalid_yaml(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()

    _write(
        workflows_dir / "invalid.yml",
        """
name: Invalid
on: [
""",
    )

    results = audit_workflows(workflows_dir)
    by_name = {item.path.name: item for item in results}

    assert by_name["invalid.yml"].valid is False
    assert by_name["invalid.yml"].error == "invalid-yaml"


def test_summarize_by_triggers_groups_workflows(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()

    _write(
        workflows_dir / "alpha.yml",
        """
name: Alpha
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
        workflows_dir / "beta.yml",
        """
name: Beta
on:
  pull_request:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.event.pull_request.title }}"
""",
    )

    results = audit_workflows(workflows_dir)
    summaries = summarize_by_triggers(results)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.triggers == ("pull_request",)
    assert summary.workflows == (
        str(workflows_dir / "alpha.yml"),
        str(workflows_dir / "beta.yml"),
    )
    assert "github.event.pull_request" in summary.pr_context_markers
