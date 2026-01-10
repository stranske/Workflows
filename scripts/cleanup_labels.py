#!/usr/bin/env python3
"""Label cleanup script for consumer repos.

This script audits and removes bloat labels from consumer repos.
It requires human approval before actually deleting labels.

Usage:
    # Audit mode (dry run) - lists labels to remove
    python cleanup_labels.py --repo owner/repo --audit

    # Execute mode - actually removes labels (requires --confirm)
    python cleanup_labels.py --repo owner/repo --execute --confirm

    # Audit all consumer repos
    python cleanup_labels.py --all-repos --audit
"""

import argparse
import json
import os
import sys
from typing import NamedTuple

# Try to import github, fall back to instructions
try:
    from github import Github
except ImportError:
    print("ERROR: PyGithub not installed. Run: pip install PyGithub")
    sys.exit(1)


class LabelInfo(NamedTuple):
    """Information about a label."""

    name: str
    color: str
    description: str


# Canonical labels that have workflow effects - DO NOT REMOVE
FUNCTIONAL_LABELS = {
    # Agent assignment
    "agent:codex",
    "agent:claude",
    "agent:copilot",
    "agent:needs-attention",
    "agent:decompose",
    "agent:optimize",
    "agents",
    # Issue formatting
    "agents:format",
    "agents:formatted",
    "agents:optimize",
    "agents:apply-suggestions",
    # Auto-pilot (end-to-end automation)
    "agents:auto-pilot",
    "agents:auto-pilot-pause",
    "agents:auto-pilot-failed",
    # PR control
    "agents:allow-change",
    "agents:keepalive",
    "agents:keepalive-nudge",
    "agents:activated",
    "agents:paused",
    # Autofix - all variants used by reusable-18-autofix.yml
    "autofix",
    "autofix:clean",
    "autofix:clean-only",
    "autofix:bot-comments",
    "autofix:applied",
    "autofix:patch",
    "autofix:escalated",
    "autofix:debt",
    "needs-autofix-review",
    # Merge control
    "automerge",
    "from:codex",
    "from:copilot",
    "risk:low",
    "ci:green",
    # Issue states
    "codex-ready",
    "needs-human",
    # Verification
    "verify:checkbox",
    "verify:evaluate",
    "verify:compare",
    "verify:create-issue",
    # Workflow markers
    "sync",
    "automated",
    "coverage",
    "follow-up",
    # Phase 3 labels
    "agents:decompose",
    "needs-formatting",
    # CI/Integration markers
    "ci-failure",
    "integration-failure",
    "integration-sync",
    "integration-test",
    # Allow guard bypass
    "allow-agents-guard",
}

# Standard informational labels - keep for categorization
INFORMATIONAL_LABELS = {
    "bug",
    "enhancement",
    "documentation",
    "duplicate",
    "wontfix",
    "good first issue",
    "help wanted",
    "invalid",
    "question",
    # Common categorization labels (useful for human triage)
    "security",
    "performance",
    "dependencies",
    "testing",
    "refactor",
    "cleanup",
    "maintenance",
    "feature",
    # Area/component labels
    "ci",
    "devops",
    "infra",
    "config",
    "docs",
    "automation",
    "workflows",
    "langchain",
    "pipeline",
    "logging",
    "data",
    "exports",
    # Priority labels (various formats)
    "priority: high",
    "priority: low",
    "priority: medium",
    "priority:high",
    # Risk labels
    "risk:medium",
    "risk:high",
    "risk:major",
    "risk:minor",
    # Status labels
    "status: ready",
    "status: in-progress",
    "status:ready",
    "status:in-progress",
    # Health labels
    "health:coverage",
    "health:repo",
    # Other useful markers
    "guardrail",
    "reliability",
    "usability",
    "versioning",
    "reminder",
    "auth-expiring",
    "phase-1",
    "test",
    "validation",
    # GitHub/Actions related
    "github:actions",
    # Component/area labels (common patterns)
    "app",
    "engine",
    "ui",
    "backend",
    "cli",
    "frontend",
    # Tech/language labels
    "javascript",
    "python",
    "typescript",
    # Domain-specific but common
    "metrics",
    "modeling",
    "schema",
    "build",
    "lint",
    "observability",
    "llm",
    "research",
}

# Labels verified as bloat - safe to remove
BLOAT_LABELS = {
    "codex",  # Redundant with agent:codex
    "agents:pause",  # Consolidated to agents:paused
    "ai:agent",  # Unused
    "auto-merge-audit",  # Unused
    "automerge:ok",  # Unused variant
}

# Consumer repos to audit
CONSUMER_REPOS = [
    "stranske/Manager-Database",
    "stranske/Template",
    "stranske/trip-planner",
    "stranske/Travel-Plan-Permission",
    "stranske/Portable-Alpha-Extension-Model",
    "stranske/Trend_Model_Project",
    "stranske/Collab-Admin",
]


def get_github_client() -> Github:
    """Get authenticated GitHub client."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN environment variable not set")
        sys.exit(1)
    return Github(token)


def get_repo_labels(gh: Github, repo_name: str) -> list[LabelInfo]:
    """Get all labels from a repository."""
    repo = gh.get_repo(repo_name)
    labels = []
    for label in repo.get_labels():
        labels.append(
            LabelInfo(name=label.name, color=label.color, description=label.description or "")
        )
    return labels


def classify_label(label_name: str) -> str:
    """Classify a label as functional, informational, bloat, or idiosyncratic."""
    if label_name in FUNCTIONAL_LABELS:
        return "functional"
    if label_name in INFORMATIONAL_LABELS:
        return "informational"
    if label_name in BLOAT_LABELS:
        return "bloat"
    return "idiosyncratic"


def audit_repo(gh: Github, repo_name: str) -> dict:
    """Audit a repository's labels and classify them."""
    print(f"\n{'=' * 60}")
    print(f"Auditing: {repo_name}")
    print("=" * 60)

    labels = get_repo_labels(gh, repo_name)

    results = {
        "repo": repo_name,
        "total_labels": len(labels),
        "functional": [],
        "informational": [],
        "bloat": [],
        "idiosyncratic": [],
    }

    for label in labels:
        category = classify_label(label.name)
        results[category].append(label.name)

    # Print summary
    print(f"\nTotal labels: {len(labels)}")
    print(f"  Functional (keep): {len(results['functional'])}")
    print(f"  Informational (keep): {len(results['informational'])}")
    print(f"  Bloat (remove): {len(results['bloat'])}")
    print(f"  Idiosyncratic (review): {len(results['idiosyncratic'])}")

    if results["bloat"]:
        print("\n⚠️  BLOAT LABELS TO REMOVE:")
        for name in results["bloat"]:
            print(f"    - {name}")

    if results["idiosyncratic"]:
        print("\n📋 IDIOSYNCRATIC LABELS (require human review):")
        for name in results["idiosyncratic"]:
            print(f"    - {name}")

    return results


def remove_labels(gh: Github, repo_name: str, labels_to_remove: list[str], confirm: bool) -> dict:
    """Remove labels from a repository."""
    if not confirm:
        print("\n❌ Execution requires --confirm flag")
        return {"removed": [], "errors": []}

    repo = gh.get_repo(repo_name)
    removed = []
    errors = []

    for label_name in labels_to_remove:
        try:
            label = repo.get_label(label_name)
            label.delete()
            removed.append(label_name)
            print(f"  ✅ Removed: {label_name}")
        except Exception as e:
            errors.append({"label": label_name, "error": str(e)})
            print(f"  ❌ Failed to remove {label_name}: {e}")

    return {"removed": removed, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Audit and clean up labels in consumer repos")
    parser.add_argument("--repo", help="Single repo to audit (format: owner/repo)")
    parser.add_argument("--all-repos", action="store_true", help="Audit all consumer repos")
    parser.add_argument(
        "--audit", action="store_true", help="Audit mode - only report, don't modify"
    )
    parser.add_argument("--execute", action="store_true", help="Execute mode - remove bloat labels")
    parser.add_argument(
        "--confirm", action="store_true", help="Required for execute mode - confirms deletion"
    )
    parser.add_argument(
        "--include-idiosyncratic",
        action="store_true",
        help="Also remove idiosyncratic labels (requires explicit list)",
    )
    parser.add_argument(
        "--remove-labels", nargs="+", help="Specific labels to remove (for idiosyncratic cleanup)"
    )
    parser.add_argument("--output-json", help="Output results to JSON file")

    args = parser.parse_args()

    if not args.audit and not args.execute:
        parser.error("Must specify --audit or --execute")

    if not args.repo and not args.all_repos:
        parser.error("Must specify --repo or --all-repos")

    gh = get_github_client()

    repos = CONSUMER_REPOS if args.all_repos else [args.repo]
    all_results = []

    for repo_name in repos:
        if args.audit:
            results = audit_repo(gh, repo_name)
            all_results.append(results)

        elif args.execute:
            # First audit to get labels
            results = audit_repo(gh, repo_name)

            # Determine what to remove
            labels_to_remove = list(results["bloat"])

            if args.include_idiosyncratic and args.remove_labels:
                # Only remove specified idiosyncratic labels
                for label in args.remove_labels:
                    if label in results["idiosyncratic"]:
                        labels_to_remove.append(label)

            if labels_to_remove:
                print(f"\n🗑️  Removing {len(labels_to_remove)} labels from {repo_name}:")
                removal_results = remove_labels(gh, repo_name, labels_to_remove, args.confirm)
                results["removal"] = removal_results
            else:
                print(f"\n✅ No bloat labels to remove from {repo_name}")

            all_results.append(results)

    # Output summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_bloat = sum(len(r["bloat"]) for r in all_results)
    total_idiosyncratic = sum(len(r["idiosyncratic"]) for r in all_results)

    print(f"Repos audited: {len(all_results)}")
    print(f"Total bloat labels: {total_bloat}")
    print(f"Total idiosyncratic labels: {total_idiosyncratic}")

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nResults saved to: {args.output_json}")


if __name__ == "__main__":
    main()
