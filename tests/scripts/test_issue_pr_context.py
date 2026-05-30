from __future__ import annotations

import base64
import hashlib

from scripts.langchain.issue_pr_context import (
    ContextOptions,
    already_conformant,
    build_formatted_body_marker,
    build_issue_context,
    build_pr_context,
    estimate_tokens,
    main,
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
    assert "truncated:" in context["context"]
    assert len(context["formatted_body"]) < len(issue["body"])


def test_issue_context_handles_tiny_budget_without_overflow() -> None:
    issue = {
        "number": 123,
        "title": "Oversize metadata and body",
        "state": "open",
        "body": "body " * 100,
    }

    context = build_issue_context(issue, ContextOptions(token_budget=1))

    assert context["truncated"] is True
    assert context["estimated_tokens"] <= 1


def test_pr_context_caps_metadata_only_payload_without_looping() -> None:
    pr = {
        "number": 77,
        "title": "x" * 2000,
        "state": "open",
        "body": "body " * 500,
    }

    context = build_pr_context(pr, ContextOptions(token_budget=3))

    assert context["truncated"] is True
    assert context["estimated_tokens"] <= 3


def test_reuse_formatted_body_returns_embedded_marker_body() -> None:
    formatted = "## Tasks\n- [ ] Keep the formatted body\n"
    marker = build_formatted_body_marker(
        downstream_workflow="agents-auto-pilot",
        formatted_body=formatted,
    )
    issue = {"body": f"Raw body that should not be reused\n\n{marker}"}

    reused = reuse_formatted_body(issue, "agents-auto-pilot")

    assert reused == formatted
    assert '"sha256":"' in marker
    assert '": "' not in marker


def test_reuse_formatted_body_parses_marker_payload_with_braces() -> None:
    formatted = "## Tasks\n- [ ] Keep } in text\n"
    body_b64 = base64.b64encode(formatted.encode("utf-8")).decode("ascii")
    digest = hashlib.sha256(formatted.encode("utf-8")).hexdigest()
    marker = (
        "<!-- issue-pr-context:formatted-body:v1 "
        f'{{"body_b64":"{body_b64}","note":"value with }} brace","sha256":"{digest}",'
        '"workflow":"agents-auto-pilot"} -->'
    )

    assert reuse_formatted_body({"body": marker}, "agents-auto-pilot") == formatted


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


def test_reuse_formatted_body_ignores_malformed_embedded_body() -> None:
    marker = (
        "<!-- issue-pr-context:formatted-body:v1 "
        '{"body_b64":"abc","sha256":"bad","workflow":"agents-auto-pilot"} -->'
    )
    non_ascii_marker = (
        "<!-- issue-pr-context:formatted-body:v1 "
        '{"body_b64":"not-ascii-\u2603","workflow":"agents-auto-pilot"} -->'
    )

    assert reuse_formatted_body({"body": f"Raw body\n\n{marker}"}, "agents-auto-pilot") is None
    assert (
        reuse_formatted_body({"body": f"Raw body\n\n{non_ascii_marker}"}, "agents-auto-pilot")
        == "Raw body"
    )


def test_reuse_formatted_body_falls_back_to_cleaned_body_for_malformed_embed() -> None:
    marker = (
        "<!-- issue-pr-context:formatted-body:v1 "
        '{"body_b64":"abc","workflow":"agents-auto-pilot"} -->'
    )

    assert (
        reuse_formatted_body(
            {"body": f"{marker}\n## Tasks\n- [ ] Visible body"}, "agents-auto-pilot"
        )
        == "## Tasks\n- [ ] Visible body"
    )


def test_reuse_formatted_body_validates_embedded_body_hash() -> None:
    formatted = "## Tasks\n- [ ] Verify cached body\n"
    body_b64 = base64.b64encode(formatted.encode("utf-8")).decode("ascii")
    digest = hashlib.sha256(formatted.encode("utf-8")).hexdigest()
    marker = (
        "<!-- issue-pr-context:formatted-body:v1 "
        f'{{"body_b64":"{body_b64}","sha256":"{digest}","workflow":"agents-auto-pilot"}} -->'
    )
    stale_marker = marker.replace(digest, "0" * 64)

    assert reuse_formatted_body({"body": marker}, "agents-auto-pilot") == formatted
    assert reuse_formatted_body({"body": stale_marker}, "agents-auto-pilot") is None


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


def test_cli_outputs_json_payload(tmp_path, capsys) -> None:
    input_file = tmp_path / "issue.md"
    input_file.write_text("## Tasks\n- [ ] Use helper", encoding="utf-8")

    exit_code = main(
        [
            "--kind",
            "issue",
            "--input-file",
            str(input_file),
            "--token-budget",
            "100",
            "--downstream-workflow",
            "agents-auto-pilot",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"kind": "issue"' in captured.out
    assert "Use helper" in captured.out


# ---------------------------------------------------------------------------
# Anti-bloat: hash-only reuse marker + already_conformant guard
# ---------------------------------------------------------------------------

CONFORMANT_BODY = "\n".join(
    [
        "## Why",
        "",
        "Ship it.",
        "",
        "## Scope",
        "",
        "_Not provided._",
        "",
        "## Non-Goals",
        "",
        "_Not provided._",
        "",
        "## Tasks",
        "",
        "- [ ] do a thing",
        "",
        "## Acceptance Criteria",
        "",
        "- [ ] it works",
        "",
        "## Implementation Notes",
        "",
        "_Not provided._",
        "",
        "<details>",
        "<summary>Original Issue</summary>",
        "",
        "```text",
        "## Tasks",
        "- [ ] do a thing",
        "## Acceptance Criteria",
        "```",
        "</details>",
    ]
)


def test_build_marker_hash_only_omits_body_b64() -> None:
    """embed_body=False stores only the sha256, not a (size-doubling) base64 copy."""
    formatted = "## Tasks\n- [ ] keep it small\n"
    marker = build_formatted_body_marker(
        workflows=["agents-auto-pilot"],
        formatted_body=formatted,
        embed_body=False,
    )
    assert "body_b64" not in marker
    assert '"sha256":"' in marker


def test_hash_only_marker_round_trips_via_visible_body() -> None:
    """A hash-only marker validates against the visible body and returns it cleaned."""
    formatted = "## Tasks\n- [ ] keep it small\n## Acceptance Criteria\n- [ ] ok"
    marker = build_formatted_body_marker(
        workflows=["agents-auto-pilot"],
        formatted_body=formatted,
        embed_body=False,
    )
    body = f"{formatted}\n\n{marker}"
    assert reuse_formatted_body({"body": body}, "agents-auto-pilot") == formatted
    # A body edited after the marker was written fails the hash check (no false reuse).
    tampered = f"{formatted}\n- [ ] sneaky extra\n\n{marker}"
    assert reuse_formatted_body({"body": tampered}, "agents-auto-pilot") is None


def test_already_conformant_detects_full_template_with_original_block() -> None:
    assert already_conformant(CONFORMANT_BODY) is True


def test_already_conformant_ignores_headings_inside_original_block() -> None:
    """Headings inside the fenced Original-Issue block must not satisfy conformance."""
    # The fenced block contains '## Tasks'/'## Acceptance Criteria' but the visible
    # body has none -> not conformant.
    body = "\n".join(
        [
            "Some raw text",
            "",
            "<details>",
            "<summary>Original Issue</summary>",
            "",
            "```text",
            "## Why",
            "## Scope",
            "## Non-Goals",
            "## Tasks",
            "## Acceptance Criteria",
            "## Implementation Notes",
            "```",
            "</details>",
        ]
    )
    assert already_conformant(body) is False


def test_already_conformant_requires_all_sections_in_order() -> None:
    partial = "## Tasks\n- [ ] x\n## Acceptance Criteria\n- [ ] y"
    assert already_conformant(partial) is False


def test_already_conformant_original_issue_optional_flag() -> None:
    no_block = CONFORMANT_BODY.split("<details>")[0].rstrip()
    assert already_conformant(no_block) is False
    assert already_conformant(no_block, require_original_issue=False) is True


def test_already_conformant_handles_empty_and_none() -> None:
    assert already_conformant("") is False
    assert already_conformant(None) is False
