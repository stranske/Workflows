import json
from pathlib import Path

from scripts import repo_review_evaluator as evaluator


def test_split_issue_entries_accepts_common_heading_shapes() -> None:
    text = """1. First title
Tasks
- [ ] one

Issue 2 — Second title
Tasks
- [x] done

3) Third title
- [ ] open
"""

    entries = evaluator.split_issue_entries(text)

    assert [entry[0] for entry in entries] == [1, 2, 3]
    assert entries[0][1] == "First title"
    assert entries[1][1] == "Second title"
    assert entries[2][1] == "Third title"


def test_extract_issue_drafts_only_returns_entries_with_open_tasks(tmp_path: Path) -> None:
    issues = tmp_path / "Issues.txt"
    issues.write_text(
        """1. Open work
- [ ] do it
- [x] started

2. Done work
- [x] finished
""",
        encoding="utf-8",
    )

    drafts = evaluator.extract_issue_drafts(issues)

    assert len(drafts) == 1
    assert drafts[0].title == "Open work"
    assert drafts[0].open_tasks == 1
    assert drafts[0].done_tasks == 1


def test_extract_issue_drafts_ignores_commented_template_skeleton(tmp_path: Path) -> None:
    issues = tmp_path / "Issues.txt"
    issues.write_text(
        """# Example skeleton
# 1) Title
# - [ ] <task>
#
2) Real work
- [ ] task
""",
        encoding="utf-8",
    )

    drafts = evaluator.extract_issue_drafts(issues)

    assert len(drafts) == 1
    assert drafts[0].number == 2
    assert drafts[0].title == "Real work"


def test_load_registry_filters_excluded_repo_names_and_duplicates(tmp_path: Path) -> None:
    registry = tmp_path / "config" / "repo_review_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "workspace_root": "..",
                "excluded_repo_names": ["collab-deliverables"],
                "repos": [
                    {
                        "repo": "owner/keep",
                        "local_path": "keep",
                        "status": "active",
                        "cadence": "weekly",
                    },
                    {
                        "repo": "owner/keep",
                        "local_path": "keep-copy",
                        "status": "paused",
                    },
                    {
                        "repo": "owner/collab-deliverables",
                        "local_path": "collab-deliverables",
                        "status": "active",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    _workspace, _excluded, repos, _archive_paths = evaluator.load_registry(registry)

    assert [repo.repo for repo in repos] == ["owner/keep"]
    assert repos[0].status == "active"


def test_collect_repo_state_marks_issue_queue_productive(tmp_path: Path) -> None:
    repo_dir = tmp_path / "demo"
    repo_dir.mkdir()
    (repo_dir / "Issues.txt").write_text("1. Draft\n- [ ] task\n", encoding="utf-8")
    config = evaluator.RepoConfig(
        repo="owner/demo",
        local_path="demo",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )

    state = evaluator.collect_repo_state(tmp_path, config)

    assert state["decision"] == "productive"
    assert state["issue_draft_count"] == 1
    assert state["issue_open_task_count"] == 1


def test_material_status_lines_filters_generated_cache_noise() -> None:
    lines = [
        " M .venv/lib/python3.12/site-packages/example.pyc",
        " M src/pension_data/db/strategy.py",
        " M docs/reports/issue_completion_queue.tsv",
        "?? workloop-state.md",
        "?? tests/__pycache__/test_example.cpython-312.pyc",
    ]

    assert evaluator.material_status_lines(lines) == [" M src/pension_data/db/strategy.py"]


def test_run_git_preserves_status_leading_columns(tmp_path: Path) -> None:
    subprocess = evaluator.subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test User"], check=True)
    tracked = repo / "docs" / "reports" / "issue_completion_queue.tsv"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", str(tracked)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "initial"], check=True, capture_output=True
    )

    tracked.write_text("two\n", encoding="utf-8")

    assert evaluator.run_git(repo, ["status", "--short"]).splitlines() == [
        " M docs/reports/issue_completion_queue.tsv"
    ]


def test_archive_candidates_make_clean_repo_productive(tmp_path: Path) -> None:
    repo_dir = tmp_path / "trip-planner"
    repo_dir.mkdir()
    subprocess = evaluator.subprocess
    subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
    config = evaluator.RepoConfig(
        repo="stranske/trip-planner",
        local_path="trip-planner",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )
    candidate = evaluator.ArchiveCandidate(
        title="Add failing acceptance tests before implementation",
        source_file="/tmp/session.jsonl",
        thread_name="Planner review",
        timestamp="2026-04-19T00:00:00Z",
        excerpt="1. Add failing acceptance tests before implementation.",
    )

    state = evaluator.collect_repo_state(tmp_path, config, [candidate])

    assert state["decision"] == "productive"
    assert state["issue_draft_count"] == 0
    assert state["archive_candidate_count"] == 1


def test_collect_archive_candidates_reads_review_sessions(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    session = archive_dir / "session.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"timestamp": "2026-04-19T00:00:00Z"},
                    }
                ),
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "thread_name_updated",
                            "thread_name": "Planner review",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "user_message",
                            "message": (
                                "Please evaluate the state of trip-planner against the original design. "
                                "What work remains before testing?"
                            ),
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "agent_message",
                            "message": ("1. Add inventory acceptance tests before implementation."),
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = evaluator.RepoConfig(
        repo="stranske/trip-planner",
        local_path="trip-planner",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )

    candidates = evaluator.collect_archive_candidates([archive_dir], [config])

    assert candidates["stranske/trip-planner"][0].title == (
        "Add inventory acceptance tests before implementation"
    )


def test_archive_candidates_are_matched_to_candidate_repo_terms(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    session = archive_dir / "session.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "user_message",
                            "message": (
                                "Please evaluate the state of the codebase for the repos "
                                "after the most recent issue set."
                            ),
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "agent_message",
                            "message": (
                                "1. Add planner end-to-end tests for the conversation panel.\n"
                                "2. Add Manager Database RAG alert coverage."
                            ),
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    trip = evaluator.RepoConfig(
        repo="stranske/trip-planner",
        local_path="trip-planner",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )
    manager = evaluator.RepoConfig(
        repo="stranske/Manager-Database",
        local_path="Manager-Database",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )

    candidates = evaluator.collect_archive_candidates([archive_dir], [trip, manager])

    assert [item.title for item in candidates["stranske/trip-planner"]] == [
        "Add planner end-to-end tests for the conversation panel"
    ]
    assert [item.title for item in candidates["stranske/Manager-Database"]] == [
        "Add Manager Database RAG alert coverage"
    ]
