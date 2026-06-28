"""Tests for generate_suppression_guard_comment helpers."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.generate_suppression_guard_comment import _extract_step_hints, build_comment


def _write_yaml(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_build_comment_reports_missing_workflow(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yml"

    comment = build_comment([missing_path], include_label=True)

    assert "Label: needs-human" in comment
    assert f"Workflow: {missing_path}" in comment
    assert "Workflow file not found in repository." in comment


def test_build_comment_ignores_guarded_steps(tmp_path: Path) -> None:
    workflow_path = tmp_path / "guarded.yml"
    _write_yaml(
        workflow_path,
        """
        name: Guarded Workflow
        jobs:
          post:
            if: ${{ needs.guard.outputs.should_post_review == 'true' }}
            runs-on: ubuntu-latest
            steps:
              - name: Post comment
                run: github.rest.issues.createComment
        """,
    )

    comment = build_comment([workflow_path])

    assert "No unguarded PR comment/review posting steps detected" in comment
    assert "post / Post comment" not in comment


def test_build_comment_reports_unguarded_steps(tmp_path: Path) -> None:
    workflow_path = tmp_path / "unguarded.yml"
    _write_yaml(
        workflow_path,
        """
        name: Unguarded Workflow
        jobs:
          post:
            runs-on: ubuntu-latest
            steps:
              - name: Post comment
                run: github.rest.issues.createComment
        """,
    )

    comment = build_comment([workflow_path])

    assert "post / Post comment" in comment


def test_build_comment_ignores_suppress_comments_guarded_steps(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "suppress.yml"
    _write_yaml(
        workflow_path,
        """
        name: Suppress Comments Workflow
        jobs:
          post:
            runs-on: ubuntu-latest
            steps:
              - name: Post comment
                if: inputs.suppress_comments != true
                run: github.rest.issues.createComment
        """,
    )

    comment = build_comment([workflow_path])

    assert "No unguarded PR comment/review posting steps detected" in comment
    assert "post / Post comment" not in comment


def test_build_comment_flags_inverted_suppress_comments_guard(
    tmp_path: Path,
) -> None:
    """``suppress_comments == true`` allows posting during suppression."""
    workflow_path = tmp_path / "inverted.yml"
    _write_yaml(
        workflow_path,
        """
        name: Inverted Guard Workflow
        jobs:
          post:
            runs-on: ubuntu-latest
            steps:
              - name: Post comment
                if: inputs.suppress_comments == true
                run: github.rest.issues.createComment
        """,
    )

    comment = build_comment([workflow_path])

    # Inverted guard should NOT be treated as properly guarded
    assert "post / Post comment" in comment


def test_build_comment_ignores_parenthesized_negation_guard(
    tmp_path: Path,
) -> None:
    """``!(inputs.suppress_comments)`` is a valid negation guard."""
    workflow_path = tmp_path / "paren.yml"
    _write_yaml(
        workflow_path,
        """
        name: Parenthesized Negation Workflow
        jobs:
          post:
            runs-on: ubuntu-latest
            steps:
              - name: Post comment
                if: ${{ !(inputs.suppress_comments) }}
                run: github.rest.issues.createComment
        """,
    )

    comment = build_comment([workflow_path])

    assert "No unguarded PR comment/review posting steps detected" in comment
    assert "post / Post comment" not in comment


def test_build_comment_detects_octokit_aliases(tmp_path: Path) -> None:
    workflow_path = tmp_path / "octokit.yml"
    _write_yaml(
        workflow_path,
        """
        name: Octokit Workflow
        jobs:
          post:
            runs-on: ubuntu-latest
            steps:
              - name: Post comment
                run: octokit.issues.createComment
        """,
    )

    comment = build_comment([workflow_path])

    assert "post / Post comment" in comment


def test_extract_step_hints_mixed_run_uses() -> None:
    """Test that _extract_step_hints handles steps with both run and uses fields."""
    # Step with run field containing script pattern
    step_with_run = {
        "name": "Script step",
        "run": "github.rest.issues.createComment",
    }
    hints = _extract_step_hints(step_with_run)
    assert "issues.createComment" in hints

    # Step with uses field containing action hint
    step_with_uses = {
        "name": "Action step",
        "uses": "peter-evans/create-or-update-comment@v2",
    }
    hints = _extract_step_hints(step_with_uses)
    assert "create-or-update-comment action" in hints

    # Step with both run and uses
    step_mixed = {
        "name": "Mixed step",
        "run": "github.rest.pulls.createReview",
        "uses": "peter-evans/create-pull-request@v4",
    }
    hints = _extract_step_hints(step_mixed)
    assert "pulls.createReview" in hints
    assert "create-pull-request action" in hints

    # Step with neither run nor uses
    step_empty = {
        "name": "Empty step",
    }
    hints = _extract_step_hints(step_empty)
    assert hints == []


def test_build_comment_no_findings(tmp_path: Path) -> None:
    """Test build_comment with workflow that has no posting steps (no findings)."""
    workflow_path = tmp_path / "no_findings.yml"
    _write_yaml(
        workflow_path,
        """
        name: No Findings Workflow
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - name: Build
                run: echo "building"
              - name: Test
                run: echo "testing"
        """,
    )

    comment = build_comment([workflow_path])

    assert "No unguarded PR comment/review posting steps detected" in comment
    assert "Workflow: " + str(workflow_path) in comment


def test_build_comment_include_label(tmp_path: Path) -> None:
    """Test build_comment with include_label=True."""
    workflow_path = tmp_path / "with_label.yml"
    _write_yaml(
        workflow_path,
        """
        name: Label Test Workflow
        jobs:
          post:
            runs-on: ubuntu-latest
            steps:
              - name: Post comment
                run: github.rest.issues.createComment
        """,
    )

    comment = build_comment([workflow_path], include_label=True)

    assert "Label: needs-human" in comment
    assert "post / Post comment" in comment


def test_build_comment_include_label_no_findings(tmp_path: Path) -> None:
    """Test build_comment with include_label=True and no findings."""
    workflow_path = tmp_path / "label_no_findings.yml"
    _write_yaml(
        workflow_path,
        """
        name: Label No Findings Workflow
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - name: Build
                run: echo "building"
        """,
    )

    comment = build_comment([workflow_path], include_label=True)

    assert "Label: needs-human" in comment
    assert "No unguarded PR comment/review posting steps detected" in comment
