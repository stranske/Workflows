"""Tests for generate_suppression_guard_comment helpers."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.generate_suppression_guard_comment import build_comment


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
