from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOTS = (
    REPO_ROOT / ".github" / "actions",
    REPO_ROOT / ".github" / "scripts",
    REPO_ROOT / ".github" / "workflows",
    REPO_ROOT / "templates" / "consumer-repo" / ".github",
)


def _automation_sources() -> list[Path]:
    suffixes = {".js", ".py", ".sh", ".yaml", ".yml"}
    return sorted(
        path
        for root in AUTOMATION_ROOTS
        for path in root.rglob("*")
        if path.is_file() and path.suffix in suffixes
    )


DRAFT_ASSIGNMENT = re.compile(r"\bdraft[ \t]*:[ \t]*([^\r\n]*)")


def _has_non_false_draft_value(text: str) -> bool:
    for match in DRAFT_ASSIGNMENT.finditer(text):
        value = re.split(r"[,#}\]]", match.group(1), maxsplit=1)[0].strip()
        if value and value != "false":
            return True
    return False


def test_non_false_draft_matcher_catches_quoted_and_dynamic_values() -> None:
    for value in ("true", "'true'", '"true"', "${{ inputs.draft }}", "inputs.draft"):
        assert _has_non_false_draft_value(f"draft: {value},")

    assert not _has_non_false_draft_value("draft: false,")
    assert not _has_non_false_draft_value("draft: false # invariant")
    assert not _has_non_false_draft_value("draft:\n  description: compatibility input")


def test_automation_never_creates_or_restages_draft_pull_requests() -> None:
    violations: list[str] = []

    for path in _automation_sources():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(REPO_ROOT)
        if "--draft" in text:
            violations.append(f"{relative}: uses gh pr create --draft")
        if "convertPullRequestToDraft" in text:
            violations.append(f"{relative}: converts a ready PR back to draft")
        if ("pulls.create" in text or "gh pr create" in text) and _has_non_false_draft_value(text):
            violations.append(f"{relative}: supplies a non-false draft value")

    assert not violations, "\n".join(violations)


def test_pr_creators_state_the_ready_for_review_invariant() -> None:
    bootstrap = (
        REPO_ROOT / ".github" / "actions" / "codex-bootstrap-lite" / "action.yml"
    ).read_text(encoding="utf-8")
    bridge = (REPO_ROOT / ".github" / "workflows" / "reusable-agents-issue-bridge.yml").read_text(
        encoding="utf-8"
    )
    sync = (REPO_ROOT / ".github" / "workflows" / "maint-68-sync-consumer-repos.yml").read_text(
        encoding="utf-8"
    )

    assert "draft: false" in bootstrap
    assert "inputs.draft" not in bootstrap
    assert "inputs.auto_ready" not in bootstrap
    assert "draft: false" in bridge
    assert "sync:delivery-staging" in sync
    assert 'gh pr merge "$pr_number" --disable-auto' in sync


def test_reused_automation_pull_requests_are_recovered_to_ready() -> None:
    bridge = (REPO_ROOT / ".github" / "workflows" / "reusable-agents-issue-bridge.yml").read_text(
        encoding="utf-8"
    )
    sync = (REPO_ROOT / ".github" / "workflows" / "maint-68-sync-consumer-repos.yml").read_text(
        encoding="utf-8"
    )

    reused_pr = bridge.index("let pr = existing.data[0];")
    ready_guard = bridge.index("if (pr?.draft)", reused_pr)
    ready_mutation = bridge.index("markPullRequestReadyForReview", ready_guard)
    body_mutation = bridge.index("github.rest.pulls.update", ready_mutation)
    assert reused_pr < ready_guard < ready_mutation < body_mutation
    assert "{ id: pr.node_id }" in bridge[ready_guard:body_mutation]
    assert "pullRequest.isDraft" in bridge[ready_guard:body_mutation]

    hold_function = sync.index("hold_ready_pr()")
    ready_command = sync.index('gh pr ready "$pr_number"', hold_function)
    first_label_mutation = sync.index('gh pr edit "$existing_pr" --add-label', ready_command)
    assert hold_function < ready_command < first_label_mutation


def test_legacy_draft_inputs_are_inert_and_absent_from_operator_ui() -> None:
    bridge = (REPO_ROOT / ".github" / "workflows" / "reusable-agents-issue-bridge.yml").read_text(
        encoding="utf-8"
    )
    reusable_agents = (REPO_ROOT / ".github" / "workflows" / "reusable-16-agents.yml").read_text(
        encoding="utf-8"
    )
    intake = (REPO_ROOT / ".github" / "workflows" / "agents-63-issue-intake.yml").read_text(
        encoding="utf-8"
    )
    template_intake = (
        REPO_ROOT
        / "templates"
        / "consumer-repo"
        / ".github"
        / "workflows"
        / "agents-issue-intake.yml"
    ).read_text(encoding="utf-8")
    resolver = (REPO_ROOT / ".github" / "scripts" / "agents_orchestrator_resolve.js").read_text(
        encoding="utf-8"
    )

    assert "inputs.agent_pr_draft" not in bridge
    assert "inputs.draft_pr" not in reusable_agents
    dispatch_inputs = intake.split("workflow_dispatch:", 1)[1].split("workflow_call:", 1)[0]
    assert "bridge_draft_pr" not in dispatch_inputs
    assert "bridge_draft_pr" not in template_intake
    assert "merged.draft_pr" not in resolver
    assert "draft_pr: 'false'" in resolver


def test_consumer_setup_uses_current_ready_for_review_topology() -> None:
    checklist = (
        REPO_ROOT / "templates" / "consumer-repo" / "docs" / "SETUP_CHECKLIST.md"
    ).read_text(encoding="utf-8")
    retired_tokens = (
        "agents-63",
        "Agents 63",
        "agents-70-orchestrator.yml",
        "agents-pr-meta.yml",
        "agents-orchestrator.yml",
        "agents-keepalive-loop.yml",
        "PR Meta",
        "pr_meta_comment",
        "allow_replay",
        "raw.githubusercontent.com/stranske/Workflows/v1",
        "@v1",
    )
    affirmative_draft_instruction = re.compile(
        r"(?<!non-)(?<!no )(?<!not )\bdraft\s+(?:PR|pull request)\b",
        re.IGNORECASE,
    )

    assert not [token for token in retired_tokens if token in checklist]
    assert affirmative_draft_instruction.search(checklist) is None
    assert "Verify a ready-for-review PR is opened linking to the issue" in checklist
    assert "agents-81-gate-followups.yml" in checklist
    assert "Keepalive Sweep re-enters the Agents 81 evaluation" in checklist
    assert checklist.count("both `agent:codex` and `agents:keepalive` labels") == 2

    user_guide = (REPO_ROOT / "templates" / "consumer-repo" / "WORKFLOW_USER_GUIDE.md").read_text(
        encoding="utf-8"
    )
    assert "PR Meta" not in user_guide
    assert affirmative_draft_instruction.search(user_guide) is None
    assert "opens a ready-for-review PR" in user_guide
