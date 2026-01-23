from pathlib import Path

from scripts import workflow_concurrency_audit


def _write_workflow(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def _runs_fixture(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / "workflow_runs" / name


def test_audit_marks_high_frequency_missing_cancel(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "ci.yml",
        """
name: CI
on: [push]
concurrency: ci-${{ github.ref }}
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hello
""",
    )

    results = workflow_concurrency_audit.audit_workflows(workflow_dir)
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.has_canceling_concurrency is False
    assert item.has_workflow_concurrency is True
    assert item.has_workflow_canceling_concurrency is False
    assert item.has_job_concurrency is False
    assert item.has_job_canceling_concurrency is False
    assert item.action_required == "set_cancel_in_progress_true"
    assert item.recommended_group == "${{ github.workflow }}-${{ github.ref }}"
    assert any(setting.group == "ci-${{ github.ref }}" for setting in item.concurrency)


def test_normalize_triggers_dedupes_mixed_list() -> None:
    triggers = workflow_concurrency_audit.normalize_triggers(
        ["pull_request", {"issues": {"types": ["opened"]}}, {"pull_request": None}]
    )
    assert triggers == ("issues", "pull_request")


def test_normalize_triggers_strips_string_trigger() -> None:
    triggers = workflow_concurrency_audit.normalize_triggers("  pull_request  ")
    assert triggers == ("pull_request",)


def test_normalize_triggers_ignores_blank_string_trigger() -> None:
    triggers = workflow_concurrency_audit.normalize_triggers("   ")
    assert triggers == ()


def test_normalize_triggers_ignores_blank_entries() -> None:
    triggers = workflow_concurrency_audit.normalize_triggers(
        [" pull_request ", "", {"issues": None}, "   "]
    )
    assert triggers == ("issues", "pull_request")


def test_normalize_triggers_ignores_non_string_entries() -> None:
    triggers = workflow_concurrency_audit.normalize_triggers(["pull_request", None, 123, True])
    assert triggers == ("pull_request",)


def test_audit_accepts_job_level_cancel(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "pr.yml",
        """
name: PR
on: pull_request
jobs:
  test:
    runs-on: ubuntu-latest
    concurrency:
      group: pr-${{ github.event.pull_request.number }}
      cancel-in-progress: true
    steps:
      - run: echo ok
""",
    )

    results = workflow_concurrency_audit.audit_workflows(workflow_dir)
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.has_canceling_concurrency is True
    assert item.has_workflow_concurrency is False
    assert item.has_workflow_canceling_concurrency is False
    assert item.has_job_concurrency is True
    assert item.has_job_canceling_concurrency is True
    assert item.action_required == "none"
    assert (
        item.recommended_group
        == "${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}"
    )
    assert any(setting.location == "job:test" for setting in item.concurrency)


def test_audit_accepts_job_level_overrides(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "pr.yml",
        """
name: PR
on: pull_request
concurrency:
  group: pr-${{ github.event.pull_request.number }}
  cancel-in-progress: false
jobs:
  test:
    runs-on: ubuntu-latest
    concurrency:
      group: pr-${{ github.event.pull_request.number }}
      cancel-in-progress: true
    steps:
      - run: echo ok
""",
    )

    results = workflow_concurrency_audit.audit_workflows(workflow_dir)
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.has_canceling_concurrency is True
    assert item.has_workflow_concurrency is True
    assert item.has_workflow_canceling_concurrency is False
    assert item.has_job_concurrency is True
    assert item.has_job_canceling_concurrency is True
    assert item.action_required == "none"
    assert len(item.concurrency) == 2


def test_audit_accepts_expression_cancel(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "expr.yml",
        """
name: Expr
on: pull_request
concurrency:
  group: pr-${{ github.event.pull_request.number }}
  cancel-in-progress: ${{ github.event_name != 'workflow_dispatch' }}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
    )

    results = workflow_concurrency_audit.audit_workflows(workflow_dir)
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.has_canceling_concurrency is True
    assert item.has_workflow_concurrency is True
    assert item.has_workflow_canceling_concurrency is True
    assert item.has_job_concurrency is False
    assert item.has_job_canceling_concurrency is False
    assert item.action_required == "none"
    setting = item.concurrency[0]
    assert setting.cancel_in_progress is None
    assert setting.cancel_is_expression is True


def test_audit_tracks_workflow_level_cancel(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "workflow.yml",
        """
name: Workflow
on: pull_request
concurrency:
  group: pr-${{ github.event.pull_request.number }}
  cancel-in-progress: true
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
    )

    results = workflow_concurrency_audit.audit_workflows(workflow_dir)
    assert len(results) == 1
    item = results[0]
    assert item.has_canceling_concurrency is True
    assert item.has_workflow_concurrency is True
    assert item.has_workflow_canceling_concurrency is True
    assert item.has_job_concurrency is False
    assert item.has_job_canceling_concurrency is False


def test_audit_recommends_issue_comment_group(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "comment.yml",
        """
name: Comment
on: issue_comment
jobs:
  handle:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )

    results = workflow_concurrency_audit.audit_workflows(workflow_dir)
    assert len(results) == 1
    assert (
        results[0].recommended_group
        == "${{ github.workflow }}-issue-${{ github.event.issue.number || github.ref }}"
    )
    assert results[0].action_required == "add_concurrency"


def test_audit_prefers_issue_group_when_mixed_with_pull_request(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "mixed.yml",
        """
name: Mixed
on: [issues, pull_request]
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.action_required == "add_concurrency"
    assert (
        item.recommended_group
        == "${{ github.workflow }}-issue-${{ github.event.issue.number || github.event.pull_request.number || github.ref }}"
    )


def test_audit_handles_list_with_dict_trigger(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "mixed.yml",
        """
name: Mixed list
on:
  - pull_request
  - issue_comment:
      types: [created]
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.action_required == "add_concurrency"
    assert (
        item.recommended_group
        == "${{ github.workflow }}-issue-${{ github.event.issue.number || github.event.pull_request.number || github.ref }}"
    )


def test_audit_marks_issues_as_high_frequency(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "issues.yml",
        """
name: Issues
on: issues
jobs:
  triage:
    runs-on: ubuntu-latest
    steps:
      - run: echo triage
""",
    )

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.action_required == "add_concurrency"
    assert (
        item.recommended_group
        == "${{ github.workflow }}-issue-${{ github.event.issue.number || github.ref }}"
    )


def test_audit_marks_workflow_run_as_high_frequency(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "autofix.yml",
        """
name: Autofix
on:
  workflow_run:
    workflows: [Gate]
    types: [completed]
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
    )

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.action_required == "add_concurrency"
    assert (
        item.recommended_group
        == "${{ github.workflow }}-workflow-run-${{ github.event.workflow_run.pull_requests[0].number || github.event.workflow_run.id || github.run_id }}"
    )


def test_audit_marks_merge_group_as_high_frequency(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "merge.yml",
        """
name: Merge queue
on: merge_group
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
    )

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.action_required == "add_concurrency"
    assert (
        item.recommended_group
        == "${{ github.workflow }}-merge-group-${{ github.event.merge_group.head_sha || github.sha }}"
    )


def test_audit_marks_pull_request_target_as_high_frequency(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "pr-target.yml",
        """
name: PR Target
on: pull_request_target
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
    )

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.action_required == "add_concurrency"
    assert (
        item.recommended_group
        == "${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.ref }}"
    )


def test_audit_skips_non_high_frequency_when_excluded(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "manual.yml",
        """
name: Manual
on: workflow_dispatch
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert results == []


def test_audit_includes_non_high_frequency_by_default(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "manual.yml",
        """
name: Manual
on: workflow_dispatch
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )

    results = workflow_concurrency_audit.audit_workflows(workflow_dir)
    assert len(results) == 1
    assert results[0].high_frequency is False
    assert results[0].action_required == "none"


def test_audit_ignores_cancel_without_group(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "bad.yml",
        """
name: Broken
on: pull_request
concurrency:
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.has_canceling_concurrency is False
    assert item.action_required == "add_concurrency"
    assert item.has_job_concurrency is False
    assert item.has_job_canceling_concurrency is False


def test_audit_treats_blank_group_as_missing(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "blank.yml",
        """
name: Blank group
on: pull_request
concurrency:
  group: "   "
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert len(results) == 1
    item = results[0]
    assert item.high_frequency is True
    assert item.has_canceling_concurrency is False
    assert item.action_required == "add_concurrency"
    assert item.has_job_concurrency is False
    assert item.has_job_canceling_concurrency is False


def test_audit_reports_invalid_yaml(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "invalid.yml",
        """
name: Invalid
on: [
""",
    )

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert len(results) == 1
    item = results[0]
    assert item.valid is False
    assert item.error == "invalid-yaml"
    assert item.action_required == "invalid-yaml"


def test_audit_reports_unreadable_paths(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    bad_path = workflow_dir / "bad.yml"
    bad_path.mkdir()

    results = workflow_concurrency_audit.audit_workflows(
        workflow_dir, include_non_high_frequency=False
    )
    assert len(results) == 1
    item = results[0]
    assert item.valid is False
    assert item.error == "unreadable"
    assert item.action_required == "unreadable"


def test_format_table_includes_valid_error_columns(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "invalid.yml",
        """
name: Invalid
on: [
""",
    )

    table = workflow_concurrency_audit.format_table(
        workflow_concurrency_audit.audit_workflows(workflow_dir)
    )
    header = table.splitlines()[0]
    assert header.endswith(
        "high_frequency\tvalid\terror\tmissing_or_incorrect\thas_canceling_concurrency"
        "\tworkflow_has_concurrency\tworkflow_has_canceling_concurrency"
        "\tjob_has_concurrency\tjob_has_canceling_concurrency\taction_required"
        "\trecommended_group\tconcurrency"
    )


def test_format_table_reports_job_concurrency_columns(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "job.yml",
        """
name: Job
on: pull_request
jobs:
  test:
    runs-on: ubuntu-latest
    concurrency:
      group: job-${{ github.event.pull_request.number }}
      cancel-in-progress: true
    steps:
      - run: echo ok
""",
    )

    table = workflow_concurrency_audit.format_table(
        workflow_concurrency_audit.audit_workflows(workflow_dir, include_non_high_frequency=False)
    )
    row = table.splitlines()[1].split("\t")
    assert row[6] == "true"  # has_canceling_concurrency
    assert row[7] == "false"  # workflow_has_concurrency
    assert row[8] == "false"  # workflow_has_canceling_concurrency
    assert row[9] == "true"  # job_has_concurrency
    assert row[10] == "true"  # job_has_canceling_concurrency


def test_format_markdown_outputs_table(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "manual.yml",
        """
name: Manual
on: workflow_dispatch
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )

    table = workflow_concurrency_audit.format_markdown(
        workflow_concurrency_audit.audit_workflows(workflow_dir)
    )
    lines = table.splitlines()
    assert lines[0].startswith("| path | triggers |")
    assert lines[1].startswith("| --- | --- |")
    assert lines[2].startswith("|")


def test_format_markdown_escapes_pipes(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "mixed.yml",
        """
name: Mixed
on: [issues, pull_request]
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )

    table = workflow_concurrency_audit.format_markdown(
        workflow_concurrency_audit.audit_workflows(workflow_dir)
    )
    row = table.splitlines()[2]
    assert "\\|\\|" in row


def test_format_missing_summary_returns_empty_when_no_issues(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_workflow(
        workflow_dir / "clean.yml",
        """
name: Clean
on: pull_request
concurrency:
  group: pr-${{ github.event.pull_request.number }}
  cancel-in-progress: true
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
    )

    results = workflow_concurrency_audit.audit_workflows(workflow_dir)
    output = workflow_concurrency_audit._format_missing_summary(results)
    assert output == ""


def test_format_missing_summary_includes_missing_entries(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    workflow_path = workflow_dir / "ci.yml"
    _write_workflow(
        workflow_path,
        """
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
    )

    results = workflow_concurrency_audit.audit_workflows(workflow_dir)
    output = workflow_concurrency_audit._format_missing_summary(results)
    lines = output.splitlines()
    assert lines[0] == "missing_or_incorrect_total\t1"
    assert (
        lines[1]
        == f"missing_or_incorrect\t{workflow_path}\tadd_concurrency\t"
        "${{ github.workflow }}-${{ github.ref }}"
    )


def test_calculate_debounced_runs_summarizes_totals() -> None:
    summary = workflow_concurrency_audit.calculate_debounced_runs(
        _runs_fixture("before.json"),
        _runs_fixture("after.json"),
        period_label="2026-01-01..2026-01-10",
    )
    assert summary.before_total == 5
    assert summary.after_total == 4
    assert summary.debounced_total == 2
    assert summary.period_label == "2026-01-01..2026-01-10"


def test_format_debounced_summary_emits_lines() -> None:
    summary = workflow_concurrency_audit.calculate_debounced_runs(
        _runs_fixture("before.json"),
        _runs_fixture("after.json"),
        period_label="2026-01-01..2026-01-10",
    )
    output = workflow_concurrency_audit._format_debounced_summary(summary)
    lines = output.splitlines()
    assert lines[0] == "debounced_runs_total\t2"
    assert lines[1] == "debounced_runs_before_total\t5"
    assert lines[2] == "debounced_runs_after_total\t4"
    assert lines[3] == "debounced_runs_period\t2026-01-01..2026-01-10"
