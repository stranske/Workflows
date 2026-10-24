import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from scripts import repo_review_evaluator as evaluator


def _writer_analyzer(
    tmp_path: Path,
    *,
    detached_output: bool,
    invalid_output: bool = False,
    launcher_lifetime: int | None = None,
) -> Path:
    """Create a launcher whose child ignores SIGTERM and keeps writing."""
    analyzer = tmp_path / "gitnexus"
    redirect = ">/dev/null 2>&1" if detached_output else ""
    analyzer.write_text(
        "#!/bin/sh\n"
        'repo="$2"\n'
        "write_forever() {\n"
        "  trap '' TERM\n"
        '  while :; do printf x >> "$repo/writer.activity"; sleep 0.05; done\n'
        "}\n"
        f"write_forever {redirect} &\n"
        # Let the child become active before the launcher publishes its PID.
        "sleep 0.1\n"
        'printf "%s" "$!" > "$repo/writer.pid"\n'
        "echo wrapper-ready\n"
        "echo wrapper-stderr >&2\n"
        + (r"printf '\377' >&2" + "\n" if invalid_output else "")
        + (
            f"sleep {launcher_lifetime}\n"
            if launcher_lifetime is not None
            else "while :; do sleep 0.05; done\n"
        ),
        encoding="utf-8",
    )
    analyzer.chmod(0o755)
    return analyzer


def _wait_for_writer_ready(tmp_path: Path) -> None:
    """Wait for child activity and the launcher's complete PID record."""
    deadline = time.monotonic() + 5
    pid_path = tmp_path / "writer.pid"
    while not (
        (tmp_path / "writer.activity").exists()
        and pid_path.exists()
        and pid_path.read_text().strip().isdigit()
    ):
        assert time.monotonic() < deadline, "fixture writer did not become ready"
        time.sleep(0.01)


def _assert_writer_stopped(tmp_path: Path) -> None:
    """Establish child exit before test cleanup, treating zombies as terminated."""
    activity = tmp_path / "writer.activity"
    assert activity.exists(), "fixture must establish a live writer"
    pid = int((tmp_path / "writer.pid").read_text())
    deadline = time.monotonic() + 1
    while True:
        state = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True, check=False
        ).stdout.strip()
        if not state or state.startswith("Z"):
            break
        if time.monotonic() >= deadline:
            pytest.fail("analyzer left a live descendant after exceptional exit")
        time.sleep(0.01)
    size = activity.stat().st_size
    time.sleep(0.2)
    assert activity.stat().st_size == size, "descendant kept writing after cleanup"


def _cleanup_writer(tmp_path: Path) -> None:
    """Remove a deliberately orphaned writer when testing the broken baseline."""
    pid_path = tmp_path / "writer.pid"
    if pid_path.exists():
        with contextlib.suppress(ProcessLookupError):
            os.kill(int(pid_path.read_text()), signal.SIGKILL)


@pytest.mark.skipif(os.name != "posix", reason="GitNexus worker process groups are POSIX")
@pytest.mark.parametrize("detached_output", [False, True])
@pytest.mark.parametrize("invalid_output", [False, True])
def test_gitnexus_timeout_stops_descendant_file_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, detached_output: bool, invalid_output: bool
) -> None:
    """Timeouts stop even quiet descendants and retain both diagnostic streams."""
    analyzer = _writer_analyzer(
        tmp_path, detached_output=detached_output, invalid_output=invalid_output
    )
    monkeypatch.setattr(evaluator, "GITNEXUS_SHUTDOWN_GRACE_SECONDS", 0.1)
    try:
        ok, message = evaluator.run_gitnexus_analyze(tmp_path, str(analyzer), timeout=1)
        assert not ok
        assert "timed out" in message
        _assert_writer_stopped(tmp_path)
        assert "wrapper-ready" in message
        assert "wrapper-stderr" in message
        if invalid_output:
            assert "\ufffd" in message
    finally:
        _cleanup_writer(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="GitNexus worker process groups are POSIX")
@pytest.mark.parametrize("exception_kind", ["interrupt", "oserror"])
def test_gitnexus_communication_exception_stops_writer_and_is_reraised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exception_kind: str
) -> None:
    """An interrupted or broken pipe cannot abandon the isolated analyzer group."""
    analyzer = _writer_analyzer(tmp_path, detached_output=True, launcher_lifetime=3)
    error = KeyboardInterrupt() if exception_kind == "interrupt" else OSError("fixture failure")
    launched = []

    class ExceptionalProcess(subprocess.Popen[str]):
        def communicate(self, *args, **kwargs):
            """Inject one read failure only after the descendant is active."""
            if self.args[0] == str(analyzer) and not getattr(self, "injected", False):
                launched.append(self)
                self.injected = True
                _wait_for_writer_ready(tmp_path)
                raise error
            return super().communicate(*args, **kwargs)

    monkeypatch.setattr(evaluator.subprocess, "Popen", ExceptionalProcess)
    monkeypatch.setattr(evaluator, "GITNEXUS_SHUTDOWN_GRACE_SECONDS", 0.1)
    try:
        with pytest.raises(type(error)) as caught:
            evaluator.run_gitnexus_analyze(tmp_path, str(analyzer))
        assert caught.value is error
        _assert_writer_stopped(tmp_path)
    finally:
        _cleanup_writer(tmp_path)
        for proc in launched:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=2)


@pytest.mark.skipif(os.name != "posix", reason="GitNexus worker process groups are POSIX")
def test_gitnexus_quiet_analyzer_gets_grace_after_launcher_exits(tmp_path, monkeypatch):
    analyzer = tmp_path / "gitnexus"
    analyzer.write_text(
        "#!/bin/sh\n"
        'repo="$2"\n'
        "trap 'exit 0' TERM\n"
        "flush_on_exit() {\n"
        "  trap 'sleep 0.2; printf flushed > \"$repo/writer.flushed\"; exit 0' TERM\n"
        '  printf x > "$repo/writer.activity"\n'
        "  while :; do sleep 0.05; done\n"
        "}\n"
        "flush_on_exit >/dev/null 2>&1 &\n"
        "sleep 0.1\n"
        'printf "%s" "$!" > "$repo/writer.pid"\n'
        "while :; do sleep 0.05; done\n"
    )
    analyzer.chmod(0o755)

    class TimeoutAfterReady(subprocess.Popen[bytes]):
        def communicate(self, *args, **kwargs):
            if self.args[0] == str(analyzer) and not getattr(self, "injected", False):
                self.injected = True
                _wait_for_writer_ready(tmp_path)
                raise subprocess.TimeoutExpired(self.args, 1)
            return super().communicate(*args, **kwargs)

    monkeypatch.setattr(evaluator.subprocess, "Popen", TimeoutAfterReady)
    monkeypatch.setattr(evaluator, "GITNEXUS_SHUTDOWN_GRACE_SECONDS", 1)
    try:
        ok, message = evaluator.run_gitnexus_analyze(tmp_path, str(analyzer), timeout=1)
        assert not ok
        assert "timed out" in message
        _assert_writer_stopped(tmp_path)
        assert (tmp_path / "writer.flushed").read_text() == "flushed"
    finally:
        _cleanup_writer(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="GitNexus worker process groups are POSIX")
@pytest.mark.parametrize("cleanup_read", [2, 3])
@pytest.mark.parametrize("interrupt_kind", ["interrupt", "exit"])
def test_gitnexus_cleanup_interrupt_propagates_after_stopping_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_read: int, interrupt_kind: str
) -> None:
    """A new operator interrupt during either cleanup read remains observable."""
    analyzer = _writer_analyzer(tmp_path, detached_output=True)
    interrupt = KeyboardInterrupt() if interrupt_kind == "interrupt" else SystemExit(23)
    launched = []

    class InterruptedCleanupProcess(subprocess.Popen[bytes]):
        def communicate(self, *args, **kwargs):
            """Fail the first read, then interrupt the selected cleanup read."""
            if self.args[0] != str(analyzer):
                return super().communicate(*args, **kwargs)
            self.read_count = getattr(self, "read_count", 0) + 1
            if self.read_count == 1:
                launched.append(self)
                _wait_for_writer_ready(tmp_path)
                raise OSError("initial pipe failure")
            if self.read_count == cleanup_read:
                raise interrupt
            return super().communicate(*args, **kwargs)

    monkeypatch.setattr(evaluator.subprocess, "Popen", InterruptedCleanupProcess)
    monkeypatch.setattr(evaluator, "GITNEXUS_SHUTDOWN_GRACE_SECONDS", 0.1)
    try:
        with pytest.raises(type(interrupt)) as caught:
            evaluator.run_gitnexus_analyze(tmp_path, str(analyzer))
        assert caught.value is interrupt
        _assert_writer_stopped(tmp_path)
    finally:
        _cleanup_writer(tmp_path)
        for proc in launched:
            proc.wait(timeout=2)


@pytest.mark.skipif(os.name != "posix", reason="fixture uses a POSIX executable")
@pytest.mark.parametrize("exit_code", [0, 7])
def test_gitnexus_analyzer_preserves_completed_process_output(
    tmp_path: Path, exit_code: int
) -> None:
    """The supervision wrapper preserves ordinary success and failure diagnostics."""
    analyzer = tmp_path / "gitnexus"
    analyzer.write_text(
        f"#!/bin/sh\necho analyzer-stdout\necho analyzer-stderr >&2\nexit {exit_code}\n"
    )
    analyzer.chmod(0o755)
    ok, message = evaluator.run_gitnexus_analyze(tmp_path, str(analyzer))
    assert ok is (exit_code == 0)
    assert message == "analyzer-stdout\n\nanalyzer-stderr"


def test_gitnexus_analyzer_reports_missing_executable(tmp_path: Path) -> None:
    """An absent optional CLI reports an actionable failure without spawning work."""
    analyzer = tmp_path / "missing-gitnexus"
    ok, message = evaluator.run_gitnexus_analyze(tmp_path, str(analyzer))
    assert not ok
    assert str(analyzer) in message


@pytest.mark.skipif(os.name != "posix", reason="fixture uses a POSIX executable")
def test_gitnexus_binary_diagnostics_decode_bytes_and_normalize_newlines(tmp_path: Path) -> None:
    """Decoding after shutdown retains text-mode line endings and malformed output."""
    analyzer = tmp_path / "gitnexus"
    analyzer.write_text("#!/bin/sh\n" + r"printf 'first\r\nsecond\rthird\n\377'" + "\n")
    analyzer.chmod(0o755)
    ok, message = evaluator.run_gitnexus_analyze(tmp_path, str(analyzer))
    assert ok
    assert message == "first\nsecond\nthird\n\ufffd"


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


@pytest.mark.parametrize(
    "marker",
    [
        "CORRUPTED WAL FILE",
        "Invalid WAL Record Type",
        "Database Disk Image Is Malformed",
        "DATABASE IS MALFORMED",
        "File Is Not A Database",
        "SQLITE_CORRUPT",
    ],
)
def test_gitnexus_analyze_rejects_zero_exit_corruption_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    """Reject corruption diagnostics even when the CLI reports success."""
    monkeypatch.setattr(
        evaluator,
        "_run_gitnexus_command",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["gitnexus"], returncode=0, stdout=f"analysis complete: {marker}", stderr=""
        ),
    )

    ok, message = evaluator.run_gitnexus_analyze(tmp_path, "gitnexus")

    assert ok is False
    assert "GitNexus corruption detected" in message


def test_gitnexus_analyze_accepts_clean_zero_exit_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accept clean output independently of subprocess supervision."""
    monkeypatch.setattr(
        evaluator,
        "_run_gitnexus_command",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["gitnexus"], returncode=0, stdout="GitNexus Analyzer complete", stderr=""
        ),
    )

    ok, message = evaluator.run_gitnexus_analyze(tmp_path, "gitnexus")

    assert ok is True
    assert message == "GitNexus Analyzer complete"


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


def test_run_git_and_design_collection_degrade_for_missing_local_clone(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    assert evaluator.run_git(missing, ["status"]) == ""
    assert evaluator.collect_design_files(missing) == []
    assert evaluator.collect_implementation_areas(missing) == []


def test_dynamic_run_evidence_classifies_fresh_and_tracked_findings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cli = tmp_path / "keepalive_evidence.py"
    cli.write_text("# fixture", encoding="utf-8")
    monkeypatch.setattr(evaluator, "_resolve_orchestrator_cli", lambda: cli)
    monkeypatch.setattr(
        evaluator.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "lookback_days": 7,
                    "signals": {"durable_rate": 0.5},
                    "candidates": [
                        {"type": "reverted", "severity": "HIGH", "seed": "gate reverted"},
                        {
                            "type": "recurring",
                            "severity": "LOW",
                            "seed": "already tracked",
                            "possible_duplicate": True,
                            "evidence": {"pr": 12},
                            "dup_issue": 34,
                        },
                    ],
                }
            ),
            stderr="",
        ),
    )

    evidence = evaluator.build_dynamic_run_evidence({"repo": "owner/demo"})

    assert evidence is not None
    assert evidence["gap_severity"] == "material"
    assert evidence["issue_draft_needed"] == "yes"
    assert "Net-new candidates: 1" in evidence["evidence"][1]


def test_dynamic_run_evidence_returns_none_without_a_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evaluator, "_resolve_orchestrator_cli", lambda: Path("/tmp/unused"))
    assert evaluator.build_dynamic_run_evidence({}) is None


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


def test_liveness_dimension_flags_status_claim_without_sink_evidence(tmp_path: Path) -> None:
    repo_dir = tmp_path / "brain"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text(
        "# Brain\n\nThe LangSmith pipeline is implemented, wired, and scheduled.\n",
        encoding="utf-8",
    )
    src = repo_dir / "src"
    src.mkdir()
    (src / "brain.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
    subprocess = evaluator.subprocess
    subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md", "src/brain.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    config = evaluator.RepoConfig(
        repo="owner/brain",
        local_path="brain",
        status="active",
        cadence="weekly",
        decision_anchor="cost telemetry must reach the Brain",
    )

    state = evaluator.collect_repo_state(tmp_path, config, remote_progress={})
    liveness = evaluator.execution_dimension(state, "liveness_evidence")

    assert liveness["gap_severity"] == "material"
    assert "real sink/output evidence" in liveness["finding"]
    assert state["review_execution"]["gap_count"] >= 1
    assert "Not ready to approve completion claims" in state["decision_brief"]["readiness_summary"]


def test_liveness_dimension_surfaces_possible_sink_evidence_for_review(tmp_path: Path) -> None:
    repo_dir = tmp_path / "brain"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text(
        "# Brain\n\nThe LangSmith pipeline is implemented and scheduled.\n\n"
        "Latest verified sink sample: 95 cost rows written to the Brain.\n",
        encoding="utf-8",
    )
    src = repo_dir / "src"
    src.mkdir()
    (src / "brain.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
    subprocess = evaluator.subprocess
    subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md", "src/brain.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    config = evaluator.RepoConfig(
        repo="owner/brain",
        local_path="brain",
        status="active",
        cadence="weekly",
        decision_anchor="cost telemetry must reach the Brain",
    )

    state = evaluator.collect_repo_state(tmp_path, config, remote_progress={})
    liveness = evaluator.execution_dimension(state, "liveness_evidence")

    assert liveness["gap_severity"] == "needs human decision"
    assert "possible sink/output evidence" in liveness["finding"]
    assert any("README.md" in item for item in liveness["evidence"])


def test_liveness_dimension_ignores_snake_case_fragments(tmp_path: Path) -> None:
    repo_dir = tmp_path / "brain"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text(
        "# Brain\n\nThe pull_request handler exists.\n", encoding="utf-8"
    )
    src = repo_dir / "src"
    src.mkdir()
    (src / "brain.py").write_text("def run():\n    return 'pull_request'\n", encoding="utf-8")
    subprocess = evaluator.subprocess
    subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md", "src/brain.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    config = evaluator.RepoConfig(
        repo="owner/brain",
        local_path="brain",
        status="active",
        cadence="weekly",
        decision_anchor="pull request metadata should not imply live completion",
    )

    state = evaluator.collect_repo_state(tmp_path, config, remote_progress={})
    liveness = evaluator.execution_dimension(state, "liveness_evidence")

    assert "README.md" not in "\n".join(liveness["evidence"])
    assert "No explicit implementation/status/data-flow claims" in liveness["finding"]


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
    review_inputs = output_dir / "repos" / "owner__demo" / "review-inputs.md"
    assert review.is_file()
    assert execution.is_file()
    assert brief.is_file()
    assert review_inputs.is_file()
    text = review.read_text(encoding="utf-8")
    assert "Standard Design Review" in text
    assert "Design Contract" in text
    assert "Liveness Evidence" in text
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
    assert "Liveness Evidence" in execution_text
    brief_text = brief.read_text(encoding="utf-8")
    assert "Review Quality Gate" in brief_text
    assert "Current Progress Compared With Design" in brief_text
    assert "Readiness For Testing Or Live Implementation" in brief_text
    assert "Liveness evidence" in brief_text
    assert "Candidate Issue Set" in brief_text
    review_inputs_text = review_inputs.read_text(encoding="utf-8")
    assert "## Liveness Evidence Check" in review_inputs_text
    assert "verify the real sink/output" in review_inputs_text


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


def _make_converged_candidate(
    title: str, *, priority: str = "normal", scope: str = "fix"
) -> dict[str, object]:
    """A round-2 converged candidate carrying its own agent-ready body, the
    structured fields the auto-trace needs, and a per-candidate priority."""
    return {
        "title": title,
        "scope": scope,
        "priority": priority,
        "gap": "Specific design commitment unmet for this converged candidate.",
        "current_state": "Today's code/tests do not prove the gap is closed.",
        "required_change": "Add the targeted change described by this candidate.",
        "design_refs": ["README.md", "docs/design.md"],
        "implementation_refs": ["src/example.py"],
        "test_refs": ["tests/test_example.py"],
        "acceptance_criteria": ["Test fails before fix and passes after."],
        "non_goals": ["Do not bundle unrelated cleanup."],
        "tasks": ["First task", "Second task"],
        "body": VALID_ISSUE_BODY,
        "origin": {"source_agent": "codex", "round1_index": 1, "merged_from": None},
    }


def _tiering_state(tmp_path: Path) -> dict[str, object]:
    """Repo state whose round-2 converged set carries a low, a normal, a high,
    and a meta-audit candidate — the inputs for the high-stakes tiering gate."""
    repo_dir = tmp_path / "Trend_Model_Project"
    repo_dir.mkdir(parents=True)
    (repo_dir / "README.md").write_text("# Trend\n", encoding="utf-8")
    config = evaluator.RepoConfig(
        repo="stranske/Trend_Model_Project",
        local_path="Trend_Model_Project",
        status="active",
        cadence="weekly",
        decision_anchor="trend model workflow",
    )
    converged = {
        "schema_version": "v1",
        "repo": "stranske/Trend_Model_Project",
        "synthesized_at": "2026-04-20T09:00:00+00:00",
        "converged_candidates": [
            _make_converged_candidate("Add low-priority cleanup gate", priority="low"),
            _make_converged_candidate("Add normal-priority smoke gate", priority="normal"),
            _make_converged_candidate("Add high-priority release gate", priority="high"),
        ],
        "deadlocked_candidates": [],
        "meta_candidate": _make_converged_candidate(
            "Audit duplicate-dedup pattern across modules", priority="normal", scope="audit"
        ),
    }
    return evaluator.collect_repo_state(
        tmp_path,
        config,
        review_profile={
            "progress_summary": "Trend has model surfaces and needs operational proof before release.",
            "readiness_summary": "Trend needs deterministic smoke coverage before live confidence.",
            "review_focus": ["Verify the release smoke path before upload."],
            "concerns": ["Do not treat fallback-only tests as readiness."],
        },
        round2_converged=converged,
        remote_progress={},
    )


def test_priority_tiering_routes_high_stakes_under_blanket_approval(tmp_path: Path) -> None:
    """#2272 high-stakes tiering: under a fresh blanket 'approve all' (feedback
    covers the converged set), low/normal candidates auto-approve, but a
    high-priority candidate AND the meta-audit candidate route to deeper_review.

    Deliberate-break gate: forcing ``high_stakes_tier`` to always return None
    (i.e. deleting the tiering) makes the high-priority + meta candidates
    auto-approve and the four-vs-two split assertions below fail.
    """
    state = _tiering_state(tmp_path)
    # Explicitly bind this reviewed source set; tiering remains a separate gate.
    feedback = {
        "generated_on": "2026-05-01",
        "defaults": {"approved_candidates": "all"},
        "decisions": {
            "stranske/Trend_Model_Project": {
                "decision": "approve",
                "priority": "normal",
                "approved_converged_synthesized_at": state["round2_converged"]["synthesized_at"],
            }
        },
    }

    queue = evaluator.build_approved_issue_queue([state], feedback, "2026-05-01")

    approved_titles = {item["title"] for item in queue["issues"]}
    deeper_titles = " ".join(item["notes"] for item in queue["deeper_review"])
    # low + normal auto-approve.
    assert "Add low-priority cleanup gate" in approved_titles
    assert "Add normal-priority smoke gate" in approved_titles
    # high-priority + meta-audit are held back, NOT materialized.
    assert "Add high-priority release gate" not in approved_titles
    assert "Audit duplicate-dedup pattern across modules" not in approved_titles
    assert len(queue["issues"]) == 2
    # Two deeper_review entries naming their tiers.
    assert "high-priority" in deeper_titles
    assert "meta-audit" in deeper_titles
    assert sum(1 for w in queue["warnings"] if "high-stakes tiering guard" in w) == 2


def test_priority_tiering_respects_explicit_naming_and_opt_in(tmp_path: Path) -> None:
    """The high-stakes gate yields to an explicit human decision: listing the
    high-priority candidate's index in approved_candidates approves it, and the
    repo-level auto_approve_high flag approves the whole high-stakes set."""
    # (a) Explicitly naming the high-priority candidate index (3) approves it,
    #     while the meta candidate (index 4) — not named — still routes deeper.
    state = _tiering_state(tmp_path)
    feedback_named = {
        "generated_on": "2026-05-01",
        "defaults": {"approved_candidates": "all"},
        "decisions": {
            "stranske/Trend_Model_Project": {
                "decision": "approve",
                "priority": "normal",
                "approved_candidates": [1, 2, 3],
                "approved_converged_synthesized_at": state["round2_converged"]["synthesized_at"],
            }
        },
    }
    queue_named = evaluator.build_approved_issue_queue([state], feedback_named, "2026-05-01")
    named_titles = {item["title"] for item in queue_named["issues"]}
    assert "Add high-priority release gate" in named_titles
    assert "Audit duplicate-dedup pattern across modules" not in named_titles

    # (b) auto_approve_high opts the repo into unattended high-stakes approval:
    #     all four candidates (incl. high + meta) materialize.
    state_b = _tiering_state(tmp_path / "b")
    feedback_optin = {
        "generated_on": "2026-05-01",
        "defaults": {"approved_candidates": "all"},
        "decisions": {
            "stranske/Trend_Model_Project": {
                "decision": "approve",
                "priority": "normal",
                "auto_approve_high": True,
                "approved_converged_synthesized_at": state_b["round2_converged"]["synthesized_at"],
            }
        },
    }
    queue_optin = evaluator.build_approved_issue_queue([state_b], feedback_optin, "2026-05-01")
    assert len(queue_optin["issues"]) == 4


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
    # Even a fresh global date cannot authorize an unpinned source set.
    assert evaluator.feedback_covers_converged({}, "2026-06-10", converged) is False
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
    assert (
        evaluator.feedback_covers_converged(
            {"approved_converged_synthesized_at": "2026-06-10T09:00:00+00:00"},
            "2026-06-10",
            None,
        )
        is False
    )
    # Unparseable feedback date fails closed (do not auto-approve blindly).
    assert evaluator.feedback_covers_converged({}, "not-a-date", converged) is False


def test_build_approved_issue_queue_includes_approved_scorecard_findings() -> None:
    from scripts.repo_review_scorecard import SCHEMA

    scorecard_scan = {
        "schema": SCHEMA,
        "generated_on": "2026-06-14T12:00:00Z",
        "by_repo": [
            {
                "repo": "stranske/Workflows",
                "local_path": "Workflows-steward",
                "workflow": ".github/workflows/health-53-scorecard.yml",
                "findings": [
                    {
                        "finding_id": "scorecard:Branch-Protection",
                        "check": "Branch-Protection",
                        "score": 0.0,
                        "minimum_score": 7.0,
                        "priority": "high",
                        "reason": "branch protection not enabled on default branch",
                        "details": [],
                        "documentation_url": "https://example.com/branch-protection",
                    }
                ],
            }
        ],
    }
    feedback = {
        "generated_on": "2026-06-14",
        "decisions": {
            "stranske/Workflows": {
                "decision": "defer",
                "scorecard": {
                    "decision": "approve",
                    "approved_findings": ["scorecard:Branch-Protection"],
                    "dropped_findings": [],
                    "priority": "normal",
                    "priority_overrides": {},
                },
            }
        },
    }
    queue = evaluator.build_approved_issue_queue([], feedback, "2026-06-14", scorecard_scan)
    assert len(queue["issues"]) == 1
    assert queue["issues"][0]["scorecard_finding_id"] == "scorecard:Branch-Protection"
    assert queue["issues"][0]["source_type"] == "scorecard finding"


def test_build_approved_issue_queue_surfaces_unapproved_scorecard_for_deeper_review() -> None:
    from scripts.repo_review_scorecard import SCHEMA

    scorecard_scan = {
        "schema": SCHEMA,
        "by_repo": [
            {
                "repo": "stranske/Workflows",
                "local_path": "Workflows-steward",
                "workflow": ".github/workflows/health-53-scorecard.yml",
                "findings": [
                    {
                        "finding_id": "scorecard:Branch-Protection",
                        "check": "Branch-Protection",
                        "score": 0.0,
                        "minimum_score": 7.0,
                        "priority": "high",
                        "reason": "branch protection not enabled on default branch",
                        "details": [],
                        "documentation_url": "https://example.com/branch-protection",
                    }
                ],
            }
        ],
    }
    feedback = {
        "generated_on": "2026-06-14",
        "scorecard_defaults": {"decision": "defer", "approved_findings": []},
        "decisions": {
            "stranske/Workflows": {
                "decision": "defer",
                "scorecard": {
                    "decision": "defer",
                    "approved_findings": [],
                    "dropped_findings": [],
                },
            }
        },
    }
    queue = evaluator.build_approved_issue_queue([], feedback, "2026-06-14", scorecard_scan)
    assert queue["issues"] == []
    assert any("Scorecard finding" in item["notes"] for item in queue["deeper_review"])


def test_excluded_historical_report_paths_are_filtered_before_limit(tmp_path):
    repo_dir = tmp_path / "demo"
    reports = repo_dir / "docs" / "reports"
    for index in range(12):
        report = reports / "archive" / "owner__held-repo" / f"{index:02}.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("must not be read")
    for name in (
        "held-repo.md",
        "held-repo/brief.md",
        "owner__held-repo-doc-drift.md",
        "owner__HELD-REPO-summary.md",
        "owner__held-repository/brief.md",
        "owner__held-repository-doc-drift.md",
    ):
        report = reports / name
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("report")
    config = evaluator.RepoConfig(
        repo="owner/demo",
        local_path="demo",
        status="active",
        cadence="weekly",
        decision_anchor="demo",
    )
    state = evaluator.collect_repo_state(
        tmp_path, config, remote_progress={}, excluded_repo_names=["owner", "owner/held-repo"]
    )
    assert set(state["report_files"]) == {
        "docs/reports/owner__held-repository/brief.md",
        "docs/reports/owner__held-repository-doc-drift.md",
    }


def test_excluded_parent_references_are_removed_before_remote_counts(tmp_path):
    repo_dir = tmp_path / "demo"
    repo_dir.mkdir()
    config = evaluator.RepoConfig(
        repo="owner/demo",
        local_path="demo",
        status="active",
        cadence="weekly",
        decision_anchor="demo",
    )
    progress = {
        "available": True,
        "open_issues": [
            {"number": 1, "title": "Repair OWNER/held-repo#12"},
            {"number": 2, "title": "Repair held-repository#12"},
            {"number": 3, "title": "Repair demo", "url": "https://github.com/owner/demo/issues/3"},
        ],
        "recent_merged_prs": [{"number": 4, "title": "Fix held-repo integration"}],
        "warnings": [],
    }
    archive = [
        evaluator.ArchiveCandidate(
            title=title,
            source_file="held-repo/prior.jsonl",
            thread_name="review",
            timestamp="2026-10-15",
            excerpt=title,
        )
        for title in ("Prior held-repo work", "Prior demo work")
    ]
    state = evaluator.collect_repo_state(
        tmp_path,
        config,
        archive_candidates=archive,
        remote_progress=progress,
        excluded_repo_names=["owner", "held-repo"],
    )
    assert state["remote_open_issue_count"] == 2
    assert [item["number"] for item in state["remote_progress"]["open_issues"]] == [2, 3]
    assert state["remote_progress"]["recent_merged_prs"] == []
    assert state["archive_progress_count"] == 1
    assert state["archive_progress"][0]["title"] == "Prior demo work"
    assert len(progress["open_issues"]) == 3  # caller evidence is retained


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Repair held-repo.", True),
        ("Repair HELD-REPO...", True),
        ("Repair owner/held-repo#12", True),
        ("https://github.com/owner/held-repo/issues/12", True),
        ("Repair held-repo.v2", False),
        ("Repair held-repo..v2", False),
        ("Repair held-repository", False),
        ("Repair held-repo-other", False),
    ],
)
def test_exclusion_repo_name_punctuation_and_longer_names(text, expected):
    assert evaluator.references_excluded_repo(text, ["held-repo"]) is expected


def test_unmatched_approval_titles_never_fall_back_to_old_positions() -> None:
    candidates = [{"candidate_index": 1, "title": "New production smoke audit"}]
    for patterns in (["^Old scoring fix$"], ["["], [], [""], [" ", None]):
        decision = {"approved_candidates": [1], "approved_title_patterns": patterns}
        assert evaluator.approved_candidate_indexes(decision, 1, {}, candidates) == set()


def test_stale_explicit_approval_cannot_select_another_cycle(tmp_path: Path) -> None:
    state = _tiering_state(tmp_path)
    decision = {
        "decision": "approve",
        "approved_candidates": [1, 2, 3],
        "approved_converged_synthesized_at": "2026-01-01T00:00:00Z",
    }
    feedback = {"generated_on": "2026-05-01", "decisions": {state["repo"]: decision}}
    for extra in ({}, {"approved_title_patterns": ["^Add low-priority cleanup gate$"]}):
        decision.update(extra)
        queue = evaluator.build_approved_issue_queue([state], feedback, "2026-05-01")
        assert queue["issues"] == []
        assert any("stale-feedback guard" in warning for warning in queue["warnings"])


def test_current_cycle_explicit_approval_still_selects_named_position(tmp_path: Path) -> None:
    state = _tiering_state(tmp_path)
    feedback = {
        "generated_on": "2026-01-01",
        "decisions": {
            state["repo"]: {
                "decision": "approve",
                "approved_candidates": [2],
                "approved_converged_synthesized_at": state["round2_converged"]["synthesized_at"],
            }
        },
    }
    queue = evaluator.build_approved_issue_queue([state], feedback, "2026-05-01")
    assert [issue["title"] for issue in queue["issues"]] == ["Add normal-priority smoke gate"]


def test_queue_regeneration_preserves_original_approval_and_hold(tmp_path: Path) -> None:
    import hashlib
    import json

    from scripts import repo_review_approval_ledger as ledger

    state = _tiering_state(tmp_path)
    current_feedback = {
        "generated_on": "2026-05-01",
        "decisions": {
            state["repo"]: {
                "decision": "approve",
                "approved_candidates": [1, 2],
                "approved_converged_synthesized_at": state["round2_converged"]["synthesized_at"],
            }
        },
    }
    original = evaluator.build_approved_issue_queue([state], current_feedback, "2026-05-01")
    assert len(original["issues"]) == 2
    source = tmp_path / "original-approved.json"
    source.write_text(json.dumps(original))
    entries = [
        {
            "repo": item["repo"],
            "title": item["title"],
            "finding_id": ledger.finding_id(item["repo"], item["title"]),
            "approved_item_sha256": ledger.item_digest(item),
            "filing": {"status": "unfiled", "issues": []},
        }
        for item in original["issues"]
    ]
    (tmp_path / "approval-ledger.json").write_text(
        json.dumps(
            {
                "schema": ledger.SCHEMA,
                "source_queue_path": str(source),
                "source_queue_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "authority": "Owner approved original snapshot",
                "source_cycle": "earlier-cycle",
                "entries": entries,
                "intake_hold": {"active": True},
            }
        )
    )
    state["round2_converged"]["synthesized_at"] = "2026-06-01T00:00:00Z"
    state["round2_converged"]["converged_candidates"][0]["title"] = "Different new work"
    for _ in range(2):
        queue = evaluator.write_approved_issue_queue(
            tmp_path, [state], current_feedback, "2026-06-01"
        )
        assert queue["issues"] == []
        assert [x["title"] for x in queue["held_approved_issues"]] == [
            x["title"] for x in original["issues"]
        ]
        assert all(
            x["body"] == original["issues"][i]["body"]
            for i, x in enumerate(queue["held_approved_issues"])
        )
        assert queue["intake_hold"]["active"] is True
        assert queue["upload_allowed"] is False
        assert "Owner intake hold active" in (tmp_path / "approved-issue-queue.md").read_text()
    state["status"] = "paused"
    queue = evaluator.write_approved_issue_queue(tmp_path, [state], current_feedback, "2026-06-01")
    assert queue["issues"] == []
    assert queue["held_approved_issues"] == []
    assert len(json.loads((tmp_path / "approval-ledger.json").read_text())["entries"]) == 2


def test_fresh_global_date_cannot_rebind_unpinned_numeric_positions(tmp_path: Path) -> None:
    state = _tiering_state(tmp_path)
    feedback = {
        "generated_on": "2099-01-01",
        "decisions": {state["repo"]: {"decision": "approve", "approved_candidates": [1]}},
    }
    queue = evaluator.build_approved_issue_queue([state], feedback, "2099-01-01")
    assert queue["issues"] == []
    assert any("stale-feedback guard" in warning for warning in queue["warnings"])


def test_fresh_global_date_cannot_rebind_old_title_patterns(tmp_path: Path) -> None:
    state = _tiering_state(tmp_path)
    feedback = {
        "generated_on": "2099-01-01",
        "decisions": {
            state["repo"]: {
                "decision": "approve",
                "approved_candidates": [1],
                "approved_title_patterns": ["^Add low-priority"],
            }
        },
    }
    queue = evaluator.build_approved_issue_queue([state], feedback, "2099-01-01")
    assert queue["issues"] == []
    assert any("stale-feedback guard" in warning for warning in queue["warnings"])


def test_explicit_unattended_opt_in_still_respects_high_stakes_gate(tmp_path: Path) -> None:
    state = _tiering_state(tmp_path)
    feedback = {
        "generated_on": "2026-01-01",
        "defaults": {"approved_candidates": "all"},
        "decisions": {state["repo"]: {"decision": "approve", "auto_approve_new": True}},
    }
    queue = evaluator.build_approved_issue_queue([state], feedback, "2026-05-01")
    assert {x["title"] for x in queue["issues"]} == {
        "Add low-priority cleanup gate",
        "Add normal-priority smoke gate",
    }
    assert len(queue["deeper_review"]) == 2


def test_queue_writer_renders_conflict_resolution_approval_metadata(tmp_path, monkeypatch):
    from scripts import repo_review_approval_ledger as ledger

    state = _tiering_state(tmp_path)

    def resolved(queue, *args, **kwargs):
        for item in queue["issues"]:
            item.update(
                finding_id="resolved-finding",
                approval_source={
                    "authority": "Owner resolution",
                    "item_sha256": "resolved-digest",
                    "conflict_store": "local-store",
                },
            )
        return queue

    monkeypatch.setattr(ledger, "merge_approval_ledger", resolved)
    feedback = {
        "decisions": {
            state["repo"]: {
                "decision": "approve",
                "approved_candidates": "all",
                "approved_converged_synthesized_at": state["round2_converged"]["synthesized_at"],
            }
        }
    }
    queue = evaluator.write_approved_issue_queue(tmp_path, [state], feedback, "2026-06-01")
    assert queue["issues"]
    rendered = (tmp_path / "approved-issue-queue.md").read_text()
    assert "explicit scope resolution" in rendered
    assert "original scope only" not in rendered


def test_remote_progress_normalizes_gh_payloads_and_keeps_partial_failures_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    [
                        {
                            "number": 7,
                            "title": "Open gap",
                            "labels": [{"name": "bug"}, "not-a-label"],
                            "createdAt": "2026-10-20T00:00:00Z",
                        }
                    ]
                ),
                "",
            ),
            subprocess.CompletedProcess([], 0, "not-json", ""),
        ]
    )
    monkeypatch.setattr(evaluator.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(evaluator.subprocess, "run", lambda *args, **kwargs: next(responses))

    progress = evaluator.collect_remote_progress("owner/repo", open_issue_limit=3)

    assert progress["available"] is True
    assert progress["open_issues"] == [
        {
            "number": 7,
            "title": "Open gap",
            "labels": ["bug"],
            "created_at": "2026-10-20T00:00:00Z",
        }
    ]
    assert progress["recent_merged_prs"] == []
    assert progress["warnings"] == ["gh pr list (merged) failed or returned non-list"]


def test_remote_issue_count_fails_closed_when_gh_is_missing_or_returns_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evaluator.shutil, "which", lambda _name: None)
    assert evaluator.remote_open_issue_count("owner/repo") is None

    monkeypatch.setattr(evaluator.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(
        evaluator.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "{}", ""),
    )
    assert evaluator.remote_open_issue_count("owner/repo") is None


def test_issue_set_recommendation_distinguishes_round_two_completion_states() -> None:
    base = {"review_execution": {"gap_count": 0}}
    thin = evaluator.issue_set_recommendation(
        {**base, "round2_converged": {"converged_candidates": [], "no_new_work_justifications": []}}
    )
    complete = evaluator.issue_set_recommendation(
        {
            **base,
            "round2_converged": {
                "converged_candidates": [],
                "no_new_work_justifications": [
                    _no_new_work_entry("codex"),
                    _no_new_work_entry("claude"),
                ],
            },
        }
    )
    candidates = evaluator.issue_set_recommendation(
        {
            **base,
            "round2_converged": {
                "converged_candidates": [{"title": "A"}],
                "meta_candidate": {"title": "Audit"},
                "deadlocked_candidates": [{"title": "Conflict"}],
            },
        }
    )

    assert "missing or thin" in thin
    assert "Both agents (codex, claude)" in complete
    assert "plus 1 meta-candidate" in candidates
    assert "1 deadlocked candidate" in candidates


def test_write_repo_artifacts_preserves_drafts_and_archive_entries(tmp_path: Path) -> None:
    state = _tiering_state(tmp_path)
    state["archive_candidates"] = [
        {
            "title": "Prior review",
            "thread_name": "weekly-review",
            "timestamp": "2026-10-01",
            "source_file": "archive.jsonl",
            "excerpt": "Validate the old result against current code.",
        }
    ]
    state["archive_candidate_count"] = 2
    state["drafts"] = [
        {
            "number": 4,
            "title": "Existing draft",
            "open_tasks": 2,
            "done_tasks": 1,
            "body": "- [ ] verify behavior",
        }
    ]
    state["issue_draft_count"] = 2

    evaluator.write_repo_artifacts(tmp_path / "out", state, max_drafts=1)

    artifacts = tmp_path / "out" / "repos" / "stranske__Trend_Model_Project"
    assert "Archive Review Precedent" in (artifacts / "design-review.md").read_text()
    drafts = (artifacts / "issue-drafts.md").read_text()
    assert "Existing draft" in drafts
    assert "Only the first 1 archive candidates" in drafts
    assert "Only the first 1 drafts" in drafts


def test_round_result_loaders_select_valid_latest_files_and_reject_invalid_data(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "reports"
    repo = "owner/repo"
    # The older file sits in the directory that sorts last, so only the modification time can
    # make the loader pick the newer one.
    old = output_dir / "round1" / "zulu" / "owner__repo" / "findings.json"
    new = output_dir / "round1" / "alpha" / "owner__repo" / "findings.json"
    old.parent.mkdir(parents=True)
    new.parent.mkdir(parents=True)
    old.write_text(json.dumps({"agent": "first"}), encoding="utf-8")
    new.write_text(json.dumps({"agent": "second"}), encoding="utf-8")
    os.utime(old, (1_000, 1_000))
    os.utime(new, (2_000, 2_000))

    latest = evaluator.load_round1_findings(output_dir, repo)

    assert latest is not None
    assert latest["agent"] == "second"
    assert latest["__source_path"] == str(new)
    converged = output_dir / "round2" / "owner__repo" / "converged.json"
    converged.parent.mkdir(parents=True)
    converged.write_text(json.dumps({"converged_candidates": []}), encoding="utf-8")
    assert evaluator.load_round2_converged(output_dir, repo)["__source_path"] == str(converged)
    converged.write_text("[]", encoding="utf-8")
    assert evaluator.load_round2_converged(output_dir, repo) is None


def test_collect_gitnexus_map_reports_current_metadata_and_degraded_embeddings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = tmp_path / "repo"
    meta = repo_path / ".gitnexus" / "meta.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(
        json.dumps(
            {"lastCommit": "abc123", "repoPath": str(repo_path), "stats": {"embeddings": 0}}
        ),
        encoding="utf-8",
    )
    repo = evaluator.RepoConfig("owner/repo", "repo", "active", "weekly", "anchor")
    monkeypatch.setattr(evaluator, "run_git", lambda *_args, **_kwargs: "abc123")

    record = evaluator.collect_gitnexus_map(tmp_path, repo_path, repo)

    assert record["status"] == "current"
    assert record["needs_embeddings"] is True
    meta.unlink()
    assert evaluator.collect_gitnexus_map(tmp_path, repo_path, repo)["status"] == "missing"


def test_main_filters_statuses_and_reports_generated_queue_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    active = evaluator.RepoConfig("owner/active", "active", "active", "weekly", "anchor")
    paused = evaluator.RepoConfig("owner/paused", "paused", "paused", "weekly", "anchor")
    calls: list[str] = []
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "repo_review_evaluator",
            "--status",
            "active",
            "--date",
            "2026-10-22",
            "--skip-gitnexus-preflight",
        ],
    )
    monkeypatch.setattr(
        evaluator,
        "gitnexus_preflight",
        lambda *_args, **_kwargs: pytest.fail("the GitNexus preflight must be skipped here"),
    )
    monkeypatch.setattr(
        evaluator, "load_registry", lambda _path: (tmp_path, [], [active, paused], [])
    )
    monkeypatch.setattr(
        evaluator,
        "load_json_config",
        lambda _path: {"decisions": {"owner/active": {"decision": "approve"}}},
    )
    monkeypatch.setattr(evaluator, "collect_archive_candidates", lambda *_args: {})
    monkeypatch.setattr(
        evaluator,
        "collect_repo_state",
        lambda _root, repo, *_args, **_kwargs: {
            "repo": repo.repo,
            "status": repo.status,
            "review_status": evaluator.PENDING_REVIEW_STATUS,
            "review_execution": {"status": "executed", "gap_count": 1},
            "issue_queue_status": "round 1 candidates present",
        },
    )
    monkeypatch.setattr(
        evaluator, "write_repo_artifacts", lambda *_args, **_kwargs: calls.append("artifacts")
    )
    monkeypatch.setattr(evaluator, "write_packet", lambda *_args, **_kwargs: calls.append("packet"))
    monkeypatch.setattr(
        evaluator,
        "write_approved_issue_queue",
        lambda *_args, **_kwargs: {"issues": [object()], "deeper_review": [object(), object()]},
    )

    evaluator.main()

    report = json.loads(capsys.readouterr().out)
    assert calls == ["artifacts", "packet"]
    assert report["repo_count"] == 1
    assert report["active_count"] == 1
    assert report["approved_issue_count"] == 1
    assert report["deeper_review_count"] == 2


def test_packet_sections_render_deadlocks_meta_candidates_and_dual_no_new_work_evidence() -> None:
    state = {
        "round2_converged": {
            "converged_candidates": [],
            "deadlocked_candidates": [
                {
                    "title": "Resolve transport ownership",
                    "source_agent": "codex",
                    "round1_index": 2,
                    "marks_history": [
                        {
                            "from_agent": "claude",
                            "mark": "reject",
                            "turn": 3,
                            "reason": "Needs a narrower integration boundary.",
                        }
                    ],
                }
            ],
            "deadlocked_meta": {
                "title": "Audit flaky retry patterns",
                "pattern": "retries without receipt binding",
                "proposed_by": "codex",
                "rejected_by": ["claude"],
                "priority": "high",
                "confidence": "medium",
                "rejection_reasons": {"claude": "Evidence is not yet sufficient."},
            },
            "no_new_work_justifications": [
                {"agent": "codex", "candidate_count": 0, "justification": "a" * 200},
                {"agent": "claude", "candidate_count": 0, "justification": "b" * 200},
            ],
        }
    }

    deadlocks = "\n".join(evaluator.deadlocked_candidates_section(state))
    meta = "\n".join(evaluator.deadlocked_meta_section(state))
    no_new_work = "\n".join(evaluator.no_new_work_justifications_section(state))

    assert "Resolve transport ownership" in deadlocks
    assert "Needs a narrower integration boundary" in deadlocks
    assert "Audit flaky retry patterns" in meta
    assert "Evidence is not yet sufficient" in meta
    assert "Both agents independently reached the same conclusion" in no_new_work
    state["round2_converged"]["converged_candidates"] = [{"title": "New work"}]
    assert evaluator.no_new_work_justifications_section(state) == []


def test_scorecard_queue_paths_hold_invalid_issues_and_surface_unapproved_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluator,
        "approved_scorecard_issue_items",
        lambda *_args: {
            "issues": [
                {
                    "repo": "owner/scorecard",
                    "priority": "high",
                    "scorecard_finding_id": "invalid-body",
                    "body_valid": False,
                    "body_quality_errors": ["missing acceptance criteria"],
                }
            ],
            "pending": [
                {
                    "repo": "owner/scorecard",
                    "finding_id": "not-approved",
                    "check": "Branch-Protection",
                    "score": 0,
                    "reason": "explicit approval is required",
                }
            ],
            "dropped": [{"repo": "owner/scorecard", "candidate_index": 1, "title": "old"}],
            "warnings": ["scorecard data was incomplete"],
        },
    )

    queue = evaluator.build_approved_issue_queue([], {}, "2026-10-22", scorecard_scan={})

    assert queue["issues"] == []
    assert [item["decision"] for item in queue["deeper_review"]] == ["revise", "deeper-review"]
    assert "invalid-body" in queue["deeper_review"][0]["notes"]
    assert "not-approved" in queue["deeper_review"][1]["notes"]
    assert queue["dropped_candidates"][0]["title"] == "old"
    assert queue["warnings"] == ["scorecard data was incomplete"]


def _no_new_work_entry(agent: str, *, candidates: int = 0, chars: int = 200) -> dict[str, object]:
    return {"agent": agent, "candidate_count": candidates, "justification": "x" * chars}


@pytest.mark.parametrize(
    ("entries", "substantive"),
    [
        pytest.param([{"agent": "codex"}, {"agent": "claude"}], 0, id="agent names only"),
        pytest.param(
            [_no_new_work_entry("codex", candidates=2), _no_new_work_entry("claude")],
            1,
            id="one agent proposed candidates",
        ),
        pytest.param(
            [_no_new_work_entry("codex", chars=199), _no_new_work_entry("claude")],
            1,
            id="one justification is 199 characters",
        ),
        pytest.param(
            [_no_new_work_entry("codex", chars=0), _no_new_work_entry("claude")],
            1,
            id="one justification is empty",
        ),
        pytest.param(
            [_no_new_work_entry("codex"), _no_new_work_entry("claude")],
            2,
            id="both justifications are 200 characters",
        ),
    ],
)
def test_no_new_work_surfaces_agree_on_what_is_substantive(
    tmp_path: Path, entries: list[dict[str, object]], substantive: int
) -> None:
    """The recommendation, the packet section, the packet count and the brief's evidence check
    must call the same justifications substantive: one agent that proposed candidates or wrote
    a thin justification is not a completed no-new-work review."""
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "README.md").write_text("# Demo\n", encoding="utf-8")
    config = evaluator.RepoConfig("owner/demo", "demo", "active", "weekly", "demo anchor")
    converged = {
        "schema_version": "v1",
        "repo": "owner/demo",
        "converged_candidates": [],
        "deadlocked_candidates": [],
        "no_new_work_justifications": entries,
    }
    state = evaluator.collect_repo_state(
        tmp_path, config, round2_converged=converged, remote_progress={}
    )

    recommendation = evaluator.issue_set_recommendation(
        {"review_execution": {"gap_count": 0}, "round2_converged": converged}
    )
    section = evaluator.no_new_work_justifications_section(state)
    errors = evaluator.review_summary_quality_errors(state["decision_brief"])
    evaluator.write_packet(tmp_path / "out", [state], generated_on="2026-10-22")
    packet = (tmp_path / "out" / "human-decision-packet.md").read_text(encoding="utf-8")

    complete = substantive >= 2
    assert ("Both agents (codex, claude)" in recommendation) is complete
    assert ("missing or thin" in recommendation) is not complete
    assert bool(section) is complete
    assert ("missing review evidence traces" in errors) is not complete
    assert f"Round 2 dual no-new-work justifications: `{substantive}`" in packet
