from pathlib import Path

from scripts.workflow_pr_context_audit import (
    TriggerSummary,
    WorkflowAudit,
    audit_workflows,
    build_path_pattern,
    detect_pr_context_markers,
    format_table,
    load_workflow,
    normalize_triggers,
    serialize_trigger_summary,
    serialize_workflow_audit,
    summarize_by_triggers,
)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_build_path_pattern_matches_dotted_optional_and_bracket_access() -> None:
    pattern = build_path_pattern("github.event.issue.pull_request")

    assert pattern.search("github.event.issue.pull_request")
    assert pattern.search("github?.event?.issue?.pull_request")
    assert pattern.search("github['event']['issue']['pull_request']")
    assert pattern.search('github?.["event"]?.issue?.["pull_request"]')


def test_build_path_pattern_rejects_partial_segment_matches() -> None:
    pattern = build_path_pattern("github.event.issue.pull_request")

    assert pattern.search("github.event.issue.pull_request_target") is None
    assert pattern.search("github.event.issue_number.pull_request") is None


def test_normalize_triggers_returns_empty_for_none_and_unknown() -> None:
    assert normalize_triggers(None) == ()
    assert normalize_triggers(42) == ()


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


def test_normalize_triggers_sorts_collection_inputs() -> None:
    assert normalize_triggers(["workflow_dispatch", "pull_request"]) == (
        "pull_request",
        "workflow_dispatch",
    )
    assert normalize_triggers({"workflow_run": {}, "pull_request": {}}) == (
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
    if (github.event.issue?.pull_request?.url) {
      console.log("Issue PR link");
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
    assert "github.event.issue.pull_request" in markers
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


def test_detect_pr_context_markers_from_event_source_issue() -> None:
    text = """
    if (event.source?.issue?.pull_request) {
      linkedPR = event.source.issue.number;
    }
    """
    markers = detect_pr_context_markers(text)
    assert "event.source.issue.pull_request" in markers
    assert "event.source.issue.number" in markers


def test_detect_pr_context_markers_mixed_optional_chain_and_bracket_issue() -> None:
    text = """
    if (github?.event?.issue?.['pull_request']?.url) {
      console.log("issue PR url");
    }
    if (context?.payload?.['issue']?.["number"]) {
      console.log("issue number");
    }
    if (github.event?.['issue']?.pull_request) {
      console.log("mixed bracket and dot");
    }
    """
    markers = detect_pr_context_markers(text)
    assert markers == (
        "context.payload.issue.number",
        "github.event.issue.pull_request",
    )


def test_detect_pr_context_markers_mixed_optional_chain_and_bracket_workflow_run() -> None:
    text = """
    if (github?.event?.workflow_run?.['pull_requests']?.[0]) {
      console.log("workflow run PR");
    }
    if (context?.payload?.workflow_run?.["pull_requests"]) {
      console.log("payload workflow run PRs");
    }
    """
    markers = detect_pr_context_markers(text)
    assert markers == ("workflow_run.pull_requests",)


def test_detect_pr_context_markers_includes_pull_request_number() -> None:
    text = """
    const prNumber = inputs.pull_request_number;
    """
    markers = detect_pr_context_markers(text)
    assert markers == ("pull_request_number",)


def test_detect_pr_context_markers_from_bracket_notation() -> None:
    text = """
    if (github.event["pull_request"]) {
      console.log("PR event");
    }
    if (github?.event?.['issue']?.["pull_request"]) {
      console.log("Issue PR link");
    }
    if (context.payload["issue"]["number"]) {
      console.log("Issue number");
    }
    if (context?.payload?.["pull_request"]) {
      console.log("PR payload");
    }
    if (event?.source?.["issue"]?.['number']) {
      console.log("Event source issue number");
    }
    if (context.payload?.workflow_run?.["pull_requests"]) {
      console.log("Workflow run PRs");
    }
    """
    markers = detect_pr_context_markers(text)
    assert "github.event.pull_request" in markers
    assert "github.event.issue.pull_request" in markers
    assert "context.payload.issue.number" in markers
    assert "context.payload.pull_request" in markers
    assert "event.source.issue.number" in markers
    assert "workflow_run.pull_requests" in markers


def test_detect_pr_context_markers_ignores_partial_segment_matches() -> None:
    text = """
    if (github.event.pull_requester) {
      console.log("Not a PR");
    }
    if (context.payload.issue_number) {
      console.log("Not an issue number segment");
    }
    """
    markers = detect_pr_context_markers(text)
    assert "github.event.pull_request" not in markers
    assert "github.event.issue.number" not in markers


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


def test_load_workflow_returns_none_for_invalid_yaml(tmp_path: Path) -> None:
    workflow = tmp_path / "invalid.yml"
    workflow.write_text("name: Invalid\non: [\n", encoding="utf-8")

    assert load_workflow(workflow) is None


def test_load_workflow_returns_none_for_non_mapping_yaml(tmp_path: Path) -> None:
    workflow = tmp_path / "list.yml"
    workflow.write_text("- name: Not a workflow mapping\n", encoding="utf-8")

    assert load_workflow(workflow) is None


def test_audit_workflows_reads_legacy_true_on_field(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()

    _write(
        workflows_dir / "legacy-true-on.yml",
        """
name: Legacy True On
true:
  push:
    branches: [main]
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo "legacy trigger"
""",
    )

    results = audit_workflows(workflows_dir)
    by_name = {item.path.name: item for item in results}

    assert by_name["legacy-true-on.yml"].valid is True
    assert by_name["legacy-true-on.yml"].triggers == ("push",)


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


def test_audit_workflows_reports_non_mapping_yaml(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()

    _write(
        workflows_dir / "list.yml",
        """
- name: Not a workflow mapping
  on: workflow_dispatch
""",
    )

    results = audit_workflows(workflows_dir)
    by_name = {item.path.name: item for item in results}

    assert by_name["list.yml"].valid is False
    assert by_name["list.yml"].error == "invalid-yaml"


def test_format_table_includes_error_column(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()

    _write(
        workflows_dir / "invalid.yml",
        """
name: Invalid
on: [
""",
    )

    table = format_table(audit_workflows(workflows_dir))
    lines = table.splitlines()

    assert lines[0].endswith("valid\terror")
    assert any(line.endswith("\tinvalid-yaml") for line in lines[1:])


def test_format_table_serializes_representative_rows_byte_for_byte() -> None:
    rows = [
        WorkflowAudit(
            path=Path(".github/workflows/alpha.yml"),
            triggers=("pull_request", "workflow_dispatch"),
            pr_context_markers=(
                "context.payload.pull_request",
                "github.event.pull_request",
            ),
            valid=True,
            error=None,
        ),
        WorkflowAudit(
            path=Path(".github/workflows/beta.yml"),
            triggers=(),
            pr_context_markers=(),
            valid=False,
            error="invalid-yaml",
        ),
    ]

    assert format_table(rows) == (
        "path\ttriggers\tpr_context_markers\tvalid\terror\n"
        ".github/workflows/alpha.yml\t"
        "pull_request,workflow_dispatch\t"
        "context.payload.pull_request,github.event.pull_request\t"
        "true\t\n"
        ".github/workflows/beta.yml\t\t\tfalse\tinvalid-yaml"
    )


def test_serializers_normalize_dataclass_report_records() -> None:
    audit = WorkflowAudit(
        path=Path(".github/workflows/alpha.yml"),
        triggers=("pull_request",),
        pr_context_markers=("github.event.pull_request",),
        valid=True,
        error=None,
    )
    summary = TriggerSummary(
        triggers=("pull_request",),
        workflows=(str(Path(".github/workflows/alpha.yml")),),
        pr_context_markers=("github.event.pull_request",),
    )

    assert serialize_workflow_audit(audit) == {
        "path": ".github/workflows/alpha.yml",
        "triggers": ["pull_request"],
        "pr_context_markers": ["github.event.pull_request"],
        "valid": True,
        "error": None,
    }
    assert serialize_trigger_summary(summary) == {
        "triggers": ["pull_request"],
        "workflows": [".github/workflows/alpha.yml"],
        "pr_context_markers": ["github.event.pull_request"],
    }


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


def test_summarize_by_triggers_sorts_groups_and_aggregates_markers() -> None:
    results = [
        WorkflowAudit(
            path=Path("zeta.yml"),
            triggers=("workflow_dispatch",),
            pr_context_markers=("github.event.pull_request",),
            valid=True,
            error=None,
        ),
        WorkflowAudit(
            path=Path("beta.yml"),
            triggers=("pull_request",),
            pr_context_markers=("context.payload.pull_request",),
            valid=True,
            error=None,
        ),
        WorkflowAudit(
            path=Path("alpha.yml"),
            triggers=("pull_request",),
            pr_context_markers=("github.event.pull_request",),
            valid=True,
            error=None,
        ),
    ]

    summaries = summarize_by_triggers(results)

    assert [summary.triggers for summary in summaries] == [
        ("pull_request",),
        ("workflow_dispatch",),
    ]
    assert summaries[0].workflows == ("alpha.yml", "beta.yml")
    assert summaries[0].pr_context_markers == (
        "context.payload.pull_request",
        "github.event.pull_request",
    )


def test_summarize_by_triggers_unions_overlapping_markers(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()

    _write(
        workflows_dir / "alpha.yml",
        """
name: Alpha
on: pull_request
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.event.pull_request.number }}"
      - run: echo "${{ github.event.issue.number }}"
""",
    )
    _write(
        workflows_dir / "beta.yml",
        """
name: Beta
on: pull_request
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.event.pull_request.title }}"
      - run: echo "${{ context.payload.issue.pull_request }}"
""",
    )
    _write(
        workflows_dir / "gamma.yml",
        """
name: Gamma
on: workflow_dispatch
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ context.payload.issue.number }}"
""",
    )

    results = audit_workflows(workflows_dir)
    summaries = summarize_by_triggers(results)

    assert len(summaries) == 2
    by_triggers = {summary.triggers: summary for summary in summaries}

    pull_request_group = by_triggers[("pull_request",)]
    assert pull_request_group.workflows == (
        str(workflows_dir / "alpha.yml"),
        str(workflows_dir / "beta.yml"),
    )
    assert pull_request_group.pr_context_markers == (
        "context.payload.issue.pull_request",
        "github.event.issue.number",
        "github.event.pull_request",
    )

    dispatch_group = by_triggers[("workflow_dispatch",)]
    assert dispatch_group.workflows == (str(workflows_dir / "gamma.yml"),)
    assert dispatch_group.pr_context_markers == ("context.payload.issue.number",)
