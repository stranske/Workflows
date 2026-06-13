import json
from pathlib import Path

from scripts import repo_review_evaluator as evaluator

VALID_ISSUE_BODY = """## Why

Travel-Plan-Permission needs CI to execute the LangGraph path so orchestration coverage cannot pass by skipping the graph.

## Scope

- Install the orchestration extra in one deterministic CI/test path.
- Execute `run_policy_graph(..., prefer_langgraph=True)` against a small fixture plan.

## Non-Goals

- Do not expand every graph failure branch.
- Do not require live external services.

## Tasks

- [ ] Inspect `tests/python/test_langgraph_ci_gate.py` and `src/travel_plan_permission/orchestration/graph.py`.
- [ ] Add or update a pytest that imports LangGraph and runs `prefer_langgraph=True`.
- [ ] Update the repo-local CI command so the orchestration extra is installed for this test path.
- [ ] Document the exact local or CI command that proves LangGraph coverage.

## Acceptance Criteria

- [ ] The LangGraph-path test is not always skipped in the documented CI/test path.
- [ ] A broken graph compile or invocation causes a deterministic test failure.
- [ ] The PR notes the exact command or CI job used to prove the path.

## Implementation Notes

Relevant files: `pyproject.toml`, `.github/workflows/ci.yml`, `src/travel_plan_permission/orchestration/graph.py`, `tests/python/test_langgraph_ci_gate.py`.
"""

VALID_REVIEW_TRACE = {
    "candidate_title_patterns": [
        "^Keep approved repo-local work$",
        "^Add planner end-to-end tests$",
    ],
    "gap": "The reviewed workflow lacks executable proof for the intended path.",
    "current_state": "Implementation paths exist, but the acceptance path is not proved by the current tests.",
    "required_change": "Add the targeted smoke or CI gate named by the candidate issue.",
    "design_refs": ["README.md", "docs/design.md"],
    "implementation_refs": ["src/travel_plan_permission/orchestration/graph.py"],
    "test_refs": ["tests/python/test_langgraph_ci_gate.py"],
}


def _make_round1_candidate(
    title: str, *, body: str | None = None, tasks: list[str] | None = None
) -> dict[str, object]:
    return {
        "title": title,
        "gap": "Specific design commitment unmet.",
        "current_state": "Today's code/tests do not prove the gap is closed.",
        "required_change": "Add the targeted change described by this candidate.",
        "design_refs": ["README.md"],
        "implementation_refs": ["src/example.py"],
        "test_refs": ["tests/test_example.py"],
        "acceptance_criteria": ["Test fails before fix and passes after."],
        "non_goals": ["Do not bundle unrelated cleanup."],
        "tasks": tasks or ["First task", "Second task"],
        "priority": "normal",
        "confidence": "high",
        "body": body,
    }


def _make_round1_findings(
    repo: str,
    *,
    candidates: list[dict[str, object]] | None = None,
    agent: str = "codex",
) -> dict[str, object]:
    return {
        "agent": agent,
        "repo": repo,
        "design_summary": (
            f"{repo} is intended to deliver concrete product/workflow behavior; "
            "the design summary is repo-specific."
        ),
        "implementation_classification": [
            {
                "piece": "primary code path",
                "status": "partial",
                "evidence": ["src/example.py"],
            }
        ],
        "readiness_summary": (
            "Readiness depends on a specific test/smoke gate that this repo does not "
            "currently demonstrate."
        ),
        "remote_progress_check": "Reviewed open issues + recent merged PRs; no overlap.",
        "archive_dedup_check": "Reviewed archive entries; no overlap.",
        "candidates": candidates or [],
        "no_new_work_justification": "",
        "deeper_review_needed": False,
        "deeper_review_reason": "",
    }


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


def test_collect_repo_state_ignores_issues_txt_as_candidate_source(tmp_path: Path) -> None:
    """Issues.txt is template scratch; it must not produce candidate state.

    Under the new design Issues.txt is ignored as a candidate source. Without
    a round-1 findings file the issue queue status is "round 1 not yet run",
    regardless of whether Issues.txt exists.
    """
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

    state = evaluator.collect_repo_state(tmp_path, config, remote_progress={})

    assert state["review_status"] == evaluator.EXECUTED_REVIEW_STATUS
    assert state["issue_queue_status"] == "round 1 not yet run"
    assert state["issue_draft_count"] == 0
    assert state["issue_open_task_count"] == 0
    assert state["round1_findings"] is None
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
            "review_evidence_traces": [VALID_REVIEW_TRACE],
        },
    )

    assert state["gitnexus_map"]["status"] == "current"
    assert state["decision_brief"]["progress_summary"] == "Demo-specific progress."
    assert state["decision_brief"]["review_focus"] == ["Check the demo workflow."]
    assert state["decision_brief"]["review_quality_status"] == "pass"


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
    assert "owner/demo GitNexus map needs refresh (stale)" in result["warnings"][0]


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


def test_archive_entries_are_dedup_signal_not_candidates(tmp_path: Path) -> None:
    """Archive entries are progress-recognition signal only.

    Under the new design, archive entries from prior review sessions are
    surfaced as `archive_progress` (for the round-1 reviewer to use as dedup
    against already-discussed/already-shipped work) but they do NOT make the
    issue queue status "draft candidates present" — only round-1 findings do.
    """
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

    state = evaluator.collect_repo_state(tmp_path, config, [candidate], remote_progress={})

    assert state["review_status"] == evaluator.EXECUTED_REVIEW_STATUS
    assert state["issue_queue_status"] == "round 1 not yet run"
    assert state["issue_draft_count"] == 0
    assert state["archive_progress_count"] == 1
    assert state["archive_candidate_count"] == 1  # backward-compat alias
    assert state["round1_findings"] is None


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

    state = evaluator.collect_repo_state(tmp_path, config, remote_progress={})

    assert state["review_status"] == evaluator.EXECUTED_REVIEW_STATUS
    assert state["issue_queue_status"] == "round 1 not yet run"
    assert state["decision"] == evaluator.EXECUTED_REVIEW_STATUS
    assert state["review_execution"]["status"] == "executed"
    assert state["review_execution"]["gap_count"] >= 1
    assert state["decision_brief"]["review_quality_status"] == "fail"
    assert state["decision_brief"]["review_quality_errors"]


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
    assert "Process Chain Checkpoint" in text
    assert "earliest failed stage" in text
    assert "Required Review Evidence Trace" in text
    assert "review_evidence_traces" in text
    assert "candidate_title_patterns" in text
    assert "Issue Generation Gate" in text
    assert "matching `review_evidence_traces` record" in text
    execution_text = execution.read_text(encoding="utf-8")
    assert "Review Execution" in execution_text
    assert "Dimension Findings" in execution_text
    brief_text = brief.read_text(encoding="utf-8")
    assert "Review Quality Gate" in brief_text
    assert "Current Progress Compared With Design" in brief_text
    assert "Readiness For Testing Or Live Implementation" in brief_text
    assert "Candidate Issue Set" in brief_text


def test_write_packet_embeds_substantive_decision_brief(tmp_path: Path) -> None:
    """Packet embeds round-1 candidate titles when round-1 findings exist."""
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
    findings = _make_round1_findings(
        "owner/demo",
        candidates=[_make_round1_candidate("Add smoke coverage")],
    )
    state = evaluator.collect_repo_state(
        tmp_path, config, round1_findings=findings, remote_progress={}
    )
    output_dir = tmp_path / "out"

    evaluator.write_packet(output_dir, [state], generated_on="2026-04-26")

    packet = (output_dir / "human-decision-packet.md").read_text(encoding="utf-8")
    assert "Current Progress Compared With Design" in packet
    assert "Review quality gate: `fail`" in packet
    assert "process-chain checkpoint" in packet
    assert "Fix the earliest upstream cause" in packet
    assert "write a `review_evidence_traces` record" in packet
    assert "Review evidence traces:" in packet
    assert "Readiness For Testing Or Live Implementation" in packet
    assert "Candidate Issue Set" in packet
    assert "Add smoke coverage" in packet
    assert "approval prerequisite: add matching review_evidence_traces" in packet
    assert "decision: approve | revise | defer | drop | deeper-review" in packet


def test_approved_issue_queue_formats_agent_ready_issues_and_drops_feedback_items(
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "Travel-Plan-Permission"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# TPP\n", encoding="utf-8")
    config = evaluator.RepoConfig(
        repo="stranske/Travel-Plan-Permission",
        local_path="Travel-Plan-Permission",
        status="active",
        cadence="weekly",
        decision_anchor="approval workflow",
    )
    findings = _make_round1_findings(
        "stranske/Travel-Plan-Permission",
        candidates=[
            _make_round1_candidate("Keep approved repo-local work", body=VALID_ISSUE_BODY),
            _make_round1_candidate("Route workflow sync elsewhere"),
        ],
    )
    state = evaluator.collect_repo_state(
        tmp_path,
        config,
        review_profile={
            "progress_summary": "TPP has implementation surfaces and needs operational proof.",
            "readiness_summary": "TPP needs LangGraph and transport smoke coverage before live confidence.",
            "review_focus": ["Verify the LangGraph test path before upload."],
            "concerns": ["Do not treat fallback-only tests as readiness."],
            "review_evidence_traces": [VALID_REVIEW_TRACE],
        },
        round1_findings=findings,
        remote_progress={},
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
    assert queue["issues"][0]["review_evidence_trace"]["gap"] == VALID_REVIEW_TRACE["gap"]
    assert queue["issues"][0]["body"] == VALID_ISSUE_BODY
    assert "## Acceptance Criteria" in queue["issues"][0]["body"]
    assert "Implement the approved review gap" not in queue["issues"][0]["body"]
    assert queue["dropped_candidates"][0]["candidate_index"] == 2


def test_approved_issue_queue_requires_substantive_review_brief(tmp_path: Path) -> None:
    repo_dir = tmp_path / "Travel-Plan-Permission"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# TPP\n", encoding="utf-8")
    (repo_dir / "Issues.txt").write_text(
        f"""1. Keep approved repo-local work
{VALID_ISSUE_BODY}
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
    state = evaluator.collect_repo_state(tmp_path, config)
    feedback = {
        "generated_on": "2026-04-26",
        "defaults": {"approved_candidates": "all"},
        "decisions": {
            "stranske/Travel-Plan-Permission": {
                "decision": "approve",
                "priority": "high",
            }
        },
    }

    queue = evaluator.build_approved_issue_queue([state], feedback, "2026-04-26")

    assert queue["issues"] == []
    assert queue["deeper_review"][0]["decision"] == "deeper-review"
    assert "review brief failed the quality gate" in queue["warnings"][0]


def test_round1_candidate_auto_generates_matching_evidence_trace(
    tmp_path: Path,
) -> None:
    """Round-1 candidates carry their own evidence (gap, refs, acceptance) and
    therefore auto-generate a matching trace in the decision brief; the
    approved queue accepts them without requiring a hand-curated profile trace.

    Under the new design, a non-traceable round-1 candidate cannot reach this
    code path because the schema validator (`scripts/repo_review_round1_schema.py`)
    rejects malformed findings before the evaluator ingests them. The legacy
    "missing trace" rejection path therefore only fires for hand-curated
    profile traces that don't match any round-1 candidate by title.
    """
    repo_dir = tmp_path / "Travel-Plan-Permission"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# TPP\n", encoding="utf-8")
    config = evaluator.RepoConfig(
        repo="stranske/Travel-Plan-Permission",
        local_path="Travel-Plan-Permission",
        status="active",
        cadence="weekly",
        decision_anchor="approval workflow",
    )
    findings = _make_round1_findings(
        "stranske/Travel-Plan-Permission",
        candidates=[_make_round1_candidate("Keep approved repo-local work", body=VALID_ISSUE_BODY)],
    )
    state = evaluator.collect_repo_state(
        tmp_path,
        config,
        review_profile={
            "progress_summary": "TPP has implementation surfaces and needs operational proof.",
            "readiness_summary": "TPP needs LangGraph and transport smoke coverage before live confidence.",
            "review_focus": ["Verify the LangGraph test path before upload."],
            "concerns": ["Do not treat fallback-only tests as readiness."],
            # Profile trace that does NOT match the round-1 candidate by title;
            # the round-1 auto-generated trace is what makes the candidate approvable.
            "review_evidence_traces": [
                VALID_REVIEW_TRACE | {"candidate_title_patterns": ["^Different issue$"]}
            ],
        },
        round1_findings=findings,
        remote_progress={},
    )
    feedback = {
        "generated_on": "2026-04-26",
        "defaults": {"approved_candidates": "all"},
        "decisions": {
            "stranske/Travel-Plan-Permission": {
                "decision": "approve",
                "priority": "high",
            }
        },
    }

    queue = evaluator.build_approved_issue_queue([state], feedback, "2026-04-26")

    assert [item["candidate_index"] for item in queue["issues"]] == [1]
    assert queue["issues"][0]["body_valid"] is True
    # The matching trace is the auto-generated one (sourced from the round-1
    # candidate's own gap/refs/acceptance fields), not the unrelated profile trace.
    matched_trace = queue["issues"][0]["review_evidence_trace"]
    assert matched_trace["gap"] == "Specific design commitment unmet."
    assert "src/example.py" in matched_trace["implementation_refs"]
    assert queue["deeper_review"] == []


def test_round1_candidate_without_agent_ready_body_is_routed_to_revision(
    tmp_path: Path,
) -> None:
    """A round-1 candidate that doesn't carry an agent-ready body fails the
    issue-body quality gate and is routed to revision rather than uploaded."""
    repo_dir = tmp_path / "trip-planner"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Trip planner\n", encoding="utf-8")
    config = evaluator.RepoConfig(
        repo="stranske/trip-planner",
        local_path="trip-planner",
        status="active",
        cadence="weekly",
        decision_anchor="planner workflow",
    )
    # Candidate carries no body; build_agent_issue_body will auto-construct one
    # that uses the placeholder task line and the auto-constructed body fails
    # the quality gate ("Implement the approved review gap" sentinel).
    findings = _make_round1_findings(
        "stranske/trip-planner",
        candidates=[_make_round1_candidate("Add planner end-to-end tests", tasks=[])],
    )
    state = evaluator.collect_repo_state(
        tmp_path,
        config,
        review_profile={
            "progress_summary": "trip-planner has planner surfaces but needs e2e proof.",
            "readiness_summary": "Planner readiness depends on an end-to-end smoke path.",
            "review_focus": ["Verify planner turns through a real user path."],
            "concerns": ["Round-1 candidates without complete bodies are not uploadable."],
            "review_evidence_traces": [VALID_REVIEW_TRACE],
        },
        round1_findings=findings,
        remote_progress={},
    )
    feedback = {
        "generated_on": "2026-04-26",
        "defaults": {"approved_candidates": "all"},
        "decisions": {"stranske/trip-planner": {"decision": "approve", "priority": "high"}},
    }

    queue = evaluator.build_approved_issue_queue([state], feedback, "2026-04-26")

    assert queue["issues"] == []
    assert queue["deeper_review"][0]["decision"] == "revise"
    assert "needs issue-body revision before upload" in queue["warnings"][0]


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


def test_feedback_covers_converged_cycle_binding() -> None:
    """#2272: a blanket approval must not auto-approve a converged set newer than the
    feedback that 'approved all'. Deliberate-break gate: removing the date comparison in
    feedback_covers_converged makes the stale-feedback case return True and this fails.
    """
    converged = {"synthesized_at": "2026-06-10T09:00:00+00:00"}

    # Stale feedback predating the converged set -> NOT covered (the bug this closes).
    assert evaluator.feedback_covers_converged({}, "2026-05-03", converged) is False
    # Feedback at least as new as the converged set -> covered.
    assert evaluator.feedback_covers_converged({}, "2026-06-10", converged) is True
    # Explicit per-repo binding to this converged set -> covered regardless of date.
    assert (
        evaluator.feedback_covers_converged(
            {"approved_converged_synthesized_at": "2026-06-10T09:00:00+00:00"},
            "2026-05-03",
            converged,
        )
        is True
    )
    # A pin to a different converged set -> NOT covered.
    assert (
        evaluator.feedback_covers_converged(
            {"approved_converged_synthesized_at": "2026-05-01T00:00:00+00:00"},
            "2026-05-03",
            converged,
        )
        is False
    )
    # No converged set to bind to (round-1 path) -> prior behavior preserved.
    assert evaluator.feedback_covers_converged({}, "2026-05-03", None) is True
    # Unparseable feedback date fails closed (do not auto-approve blindly).
    assert evaluator.feedback_covers_converged({}, "not-a-date", converged) is False
