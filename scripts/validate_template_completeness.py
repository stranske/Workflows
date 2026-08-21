#!/usr/bin/env python3
"""Validate that workflow templates are complete.

This script checks for workflows in .github/workflows/ that appear to be
intended for consumer repos but are missing from the template directory
and/or sync manifest.

The goal is to catch the case where someone adds a workflow to Workflows
that should also be synced to consumer repos, but forgets to add it to
the template and manifest.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

# Workflows that are ONLY for the Workflows repo (not for consumers)
# These are intentionally not synced
WORKFLOWS_ONLY = {
    # Maintenance workflows specific to Workflows repo
    "maint-52-sync-dev-versions.yml",
    "maint-68-sync-consumer-repos.yml",
    "maint-post-ci.yml",
    # Health checks specific to Workflows repo
    "health-68-consumer-sync-drift.yml",
    "health-70-validate-sync-manifest.yml",
    "health-71-sync-health-check.yml",
    "health-72-template-lint.yml",
    "health-75-api-rate-diagnostic.yml",
    "health-76-codex-cli-freshness.yml",
    # Debug/testing workflows
    "agents-debug-issue-event.yml",
    "agents-model-profile-trial.yml",  # Workflows-owned remote trial transport
    # Internal dispatch handlers
    "agents-keepalive-branch-sync.yml",
    "agents-keepalive-dispatch-handler.yml",
    # Workflows repo specific features
    "agents-weekly-metrics.yml",
    "agents-moderate-connector.yml",
    # Older versions superseded in consumer repos
    "agents-63-issue-intake.yml",  # consumers have agents-issue-intake.yml
    "agents-64-verify-agent-assignment.yml",  # verification is different
    "agents-70-orchestrator.yml",  # consumers have agents-orchestrator.yml
    "agents-pr-meta-v4.yml",  # consumers have agents-80-pr-event-hub.yml
    # First-party workflows retained in Workflows; consumer templates use
    # agents-80-pr-event-hub.yml and agents-81-gate-followups.yml instead.
    "agents-autofix-loop.yml",
    "agents-bot-comment-handler.yml",
    "agents-keepalive-loop.yml",
    "agents-verify-to-issue-v2.yml",
    # Reusable workflows called FROM Workflows only
    "reusable-agents-verifier.yml",
    "reusable-codex-run.yml",
    "reusable-10-ci-python.yml",
    "reusable-18-autofix.yml",
    "reusable-pr-context.yml",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that workflows intended for consumers are in the template"
    )
    parser.add_argument(
        "--workflows-dir",
        default=".github/workflows",
        help="Path to Workflows repo workflows directory",
    )
    parser.add_argument(
        "--template-dir",
        default="templates/consumer-repo/.github/workflows",
        help="Path to template workflows directory",
    )
    parser.add_argument(
        "--manifest",
        default=".github/sync-manifest.yml",
        help="Path to sync manifest",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error if any issues found",
    )
    parser.add_argument(
        "--source",
        default="template-completeness",
        help="Identifier for the calling workflow (used in summary output)",
    )
    return parser.parse_args()


def get_workflows(directory: Path) -> set[str]:
    """Get all workflow files in a directory."""
    if not directory.exists():
        return set()
    return {f.name for f in directory.glob("*.yml")}


def get_manifest_workflows(manifest_path: Path) -> set[str]:
    """Get consumer workflow targets listed in the sync manifest."""
    if not manifest_path.exists():
        return set()

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    workflows = set()

    for entry in manifest.get("workflows", []) or []:
        source = entry.get("source", "")
        if not source:
            continue
        target = entry.get("target", source)
        if target.startswith(".github/workflows/"):
            workflows.add(target.replace(".github/workflows/", ""))

    return workflows


def is_consumer_workflow(workflow_path: Path) -> bool:
    """Heuristically determine if a workflow should be synced to consumers.

    A workflow is likely intended for consumers if it:
    - Is an agents-* workflow (agent system)
    - Is an autofix* workflow
    - Is a ci.yml or pr-00-gate.yml (core CI)
    - References consumer repo patterns

    A workflow is NOT for consumers if it:
    - Is a maint-* or health-* workflow (Workflows maintenance)
    - Is a reusable-* workflow (called by other workflows)
    - Is explicitly in WORKFLOWS_ONLY
    """
    name = workflow_path.name

    # Explicit exclusions
    if name in WORKFLOWS_ONLY:
        return False

    # Patterns that indicate consumer workflows
    consumer_patterns = [
        r"^agents-(?!debug|weekly|moderate)",  # agents-* except debug/weekly/moderate
        r"^autofix",  # autofix workflows
        r"^ci\.yml$",  # main CI
        r"^pr-00-gate\.yml$",  # gate workflow
        r"^dependabot",  # dependabot config
        r"^list-llm-models\.yml$",  # helper workflow
    ]

    # Patterns that indicate Workflows-only
    workflows_only_patterns = [
        r"^maint-",  # maintenance workflows
        r"^health-",  # health checks
        r"^reusable-",  # reusable workflows
        r"debug",  # debug workflows
    ]

    if any(re.search(pattern, name) for pattern in workflows_only_patterns):
        return False

    return any(re.search(pattern, name) for pattern in consumer_patterns)


def write_summary(issues: list[str], source: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write(f"## Template Completeness Check ({source})\n\n")
        handle.write(f"**Issues Found:** {len(issues)}\n\n")
        for issue in issues:
            handle.write(f"- {issue}\n")


def main() -> int:
    args = parse_args()

    workflows_dir = Path(args.workflows_dir)
    template_dir = Path(args.template_dir)
    manifest_path = Path(args.manifest)

    if not workflows_dir.exists():
        print(f"::error::Workflows directory not found: {workflows_dir}")
        return 1

    workflows = get_workflows(workflows_dir)
    template_workflows = get_workflows(template_dir)
    manifest_workflows = get_manifest_workflows(manifest_path)

    issues = []

    # Check for workflows that should be in template but aren't
    for workflow in sorted(workflows):
        workflow_path = workflows_dir / workflow

        if not is_consumer_workflow(workflow_path):
            continue

        in_template = workflow in template_workflows
        in_manifest = workflow in manifest_workflows

        if not in_template:
            issues.append(
                f"MISSING FROM TEMPLATE: {workflow} - exists in .github/workflows/ "
                f"but not in templates/consumer-repo/.github/workflows/"
            )

        if not in_manifest and in_template:
            issues.append(
                f"MISSING FROM MANIFEST: {workflow} - exists in template "
                f"but not listed in sync-manifest.yml workflows section"
            )

    # Check for workflows in template but not in manifest
    for workflow in sorted(template_workflows):
        already_reported = workflow in [i.split(":")[1].strip().split()[0] for i in issues]
        if workflow not in manifest_workflows and not already_reported:
            issues.append(
                f"TEMPLATE NOT IN MANIFEST: {workflow} - exists in template "
                f"but not listed in sync-manifest.yml"
            )

    # Report results
    if issues:
        print("## Template Completeness Issues\n")
        for issue in issues:
            print(f"- {issue}")
            print(f"::warning::{issue}")

        print(f"\nTotal issues: {len(issues)}")

        # Write to summary if available
        write_summary(issues, args.source)

        if args.strict:
            return 1
    else:
        print("✅ All consumer workflows are properly templated and manifested")
        write_summary([], args.source)

    return 0


if __name__ == "__main__":
    sys.exit(main())
