from __future__ import annotations

import json
from pathlib import Path

from scripts.repo_review_notify import (
    format_auto_labeled_section,
    format_docs_drift_section,
    format_needs_human_section,
    load_queue,
    summarize_queue,
)


def test_load_queue_returns_empty_queue_for_missing_file(tmp_path: Path) -> None:
    assert load_queue(tmp_path / "missing-queue.json") == {"issues": [], "skipped": []}


def test_load_queue_returns_empty_queue_for_malformed_json(tmp_path: Path) -> None:
    queue = tmp_path / "approved-issue-queue.json"
    queue.write_text("{not valid json", encoding="utf-8")

    assert load_queue(queue) == {"issues": [], "skipped": []}


def test_load_queue_reads_valid_queue_file(tmp_path: Path) -> None:
    queue = tmp_path / "approved-issue-queue.json"
    payload = {
        "issues": [{"repo": "stranske/Workflows", "title": "Add notification formatter tests"}],
        "skipped": [{"repo": "stranske/Template", "reason": "defer"}],
    }
    queue.write_text(json.dumps(payload), encoding="utf-8")

    assert load_queue(queue) == payload


def test_summarize_queue_counts_repos_titles_and_skipped_items() -> None:
    summary = summarize_queue(
        {
            "issues": [
                {"repo": "stranske/Workflows", "title": "First"},
                {"repo": "stranske/Workflows", "title": "Second"},
                {"repo": "stranske/Template", "title": "Third"},
            ],
            "skipped": [
                {"repo": "stranske/Ready", "reason": "no-new-work"},
                {"repo": "stranske/Fine-Art-Archive", "reason": "defer"},
            ],
        }
    )

    assert summary["total"] == 3
    assert summary["by_repo"] == {
        "stranske/Template": 1,
        "stranske/Workflows": 2,
    }
    assert summary["skipped_count"] == 2
    assert summary["issue_titles"] == ["First", "Second", "Third"]


def test_format_auto_labeled_section_uses_applied_wording() -> None:
    rendered = format_auto_labeled_section(
        {
            "apply_mode": True,
            "auto_labeled": [
                {
                    "repo": "stranske/Workflows",
                    "number": 2615,
                    "title": "Add repo-review notification formatter tests",
                    "age_days": 11,
                    "applied_priority": "priority:normal",
                    "applied": True,
                }
            ],
        }
    )

    assert "Auto-labeled this week (1 item)" in rendered
    assert "These were auto-labeled by the cron" in rendered
    assert "stranske/Workflows#2615" in rendered
    assert "**normal**" in rendered
    assert "dry-run; not yet applied" not in rendered
    assert "WOULD be auto-labeled" not in rendered


def test_format_auto_labeled_section_uses_dry_run_wording() -> None:
    rendered = format_auto_labeled_section(
        {
            "apply_mode": False,
            "auto_labeled": [
                {
                    "repo": "stranske/Workflows",
                    "number": 2615,
                    "title": "Add repo-review notification formatter tests",
                    "age_days": 11,
                    "applied_priority": "priority:low",
                    "applied": False,
                }
            ],
        }
    )

    assert "These WOULD be auto-labeled if the cron ran with --apply" in rendered
    assert "the labels are NOT on the issues yet" in rendered
    assert "stranske/Workflows#2615" in rendered
    assert "**low** _(dry-run; not yet applied)_" in rendered


def test_format_needs_human_section_renders_exact_decision_commands() -> None:
    rendered = format_needs_human_section(
        {
            "stale_days_threshold": 14,
            "needs_human": [
                {
                    "repo": "stranske/Workflows",
                    "number": 2615,
                    "title": "Add repo-review notification formatter tests",
                    "age_days": 22,
                    "url": "https://github.com/stranske/Workflows/issues/2615",
                    "surface_reason": "umbrella-shaped issue",
                    "labels": ["enhancement", "blocked", "agents"],
                }
            ],
        }
    )

    assert "Backlog needing your decision (1 item)" in rendered
    assert "### stranske/Workflows#2615: Add repo-review notification formatter tests" in rendered
    assert (
        "Promote: `gh issue edit 2615 --repo stranske/Workflows " "--add-label priority:normal`"
    ) in rendered
    assert (
        "Deprioritize: `gh issue edit 2615 --repo stranske/Workflows " "--add-label priority:low`"
    ) in rendered
    assert (
        "Close: `gh issue close 2615 --repo stranske/Workflows --comment "
        '"Out of scope; closing per backlog scan."`'
    ) in rendered


def test_format_docs_drift_section_bundles_one_remediation_per_drifting_repo() -> None:
    rendered = format_docs_drift_section(
        {
            "by_repo": [
                {
                    "repo": "stranske/Workflows",
                    "drift_instances": [
                        {
                            "doc_path": "README.md",
                            "claim": "Consumers use a retired pin.",
                            "authoritative_source": "docs/INTEGRATION_GUIDE.md",
                            "classification": "stale",
                        },
                        {
                            "doc_path": "docs/ci/WORKFLOWS.md",
                            "claim": "The active workflow roster omits a gate.",
                            "authoritative_source": ".github/workflows/pr-00-gate.yml",
                            "classification": "contradictory",
                        },
                    ],
                    "errors": [],
                },
                {
                    "repo": "stranske/Template",
                    "drift_instances": [
                        {
                            "doc_path": "docs/SETUP_CHECKLIST.md",
                            "claim": "A setup step names the wrong workflow.",
                            "authoritative_source": "templates/consumer-repo/.github/workflows",
                            "classification": "stale",
                        }
                    ],
                    "errors": [],
                },
            ]
        }
    )

    assert "Doc drift detected (2 repos)" in rendered
    assert rendered.count("gh issue create --repo stranske/Workflows") == 1
    assert rendered.count("gh issue create --repo stranske/Template") == 1
    assert "README.md" in rendered
    assert "docs/ci/WORKFLOWS.md" in rendered
    assert "- [ ] README.md" in rendered
    assert "- [ ] docs/ci/WORKFLOWS.md" in rendered


def test_format_docs_drift_section_surfaces_error_only_buckets_without_issue_command() -> None:
    rendered = format_docs_drift_section(
        {
            "by_repo": [
                {
                    "repo": "stranske/Workflows",
                    "drift_instances": [],
                    "errors": [
                        {"doc_path": "docs/ops/LOCAL_LANES.md", "error": "claude unavailable"},
                        {"doc_path": "docs/ops/GITNEXUS.md", "error": "timeout"},
                    ],
                }
            ]
        }
    )

    assert "Doc-drift scan errors (1 repo)" in rendered
    assert "**stranske/Workflows**: 2 doc(s) errored" in rendered
    assert "gh issue create --repo stranske/Workflows" not in rendered
