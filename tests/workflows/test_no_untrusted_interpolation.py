"""Regression guard for free-text Actions values embedded in scripts.

Workflow expressions are evaluated before a shell or github-script body runs.
The listed values are free-form workflow-dispatch or runner inputs, so placing
them directly in a ``run:``/``with.script:`` body can turn quotes or shell
metacharacters into source code. They must cross that boundary through a
step-level ``env:`` value instead.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")

BANNED_FREE_TEXT_EXPRESSIONS = frozenset(
    {
        "inputs.commit_message",
        "inputs.codex_args",
        "inputs.repos",
        "inputs.target_repo",
        "inputs.commit_prefix",
        "inputs.head_repository",
    }
)

# Reviewed constrained-value script interpolations. Each tuple was triaged in
# docs/workflows/script-interpolation-triage.md (issue #3016). Free-text inputs
# above must use step-level env: indirection instead of appearing here.
REVIEWED_SCRIPT_INTERPOLATIONS = frozenset(
    {
        (
            ".github/workflows/agents-71-codex-belt-dispatcher.yml",
            "dispatch/step-3/run",
            "inputs.dry_run",
        ),
        (
            ".github/workflows/agents-71-codex-belt-dispatcher.yml",
            "dispatch/step-8/with.script",
            "inputs.agent_key",
        ),
        (
            ".github/workflows/agents-71-codex-belt-dispatcher.yml",
            "dispatch/step-8/with.script",
            "inputs.force_issue",
        ),
        (
            ".github/workflows/agents-72-codex-belt-worker.yml",
            "bootstrap/step-11/with.script",
            "inputs.max_parallel",
        ),
        (
            ".github/workflows/agents-72-codex-belt-worker.yml",
            "bootstrap/step-3/with.script",
            "inputs.dry_run",
        ),
        (
            ".github/workflows/agents-72-codex-belt-worker.yml",
            "bootstrap/step-3/with.script",
            "inputs.use_step_branch",
        ),
        (
            ".github/workflows/agents-72-codex-belt-worker.yml",
            "bootstrap/step-4/with.script",
            "inputs.agent_key",
        ),
        (
            ".github/workflows/agents-72-codex-belt-worker.yml",
            "bootstrap/step-4/with.script",
            "inputs.base",
        ),
        (
            ".github/workflows/agents-72-codex-belt-worker.yml",
            "bootstrap/step-4/with.script",
            "inputs.branch",
        ),
        (
            ".github/workflows/agents-72-codex-belt-worker.yml",
            "bootstrap/step-4/with.script",
            "inputs.issue",
        ),
        (
            ".github/workflows/agents-72-codex-belt-worker.yml",
            "bootstrap/step-4/with.script",
            "inputs.source",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "normalize/step-0/run",
            "inputs.agent_key",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-10/with.script",
            "inputs.pr_number",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-11/with.script",
            "inputs.branch",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-12/with.script",
            "inputs.issue",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-13/with.script",
            "inputs.issue",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-13/with.script",
            "inputs.pr_number",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-6/with.script",
            "inputs.branch",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-6/with.script",
            "inputs.issue",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-6/with.script",
            "inputs.pr_number",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-7/with.script",
            "inputs.branch",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-7/with.script",
            "inputs.issue",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-7/with.script",
            "inputs.pr_number",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-8/with.script",
            "inputs.head_sha",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-9/with.script",
            "inputs.pr_number",
        ),
        (
            ".github/workflows/agents-73-codex-belt-conveyor.yml",
            "promote/step-9/with.script",
            "steps.pr.outputs.issue || inputs.issue",
        ),
        (
            ".github/workflows/agents-auto-pilot.yml",
            "auto-pilot/step-13/with.script",
            "inputs.issue_number",
        ),
        (
            ".github/workflows/agents-bot-comment-handler.yml",
            "resolve/step-9/with.script",
            "inputs.pr_number",
        ),
        (
            ".github/workflows/agents-issue-optimizer.yml",
            "optimize_issue/step-0/run",
            "github.event.issue.number",
        ),
        (
            ".github/workflows/agents-issue-optimizer.yml",
            "optimize_issue/step-0/run",
            "github.event.issue.number",
        ),
        (
            ".github/workflows/agents-issue-optimizer.yml",
            "optimize_issue/step-0/run",
            "github.event.issue.number",
        ),
        (
            ".github/workflows/agents-issue-optimizer.yml",
            "optimize_issue/step-0/run",
            "github.event.issue.number",
        ),
        (
            ".github/workflows/agents-issue-optimizer.yml",
            "optimize_issue/step-0/run",
            "github.event.issue.number",
        ),
        (
            ".github/workflows/agents-issue-optimizer.yml",
            "optimize_issue/step-0/run",
            "github.event.issue.number",
        ),
        (
            ".github/workflows/agents-issue-optimizer.yml",
            "optimize_issue/step-0/run",
            "inputs.issue_number",
        ),
        (
            ".github/workflows/agents-keepalive-branch-sync.yml",
            "sync/step-10/run",
            "inputs.base_ref",
        ),
        (
            ".github/workflows/agents-pr-meta-v4.yml",
            "update_body/step-5/with.script",
            "inputs.pr_number || ''",
        ),
        (
            ".github/workflows/health-75-api-rate-diagnostic.yml",
            "generate-historical-report/step-2/run",
            "inputs.end_date",
        ),
        (
            ".github/workflows/health-75-api-rate-diagnostic.yml",
            "generate-historical-report/step-2/run",
            "inputs.start_date",
        ),
        (
            ".github/workflows/maint-45-cosmetic-repair.yml",
            "repair/step-4/run",
            "github.event.repository.default_branch",
        ),
        (".github/workflows/maint-52-sync-dev-versions.yml", "sync/step-4/run", "inputs.dry_run"),
        (".github/workflows/maint-52-sync-dev-versions.yml", "sync/step-4/run", "inputs.dry_run"),
        (".github/workflows/maint-52-sync-dev-versions.yml", "sync/step-5/run", "inputs.dry_run"),
        (".github/workflows/maint-65-sync-label-docs.yml", "sync/step-5/run", "inputs.dry_run"),
        (".github/workflows/maint-66-monthly-audit.yml", "audit/step-7/run", "inputs.create_issue"),
        (
            ".github/workflows/maint-66-monthly-audit.yml",
            "audit/step-7/run",
            "inputs.lookback_days || 30",
        ),
        (
            ".github/workflows/maint-68-sync-consumer-repos.yml",
            "prepare/step-4/run",
            "inputs.phase || 'canary'",
        ),
        (
            ".github/workflows/maint-68-sync-consumer-repos.yml",
            "summary/step-3/run",
            "inputs.dry_run || 'false'",
        ),
        (
            ".github/workflows/maint-69-sync-integration-repo.yml",
            "sync/step-9/run",
            "inputs.dry_run",
        ),
        (
            ".github/workflows/maint-71-auto-fix-integration.yml",
            "detect-and-fix/step-10/run",
            "github.event.issue.number || 'N/A'",
        ),
        (
            ".github/workflows/maint-71-auto-fix-integration.yml",
            "detect-and-fix/step-11/run",
            "github.event.issue.number",
        ),
        (
            ".github/workflows/maint-71-auto-fix-integration.yml",
            "detect-and-fix/step-12/run",
            "github.event.issue.number || 'N/A'",
        ),
        (
            ".github/workflows/maint-71-auto-fix-integration.yml",
            "detect-and-fix/step-2/run",
            "inputs.run_id",
        ),
        (
            ".github/workflows/maint-79-verifier-corpus-harvest.yml",
            "harvest/step-2/run",
            "inputs.write",
        ),
        (
            ".github/workflows/maint-80-langsmith-metrics-dashboard.yml",
            "generate-dashboard/step-10/run",
            "inputs.days_back || '7'",
        ),
        (
            ".github/workflows/maint-80-langsmith-metrics-dashboard.yml",
            "generate-dashboard/step-10/run",
            "inputs.days_back || '7'",
        ),
        (
            ".github/workflows/maint-80-langsmith-metrics-dashboard.yml",
            "generate-dashboard/step-11/run",
            "inputs.create_issue",
        ),
        (
            ".github/workflows/maint-80-langsmith-metrics-dashboard.yml",
            "generate-dashboard/step-3/run",
            "inputs.days_back || '7'",
        ),
        (
            ".github/workflows/maint-80-langsmith-metrics-dashboard.yml",
            "generate-dashboard/step-9/run",
            "inputs.days_back || '7'",
        ),
        (
            ".github/workflows/pr-00-gate.yml",
            "issue-consistency/step-1/run",
            "github.event.pull_request.base.ref",
        ),
        (
            ".github/workflows/pr-00-gate.yml",
            "issue-consistency/step-1/run",
            "github.event.pull_request.base.repo.full_name",
        ),
        (
            ".github/workflows/pr-00-gate.yml",
            "test-quality/step-1/run",
            "github.event.pull_request.base.ref",
        ),
        (
            ".github/workflows/pr-00-gate.yml",
            "test-quality/step-1/run",
            "github.event.pull_request.base.repo.full_name",
        ),
        (
            ".github/workflows/pr-00-gate.yml",
            "test-quality/step-4/run",
            "github.event.pull_request.base.ref",
        ),
        (
            ".github/workflows/pr-00-gate.yml",
            "test-quality/step-5/run",
            "github.event.pull_request.base.ref",
        ),
        (
            ".github/workflows/reusable-16-agents.yml",
            "readiness/step-6/run",
            "inputs.readiness_custom_logins",
        ),
        (".github/workflows/reusable-16-agents.yml", "readiness/step-6/run", "inputs.require_all"),
        (
            ".github/workflows/reusable-18-autofix.yml",
            "autofix/step-17/with.script",
            "inputs.clean_label",
        ),
        (
            ".github/workflows/reusable-11-ci-node.yml",
            "tests/step-2/run",
            "inputs.package-manager",
        ),
        (
            ".github/workflows/reusable-11-ci-node.yml",
            "tests/step-3/run",
            "inputs.package-manager",
        ),
        (
            ".github/workflows/reusable-11-ci-node.yml",
            "tests/step-4/run",
            "inputs.package-manager",
        ),
        (
            ".github/workflows/reusable-11-ci-node.yml",
            "tests/step-5/run",
            "inputs.package-manager",
        ),
        (
            ".github/workflows/reusable-11-ci-node.yml",
            "tests/step-6/run",
            "inputs.package-manager",
        ),
        (
            ".github/workflows/reusable-11-ci-node.yml",
            "tests/step-6/run",
            "inputs.test-runner",
        ),
        (
            ".github/workflows/reusable-70-orchestrator-main.yml",
            "keepalive-guard/step-4/run",
            "inputs.enable_keepalive",
        ),
        (
            ".github/workflows/reusable-agents-issue-bridge.yml",
            "bridge/step-12/with.script",
            "inputs.issue_number",
        ),
        (
            ".github/workflows/reusable-agents-issue-bridge.yml",
            "bridge/step-2/with.script",
            "inputs.issue_number",
        ),
        (
            ".github/workflows/reusable-agents-issue-bridge.yml",
            "bridge/step-7/with.script",
            "inputs.force_mode",
        ),
        (
            ".github/workflows/reusable-agents-issue-bridge.yml",
            "bridge/step-7/with.script",
            "inputs.mode",
        ),
        (
            ".github/workflows/reusable-agents-issue-bridge.yml",
            "bridge/step-8/with.script",
            "inputs.agent_pr_draft",
        ),
        (
            ".github/workflows/reusable-agents-issue-bridge.yml",
            "bridge/step-9/with.script",
            "inputs.post_agent_comment",
        ),
        (".github/workflows/reusable-agents-verifier.yml", "verifier/step-11/run", "inputs.mode"),
        (".github/workflows/reusable-agents-verifier.yml", "verifier/step-21/run", "inputs.model"),
        (
            ".github/workflows/reusable-agents-verifier.yml",
            "verifier/step-21/run",
            "inputs.provider",
        ),
        (".github/workflows/reusable-agents-verifier.yml", "verifier/step-27/run", "inputs.model"),
        (".github/workflows/reusable-agents-verifier.yml", "verifier/step-27/run", "inputs.model"),
        (".github/workflows/reusable-agents-verifier.yml", "verifier/step-27/run", "inputs.model2"),
        (".github/workflows/reusable-agents-verifier.yml", "verifier/step-27/run", "inputs.model2"),
        (".github/workflows/reusable-agents-verifier.yml", "verifier/step-31/run", "inputs.mode"),
        (".github/workflows/reusable-agents-verifier.yml", "verifier/step-31/run", "inputs.mode"),
        (
            ".github/workflows/reusable-backplane-conformance.yml",
            "conformance/step-6/run",
            "inputs.manifest_path",
        ),
        (
            ".github/workflows/reusable-backplane-conformance.yml",
            "conformance/step-6/run",
            "inputs.manifest_path",
        ),
        (
            ".github/workflows/reusable-backplane-conformance.yml",
            "conformance/step-6/run",
            "inputs.repo",
        ),
        (
            ".github/workflows/reusable-backplane-conformance.yml",
            "conformance/step-6/run",
            "inputs.run_json_path",
        ),
        (
            ".github/workflows/reusable-backplane-conformance.yml",
            "conformance/step-6/run",
            "inputs.strict",
        ),
        (
            ".github/workflows/reusable-bot-comment-handler.yml",
            "collect/step-10/with.script",
            "inputs.ignored_paths",
        ),
        (
            ".github/workflows/reusable-bot-comment-handler.yml",
            "collect/step-10/with.script",
            "inputs.pr_number",
        ),
        (
            ".github/workflows/reusable-bot-comment-handler.yml",
            "collect/step-11/with.script",
            "inputs.dry_run",
        ),
        (
            ".github/workflows/reusable-bot-comment-handler.yml",
            "collect/step-8/with.script",
            "inputs.pr_number",
        ),
        (
            ".github/workflows/reusable-bot-comment-handler.yml",
            "collect/step-9/with.script",
            "inputs.bot_authors",
        ),
        (
            ".github/workflows/reusable-bot-comment-handler.yml",
            "collect/step-9/with.script",
            "inputs.ignored_paths",
        ),
        (
            ".github/workflows/reusable-bot-comment-handler.yml",
            "collect/step-9/with.script",
            "inputs.pr_number",
        ),
        (
            ".github/workflows/reusable-bot-comment-handler.yml",
            "collect/step-9/with.script",
            "inputs.skip_if_human_replied",
        ),
        (
            ".github/workflows/reusable-bot-comment-handler.yml",
            "dispatch/step-6/with.script",
            "inputs.pr_number",
        ),
        (
            ".github/workflows/reusable-codex-run.yml",
            "codex/step-14/run",
            "inputs.codex_cli_version",
        ),
        (".github/workflows/reusable-cursor-run.yml", "cursor/step-1/run", "inputs.mode"),
        (".github/workflows/reusable-cursor-run.yml", "cursor/step-1/run", "inputs.pr_number"),
        (
            ".github/workflows/reusable-pr-context.yml",
            "fetch/step-4/with.script",
            "inputs.pr_number",
        ),
    }
)

# Backward-compatible alias used by helper tests below.
UNTRUSTED_EXPRESSIONS = frozenset({"inputs.commit_message", "inputs.codex_args", "inputs.repos"})


def _workflow_paths() -> Iterable[Path]:
    for pattern in WORKFLOW_GLOBS:
        yield from sorted(ROOT.glob(pattern))


def _script_values(path: Path) -> Iterable[tuple[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for job_name, job in (data.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for index, step in enumerate(job.get("steps") or []):
            if not isinstance(step, dict):
                continue
            run = step.get("run")
            if isinstance(run, str):
                yield f"{job_name}/step-{index}/run", run
            script = (step.get("with") or {}).get("script")
            if isinstance(script, str):
                yield f"{job_name}/step-{index}/with.script", script


def _actions_expression_bodies(script: str) -> Iterable[str]:
    """Yield Actions expression bodies without ending quoted brace literals early."""

    start = 0
    while (opening := script.find("${{", start)) != -1:
        index = opening + 3
        quote: str | None = None
        escaped = False
        while index < len(script) - 1:
            character = script[index]
            if quote:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
            elif character in {"'", '"'}:
                quote = character
            elif script[index : index + 2] == "}}":
                yield script[opening + 3 : index]
                start = index + 2
                break
            index += 1
        else:
            start = opening + 3


def _normalize_expression(body: str) -> str:
    normalized = re.sub(r"\s+", " ", body.strip())
    # Keep reviewed-inventory keys stable when equivalent indexed Actions
    # context access is used (for example, inputs['dry-run']).
    return re.sub(r"\[\s*['\"]([A-Za-z0-9_-]+)['\"]\s*\]", r".\1", normalized)


def _is_banned_free_text(body: str) -> bool:
    normalized = _normalize_expression(body)
    return any(
        re.search(
            rf"\binputs\s*(?:\.\s*{re.escape(banned.split('.', maxsplit=1)[1])}\b|"
            rf"\[\s*['\"]{re.escape(banned.split('.', maxsplit=1)[1])}['\"]\s*\])",
            normalized,
        )
        for banned in BANNED_FREE_TEXT_EXPRESSIONS
    )


def _script_interpolation_hits(script: str) -> list[str]:
    return [
        _normalize_expression(body)
        for body in _actions_expression_bodies(script)
        if re.search(
            r"\binputs\s*(?:\.|\[)|" r"\bgithub\s*(?:\.\s*event\b|\[\s*['\"]event['\"]\s*\])",
            body,
        )
    ]


def _references_untrusted_input(body: str, expression: str) -> bool:
    """Recognize equivalent property and bracket references in an expression."""

    _, property_name = expression.split(".", maxsplit=1)
    return bool(
        re.search(
            rf"\binputs\s*(?:\.\s*{re.escape(property_name)}\b|\[\s*['\"]{re.escape(property_name)}['\"]\s*\])",
            body,
        )
    )


def _untrusted_references(script: str) -> list[str]:
    """Return free-text inputs referenced anywhere in Actions expressions."""

    expression_bodies = list(_actions_expression_bodies(script))
    return sorted(
        expression
        for expression in UNTRUSTED_EXPRESSIONS
        if any(_references_untrusted_input(body, expression) for body in expression_bodies)
    )


def test_no_untrusted_expressions_in_script_bodies() -> None:
    """Every inputs./github.event. script interpolation must be reviewed or banned."""

    banned_violations: list[str] = []
    unreviewed: list[str] = []
    for workflow in _workflow_paths():
        rel = str(workflow.relative_to(ROOT))
        for location, script in _script_values(workflow):
            for expression in _script_interpolation_hits(script):
                key = (rel, location, expression)
                if _is_banned_free_text(expression):
                    banned_violations.append(f"{rel}:{location}: {expression}")
                elif key not in REVIEWED_SCRIPT_INTERPOLATIONS:
                    unreviewed.append(f"{rel}:{location}: {expression}")

    messages: list[str] = []
    if banned_violations:
        messages.append(
            "Pass free-text workflow values through step env and consume the env "
            "variable in the script:\n" + "\n".join(banned_violations)
        )
    if unreviewed:
        messages.append(
            "Add each reviewed constrained interpolation to "
            "REVIEWED_SCRIPT_INTERPOLATIONS (see docs/workflows/script-"
            "interpolation-triage.md):\n" + "\n".join(unreviewed)
        )
    assert not messages, "\n\n".join(messages)


@pytest.mark.parametrize(
    ("body", "expression", "expected"),
    [
        ("inputs.commit_message", "inputs.commit_message", True),
        ("inputs['commit_message']", "inputs.commit_message", True),
        ("inputs.repos || 'all'", "inputs.repos", True),
        ("inputs['repos']", "inputs.repos", True),
        ("inputs.codex_args", "inputs.codex_args", True),
        ("inputs.safe_field", "inputs.commit_message", False),
    ],
)
def test_references_untrusted_input(body: str, expression: str, expected: bool) -> None:
    assert _references_untrusted_input(body, expression) is expected


@pytest.mark.parametrize("expression", sorted(UNTRUSTED_EXPRESSIONS))
def test_untrusted_expression_guard_detects_listed_inputs(expression: str) -> None:
    """Each listed field must be detectable via _untrusted_references."""

    property_name = expression.split(".", 1)[1]
    dot_form = f"echo ${{{{ inputs.{property_name} }}}}"
    bracket_form = f"echo ${{{{ inputs['{property_name}'] }}}}"
    assert expression in _untrusted_references(dot_form)
    assert expression in _untrusted_references(bracket_form)


def test_untrusted_expression_guard_matches_default_and_wrapper_forms() -> None:
    assert _untrusted_references("echo ${{ inputs.repos || 'all' }}") == ["inputs.repos"]
    assert _untrusted_references("const v = '${{ format('{0}', inputs.codex_args) }}';") == [
        "inputs.codex_args"
    ]
    assert _untrusted_references("echo ${{ inputs['repos'] }}") == ["inputs.repos"]
    assert _untrusted_references("${{ format('{{prefix}} {0}', inputs.codex_args) }}") == [
        "inputs.codex_args"
    ]


@pytest.mark.parametrize(
    "script",
    [
        "echo ${{ inputs['commit_message'] }}",
        "echo ${{ github['event']['issue']['title'] }}",
        "echo ${{ github['event'].issue['title'] }}",
    ],
)
def test_script_interpolation_hits_detects_indexed_context_forms(script: str) -> None:
    assert _script_interpolation_hits(script)


def test_script_interpolation_hits_normalizes_indexed_context_keys() -> None:
    assert _script_interpolation_hits("echo ${{ inputs['commit_message'] }}") == [
        "inputs.commit_message"
    ]
    assert _script_interpolation_hits("echo ${{ github['event']['issue']['title'] }}") == [
        "github.event.issue.title"
    ]


@pytest.mark.parametrize(
    "expression",
    [
        "format('{0}', inputs.codex_args)",
        "contains(inputs['repos'], 'all')",
    ],
)
def test_banned_free_text_detects_wrapper_and_indexed_forms(expression: str) -> None:
    assert _is_banned_free_text(expression)
