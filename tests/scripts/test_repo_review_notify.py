from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.repo_review_notify import (
    format_auto_labeled_section,
    format_docs_drift_section,
    format_needs_human_section,
    format_scorecard_section,
    load_backlog_scan,
    load_docs_drift_scan,
    load_queue,
    summarize_queue,
    summarize_scorecard,
    write_desktop_reminder,
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


@pytest.mark.parametrize("held,conflicts", [(1, 0), (0, 1)])
def test_held_approval_state_requires_review_on_both_surfaces(
    tmp_path, monkeypatch, held, conflicts
):
    from scripts import repo_review_notify as notify

    monkeypatch.setenv("HOME", str(tmp_path))
    queue = tmp_path / "queue.json"
    queue.write_text(
        json.dumps(
            {
                "issues": [],
                "held_approved_issues": [{}] * held,
                "approval_scope_conflicts": [{}] * conflicts,
                "upload_allowed": False,
            }
        )
    )
    notifications = []
    monkeypatch.setattr(notify, "display_notification", lambda **kw: notifications.append(kw))
    monkeypatch.setattr(
        "sys.argv", ["notify", "--output-dir", str(tmp_path), "--queue", str(queue)]
    )
    assert notify.main() == 0
    assert notifications[0]["title"] == "Repo-review: approvals remain held"
    assert "do not upload" in notifications[0]["message"]
    desktop = (tmp_path / "Desktop" / notify.DESKTOP_FILENAME).read_text()
    assert "Review approvals remain held" in desktop
    assert f"{held} approval(s), {conflicts} unresolved scope conflict(s)" in desktop
    assert "Clean week" not in desktop
    assert "--apply" not in desktop


def test_write_desktop_reminder_covers_clean_and_uploadable_states(
    tmp_path: Path, monkeypatch
) -> None:

    monkeypatch.setenv("HOME", str(tmp_path))
    clean = write_desktop_reminder(
        queue_summary={"total": 0, "by_repo": {}, "skipped_count": 0, "issue_titles": []},
        backlog={},
        docs_drift={},
        scorecard={},
        packet_path=tmp_path / "packet.md",
        queue_path=tmp_path / "queue.json",
        output_dir=tmp_path / "out",
        workflows_steward_root=tmp_path,
    )
    assert "Clean week" in clean.read_text(encoding="utf-8")

    uploadable = write_desktop_reminder(
        queue_summary={
            "total": 1,
            "by_repo": {"stranske/Workflows": 1},
            "skipped_count": 1,
            "issue_titles": ["Fix coverage"],
        },
        backlog={"needs_human": [{"repo": "x", "number": 1, "title": "Decide", "age_days": 8}]},
        docs_drift={},
        scorecard={},
        packet_path=tmp_path / "packet.md",
        queue_path=tmp_path / "queue.json",
        output_dir=tmp_path / "out",
        workflows_steward_root=tmp_path,
    )
    text = uploadable.read_text(encoding="utf-8")
    assert "1 issue ready to upload" in text
    assert "Next action — upload the queued issues" in text
    assert "1 repo decision(s) skipped" in text


def test_scorecard_summary_uses_bucket_fallback_and_empty_sections() -> None:
    assert summarize_scorecard({"by_repo": [{"findings": [{}, {}], "errors": [{}]}]}) == (2, 1)
    assert format_auto_labeled_section({}) == ""
    assert format_needs_human_section({}) == ""
    assert format_docs_drift_section({"by_repo": []}) == ""


def test_notification_and_scan_loaders_handle_best_effort_failures(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from scripts import repo_review_notify as notify

    missing = tmp_path / "missing.json"
    assert load_backlog_scan(None) == {"items": []}
    assert load_backlog_scan(missing) == {"items": []}
    assert load_docs_drift_scan(None) == {"by_repo": []}
    assert load_docs_drift_scan(missing) == {"by_repo": []}
    missing.write_text("{bad", encoding="utf-8")
    assert load_backlog_scan(missing) == {"items": []}
    assert load_docs_drift_scan(missing) == {"by_repo": []}

    monkeypatch.setattr(notify.shutil, "which", lambda _: None)
    notify.display_notification("title", "subtitle", "message")
    assert "not on PATH" in capsys.readouterr().err

    calls = []
    monkeypatch.setattr(notify.shutil, "which", lambda _: "/usr/bin/osascript")
    monkeypatch.setattr(
        notify.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs))
    )
    notify.display_notification('a"b', "sub", r"slash\\quote\"")
    assert calls[0][0][:2] == ["osascript", "-e"]
    assert '\\"' in calls[0][0][2]


def test_notification_ignores_os_error_and_reminder_falls_back_to_output_dir(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from scripts import repo_review_notify as notify

    monkeypatch.setattr(notify.shutil, "which", lambda _: "/usr/bin/osascript")
    monkeypatch.setattr(
        notify.subprocess, "run", lambda *_, **__: (_ for _ in ()).throw(OSError("no"))
    )
    notify.display_notification("title", "subtitle", "message")
    assert "osascript failed" in capsys.readouterr().err

    monkeypatch.setenv("HOME", str(tmp_path))
    original_mkdir = Path.mkdir

    def fail_desktop_mkdir(path: Path, **kwargs) -> None:
        if path.name == "Desktop":
            raise OSError("no desktop")
        original_mkdir(path, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_desktop_mkdir)
    target = notify.write_desktop_reminder(
        queue_summary={"total": 0, "by_repo": {}, "skipped_count": 0, "issue_titles": []},
        backlog={},
        docs_drift={},
        scorecard={},
        packet_path=tmp_path / "packet",
        queue_path=tmp_path / "queue",
        output_dir=tmp_path / "out",
        workflows_steward_root=tmp_path,
    )
    assert target == tmp_path / "out" / notify.DESKTOP_FILENAME


def test_scorecard_and_reminder_cover_error_and_decision_headlines(
    tmp_path: Path, monkeypatch
) -> None:
    rendered = format_scorecard_section(
        {
            "by_repo": [
                {"repo": "a/b", "errors": [{"error": "nope"}]},
                {
                    "repo": "c/d",
                    "findings": [
                        "bad",
                        {
                            "finding_id": "x",
                            "check": "Binary",
                            "score": 1,
                            "reason": "low",
                            "documentation_url": "https://docs",
                        },
                    ],
                },
            ]
        }
    )
    assert "Scan errors: 1" in rendered
    assert "**x**" in rendered and "https://docs" in rendered

    monkeypatch.setenv("HOME", str(tmp_path))
    common = {
        "packet_path": tmp_path / "packet",
        "queue_path": tmp_path / "queue",
        "output_dir": tmp_path / "out",
        "workflows_steward_root": tmp_path,
    }
    path = write_desktop_reminder(
        queue_summary={"total": 0, "by_repo": {}, "skipped_count": 0, "issue_titles": []},
        backlog={"needs_human": [{"repo": "a", "number": 1, "title": "x", "age_days": 8}]},
        docs_drift={
            "by_repo": [
                {
                    "repo": "a",
                    "drift_instances": [
                        {
                            "doc_path": "README.md",
                            "classification": "stale",
                            "claim": "old",
                            "authoritative_source": "docs/guide.md",
                        }
                    ],
                }
            ]
        },
        scorecard={},
        **common,
    )
    assert "backlog item and 1 doc-drift item need your decision" in path.read_text(
        encoding="utf-8"
    )
