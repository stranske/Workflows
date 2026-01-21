from pathlib import Path

from scripts import workflow_concurrency_audit


def _write_workflow(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


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
    assert any(setting.group == "ci-${{ github.ref }}" for setting in item.concurrency)


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
    assert any(setting.location == "job:test" for setting in item.concurrency)


def test_audit_skips_non_high_frequency_by_default(tmp_path: Path) -> None:
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
    assert results == []


def test_audit_includes_non_high_frequency_when_requested(tmp_path: Path) -> None:
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
        workflow_dir, include_non_high_frequency=True
    )
    assert len(results) == 1
    assert results[0].high_frequency is False
