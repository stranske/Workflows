from __future__ import annotations

from scripts.langchain.issue_pr_context import (
    ContextOptions,
    build_formatted_body_marker,
    build_issue_context,
    build_pr_context,
    estimate_tokens,
    reuse_formatted_body,
)


def test_issue_context_enforces_token_budget_with_truncation() -> None:
    issue = {
        "number": 123,
        "title": "Oversize context",
        "state": "open",
        "body": "a" * 2000,
        "labels": [{"name": "agents:optimize"}],
    }

    context = build_issue_context(issue, ContextOptions(token_budget=80))

    assert context["truncated"] is True
    assert context["estimated_tokens"] <= 80
    assert "context exceeded token budget" in context["context"]
    assert len(context["formatted_body"]) < len(issue["body"])


def test_reuse_formatted_body_returns_embedded_marker_body() -> None:
    formatted = "## Tasks\n- [ ] Keep the formatted body\n"
    marker = build_formatted_body_marker(
        downstream_workflow="agents-auto-pilot",
        formatted_body=formatted,
    )
    issue = {"body": f"Raw body that should not be reused\n\n{marker}"}

    reused = reuse_formatted_body(issue, "agents-auto-pilot")

    assert reused == formatted


def test_reuse_formatted_body_returns_cleaned_body_for_matching_marker() -> None:
    marker = build_formatted_body_marker(workflows=["agents-issue-optimizer"])
    formatted = f"{marker}\n## Tasks\n- [ ] Existing formatted task"

    reused = reuse_formatted_body({"body": formatted}, "agents-issue-optimizer")

    assert reused == "## Tasks\n- [ ] Existing formatted task"


def test_reuse_formatted_body_returns_none_when_marker_missing_or_mismatched() -> None:
    marker = build_formatted_body_marker(workflows=["agents-auto-pilot"])

    assert (
        reuse_formatted_body({"body": "## Tasks\n- [ ] Missing marker"}, "agents-auto-pilot")
        is None
    )
    assert reuse_formatted_body({"body": marker}, "agents-pr-meta-v4") is None


def test_issue_context_shape_for_typical_fixture() -> None:
    issue = {
        "number": 42,
        "title": "Add context helper",
        "state": "open",
        "html_url": "https://github.com/example/repo/issues/42",
        "user": {"login": "octocat"},
        "labels": [{"name": "agents:optimize"}, {"name": "bug"}],
        "body": "## Tasks\n- [ ] Add helper\n\n## Acceptance Criteria\n- [ ] Tests pass",
    }

    context = build_issue_context(issue)

    assert context["kind"] == "issue"
    assert "## Issue Metadata" in context["metadata_block"]
    assert "- Number: #42" in context["metadata_block"]
    assert "- Labels: agents:optimize, bug" in context["metadata_block"]
    assert context["formatted_body"].startswith("## Tasks")
    assert "## Issue Body" in context["context"]
    assert context["estimated_tokens"] == estimate_tokens(context["context"])


def test_pr_context_shape_includes_labels_and_diff_when_requested() -> None:
    pr = {
        "number": 77,
        "title": "Wire helper",
        "state": "open",
        "html_url": "https://github.com/example/repo/pull/77",
        "user": {"login": "octocat"},
        "base": {"ref": "main"},
        "head": {"ref": "feat/helper"},
        "changed_files": 2,
        "additions": 40,
        "deletions": 3,
        "labels": [{"name": "workflow"}],
        "body": "Updates PR metadata context.",
        "files": [
            {
                "filename": "scripts/langchain/issue_pr_context.py",
                "patch": "@@ -0,0 +1 @@\n+helper",
            }
        ],
    }

    context = build_pr_context(pr, ContextOptions(include_diff=True, token_budget=500))

    assert context["kind"] == "pr"
    assert "## Pull Request Metadata" in context["metadata_block"]
    assert "- Base: main" in context["metadata_block"]
    assert "- Head: feat/helper" in context["metadata_block"]
    assert "- Labels: workflow" in context["metadata_block"]
    assert "- Diff: included" in context["metadata_block"]
    assert "## Pull Request Body" in context["context"]
    assert "## Pull Request Diff" in context["context"]
    assert "scripts/langchain/issue_pr_context.py" in context["context"]
