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


def test_collect_repo_state_marks_issue_queue_as_review_input(tmp_path: Path) -> None:
    repo_dir = tmp_path / "demo"
    repo_dir.mkdir()
    (repo_dir / "Issues.txt").write_text("1. Draft\n- [ ] task\n", encoding="utf-8")
    (repo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
    config = evaluator.RepoConfig(
        repo="owner/demo",
        local_path="demo",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )

    state = evaluator.collect_repo_state(tmp_path, config)

    assert state["review_status"] == evaluator.EXECUTED_REVIEW_STATUS
    assert state["issue_queue_status"] == "draft candidates present"
    assert state["issue_draft_count"] == 1
    assert state["issue_open_task_count"] == 1
    assert state["design_files"] == ["README.md"]


def test_material_status_lines_filters_generated_cache_noise() -> None:
    lines = [
        "?? .gitnexus/",
        " M .venv/lib/python3.12/site-packages/example.pyc",
        " M src/pension_data/db/strategy.py",
        " M docs/reports/issue_completion_queue.tsv",
        "?? workloop-state.md",
        "?? tests/__pycache__/test_example.cpython-312.pyc",
    ]

    assert evaluator.material_status_lines(lines) == [" M src/pension_data/db/strategy.py"]


def test_collect_repo_state_uses_profile_and_gitnexus_meta(tmp_path: Path) -> None:
    repo_dir = tmp_path / "demo"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess = evaluator.subprocess
    subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    head = evaluator.run_git(repo_dir, ["rev-parse", "HEAD"])
    gitnexus_dir = repo_dir / ".gitnexus"
    gitnexus_dir.mkdir()
    (gitnexus_dir / "meta.json").write_text(
        json.dumps(
            {
                "lastCommit": head,
                "indexedAt": "2026-04-26T00:00:00Z",
                "stats": {"files": 3, "nodes": 12, "processes": 2},
            }
        ),
        encoding="utf-8",
    )
    config = evaluator.RepoConfig(
        repo="owner/demo",
        local_path="demo",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )

    state = evaluator.collect_repo_state(
        tmp_path,
        config,
        review_profile={
            "progress_summary": "Demo-specific progress.",
            "readiness_summary": "Demo-specific readiness.",
            "review_focus": ["Check the demo workflow."],
            "concerns": ["Avoid generic summaries."],
        },
    )

    assert state["gitnexus_map"]["status"] == "current"
    assert state["decision_brief"]["progress_summary"] == "Demo-specific progress."
    assert state["decision_brief"]["review_focus"] == ["Check the demo workflow."]


def test_gitnexus_preflight_reports_stale_without_refresh(tmp_path: Path) -> None:
    repo_dir = tmp_path / "demo"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess = evaluator.subprocess
    subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    gitnexus_dir = repo_dir / ".gitnexus"
    gitnexus_dir.mkdir()
    (gitnexus_dir / "meta.json").write_text(
        json.dumps({"lastCommit": "older", "stats": {"files": 1}}),
        encoding="utf-8",
    )
    config = evaluator.RepoConfig(
        repo="owner/demo",
        local_path="demo",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )

    result = evaluator.gitnexus_preflight(
        tmp_path,
        [config],
        {"active"},
        refresh_stale=False,
        gitnexus_bin="missing-gitnexus-bin",
    )

    assert result["records"]["owner/demo"]["before"]["status"] == "stale"
    assert result["records"]["owner/demo"]["refresh_status"] == "needed-not-requested"
    assert "owner/demo GitNexus map is stale" in result["warnings"][0]


def test_title_from_recommendation_prefers_concise_first_sentence() -> None:
    title = evaluator.title_from_recommendation(
        "Add a cross-repo TPP smoke test. Start Travel-Plan-Permission, configure "
        "trip-planner, submit a business proposal, poll status, and assert persisted state."
    )

    assert title == "Add a cross-repo TPP smoke test"
    assert "..." not in title


def test_candidate_goal_text_uses_title_not_full_local_draft_body() -> None:
    candidate = {
        "type": "local draft",
        "title": "CI: actually execute the LangGraph path",
        "body": """Issue 3 — CI: actually execute the LangGraph path
Why

The current smoke test forces prefer_langgraph=False.
""",
    }

    assert evaluator.candidate_goal_text(candidate) == "CI: actually execute the LangGraph path"


def test_feedback_title_patterns_are_stable_when_candidate_indexes_shift() -> None:
    candidates = [
        {"candidate_index": 1, "title": "CI: actually execute the LangGraph path"},
        {"candidate_index": 2, "title": "Workflow alignment with Workflows repo snapshot"},
        {"candidate_index": 5, "title": "Rebase or restart Travel-Plan-Permission from main"},
    ]
    decision = {
        "approved_candidates": [1, 2, 5],
        "approved_title_patterns": ["^CI:"],
        "dropped_title_patterns": ["^Workflow alignment", "^Rebase or restart"],
    }

    assert evaluator.approved_candidate_indexes(decision, 5, {}, candidates) == {1}
    assert evaluator.dropped_candidate_indexes(decision, candidates) == {2, 5}


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


def test_archive_candidates_make_clean_repo_review_pending(tmp_path: Path) -> None:
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

    assert state["review_status"] == evaluator.EXECUTED_REVIEW_STATUS
    assert state["issue_queue_status"] == "draft candidates present"
    assert state["issue_draft_count"] == 0
    assert state["archive_candidate_count"] == 1


def test_collect_repo_state_marks_clean_active_repo_review_pending(tmp_path: Path) -> None:
    repo_dir = tmp_path / "manager"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Manager\n", encoding="utf-8")
    subprocess = evaluator.subprocess
    subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    config = evaluator.RepoConfig(
        repo="owner/manager",
        local_path="manager",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )

    state = evaluator.collect_repo_state(tmp_path, config)

    assert state["review_status"] == evaluator.EXECUTED_REVIEW_STATUS
    assert state["issue_queue_status"] == "no current draft candidates"
    assert state["decision"] == evaluator.EXECUTED_REVIEW_STATUS
    assert state["review_execution"]["status"] == "executed"
    assert state["review_execution"]["gap_count"] >= 1


def test_issues_txt_changes_are_helper_inputs_not_review_blockers(tmp_path: Path) -> None:
    repo_dir = tmp_path / "intake"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Intake\n", encoding="utf-8")
    (repo_dir / "Issues.txt").write_text("# helper\n", encoding="utf-8")
    subprocess = evaluator.subprocess
    subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md", "Issues.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    (repo_dir / "Issues.txt").write_text("# helper\n# local note\n", encoding="utf-8")
    config = evaluator.RepoConfig(
        repo="owner/intake",
        local_path="intake",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )

    state = evaluator.collect_repo_state(tmp_path, config)

    assert state["review_status"] == evaluator.EXECUTED_REVIEW_STATUS
    assert state["helper_dirty_count"] == 1
    assert state["review_blocking_dirty_count"] == 0
    assert state["helper_dirty_preview"] == [" M Issues.txt"]


def test_gitnexus_ignore_change_is_helper_input_not_review_blocker(tmp_path: Path) -> None:
    repo_dir = tmp_path / "planner"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Planner\n", encoding="utf-8")
    (repo_dir / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    subprocess = evaluator.subprocess
    subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    (repo_dir / ".gitignore").write_text("node_modules/\n.gitnexus\n", encoding="utf-8")
    config = evaluator.RepoConfig(
        repo="owner/planner",
        local_path="planner",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )

    state = evaluator.collect_repo_state(tmp_path, config)

    assert state["review_status"] == evaluator.EXECUTED_REVIEW_STATUS
    assert state["helper_dirty_count"] == 1
    assert state["review_blocking_dirty_count"] == 0
    assert state["helper_dirty_preview"] == [" M .gitignore"]


def test_write_repo_artifacts_emits_standard_design_review(tmp_path: Path) -> None:
    repo_dir = tmp_path / "demo"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
    config = evaluator.RepoConfig(
        repo="owner/demo",
        local_path="demo",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )
    state = evaluator.collect_repo_state(tmp_path, config)
    output_dir = tmp_path / "out"

    evaluator.write_repo_artifacts(output_dir, state, max_drafts=8)

    review = output_dir / "repos" / "owner__demo" / "design-review.md"
    execution = output_dir / "repos" / "owner__demo" / "review-execution.md"
    brief = output_dir / "repos" / "owner__demo" / "decision-brief.md"
    assert review.is_file()
    assert execution.is_file()
    assert brief.is_file()
    text = review.read_text(encoding="utf-8")
    assert "Standard Design Review" in text
    assert "Design Contract" in text
    assert "Issue Generation Gate" in text
    execution_text = execution.read_text(encoding="utf-8")
    assert "Review Execution" in execution_text
    assert "Dimension Findings" in execution_text
    brief_text = brief.read_text(encoding="utf-8")
    assert "Current Progress Compared With Design" in brief_text
    assert "Readiness For Testing Or Live Implementation" in brief_text
    assert "Candidate Issue Set" in brief_text


def test_write_packet_embeds_substantive_decision_brief(tmp_path: Path) -> None:
    repo_dir = tmp_path / "demo"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
    (repo_dir / "Issues.txt").write_text(
        "1. Add smoke coverage\n- [ ] cover the happy path\n", encoding="utf-8"
    )
    config = evaluator.RepoConfig(
        repo="owner/demo",
        local_path="demo",
        status="active",
        cadence="weekly",
        decision_anchor="demo anchor",
    )
    state = evaluator.collect_repo_state(tmp_path, config)
    output_dir = tmp_path / "out"

    evaluator.write_packet(output_dir, [state], generated_on="2026-04-26")

    packet = (output_dir / "human-decision-packet.md").read_text(encoding="utf-8")
    assert "Current Progress Compared With Design" in packet
    assert "Readiness For Testing Or Live Implementation" in packet
    assert "Candidate Issue Set" in packet
    assert "Add smoke coverage" in packet
    assert "decision: approve | revise | defer | drop | deeper-review" in packet


def test_approved_issue_queue_formats_agent_ready_issues_and_drops_feedback_items(
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "Travel-Plan-Permission"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# TPP\n", encoding="utf-8")
    (repo_dir / "Issues.txt").write_text(
        """1. Keep approved repo-local work
- [ ] implement approved behavior

2. Route workflow sync elsewhere
- [ ] update workflow sync policy
""",
        encoding="utf-8",
    )
    config = evaluator.RepoConfig(
        repo="stranske/Travel-Plan-Permission",
        local_path="Travel-Plan-Permission",
        status="active",
        cadence="weekly",
        decision_anchor="approval workflow",
    )
    state = evaluator.collect_repo_state(
        tmp_path,
        config,
        review_profile={
            "progress_summary": "TPP has implementation surfaces and needs operational proof.",
            "readiness_summary": "TPP needs LangGraph and transport smoke coverage before live confidence.",
        },
    )
    feedback = {
        "generated_on": "2026-04-26",
        "defaults": {"approved_candidates": "all"},
        "routing_rules": ["Route workflow maintenance to Workflows."],
        "decisions": {
            "stranske/Travel-Plan-Permission": {
                "decision": "approve",
                "priority": "high",
                "approved_candidates": [1],
                "dropped_candidates": [2],
                "notes": "Candidate 2 belongs in Workflows.",
            }
        },
    }

    queue = evaluator.build_approved_issue_queue([state], feedback, "2026-04-26")

    assert [item["candidate_index"] for item in queue["issues"]] == [1]
    assert queue["issues"][0]["priority"] == "high"
    assert queue["issues"][0]["body_valid"] is True
    assert "## Acceptance Criteria" in queue["issues"][0]["body"]
    assert queue["dropped_candidates"][0]["candidate_index"] == 2


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
