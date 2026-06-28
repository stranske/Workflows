import json
from pathlib import Path

import pytest
from scripts import repo_review_state


def _freeze_time(*values: str):
    queue = list(values)

    def fake_now_iso() -> str:
        if queue:
            return queue.pop(0)
        return values[-1]

    return fake_now_iso


def test_load_state_absent_file_creates_fresh_state_without_writing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(repo_review_state, "now_iso", lambda: "2026-06-27T12:00:00+00:00")
    output_dir = tmp_path / "repo-review"
    repo = "stranske/Example"

    state = repo_review_state.load_state(output_dir, repo)

    assert state.to_dict() == {
        "schema_version": repo_review_state.STATE_SCHEMA_VERSION,
        "repo": repo,
        "status": "fresh",
        "cycle_started_at": "2026-06-27T12:00:00+00:00",
        "cycle_updated_at": "2026-06-27T12:00:00+00:00",
        "last_attempt": None,
        "attempts": [],
        "pinned_problems": [],
        "round1_findings": {},
        "round2_converged_path": "",
        "notes": "",
    }
    assert not repo_review_state.state_file_path(output_dir, repo).exists()


def test_state_round_trips_with_unchanged_json_field_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(repo_review_state, "now_iso", lambda: "2026-06-27T12:05:00+00:00")
    output_dir = tmp_path / "repo-review"
    attempt = repo_review_state.AttemptRecord(
        started_at="2026-06-27T12:01:00+00:00",
        completed_at="2026-06-27T12:02:00+00:00",
        phase="round-1",
        agent="codex",
        succeeded=True,
        notes="ok",
    )
    state = repo_review_state.RepoReviewState(
        schema_version=repo_review_state.STATE_SCHEMA_VERSION,
        repo="stranske/Example",
        status="round1-complete",
        cycle_started_at="2026-06-27T12:00:00+00:00",
        cycle_updated_at="2026-06-27T12:01:00+00:00",
        last_attempt=attempt,
        attempts=[attempt],
        pinned_problems=[
            repo_review_state.PinnedProblem(
                title="Recurring empty test refs",
                first_seen="2026-06-20T12:00:00+00:00",
                last_seen="2026-06-27T12:00:00+00:00",
                occurrences=2,
                notes="surface in packet",
            )
        ],
        round1_findings={"codex": "/tmp/codex/findings.json"},
        round2_converged_path="/tmp/round2/converged.json",
        notes="ready",
    )

    path = repo_review_state.save_state(output_dir, state)
    raw = json.loads(path.read_text(encoding="utf-8"))
    loaded = repo_review_state.load_state(output_dir, "stranske/Example")

    assert list(raw) == [
        "schema_version",
        "repo",
        "status",
        "cycle_started_at",
        "cycle_updated_at",
        "last_attempt",
        "attempts",
        "pinned_problems",
        "round1_findings",
        "round2_converged_path",
        "notes",
    ]
    assert raw["schema_version"] == repo_review_state.STATE_SCHEMA_VERSION
    assert loaded.to_dict() == raw


def test_load_state_rejects_invalid_status(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    repo = "stranske/Example"
    path = repo_review_state.state_file_path(output_dir, repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": repo_review_state.STATE_SCHEMA_VERSION,
                "repo": repo,
                "status": "bogus",
                "cycle_started_at": "2026-06-27T12:00:00+00:00",
                "cycle_updated_at": "2026-06-27T12:00:00+00:00",
                "last_attempt": None,
                "attempts": [],
                "pinned_problems": [],
                "round1_findings": {},
                "round2_converged_path": "",
                "notes": "",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown status.*bogus"):
        repo_review_state.load_state(output_dir, repo)


def test_load_state_reconstructs_pinned_problem_defaults(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    repo = "stranske/Example"
    path = repo_review_state.state_file_path(output_dir, repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": repo_review_state.STATE_SCHEMA_VERSION,
                "repo": repo,
                "status": "human-review-queued",
                "cycle_started_at": "2026-06-27T12:00:00+00:00",
                "cycle_updated_at": "2026-06-27T12:00:00+00:00",
                "last_attempt": None,
                "attempts": [],
                "pinned_problems": [
                    {
                        "title": "Round-2 repeats deadlock",
                        "first_seen": "2026-06-20T12:00:00+00:00",
                        "occurrences": 3,
                        "notes": "needs human triage",
                    }
                ],
                "round1_findings": {},
                "round2_converged_path": "",
                "notes": "",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    state = repo_review_state.load_state(output_dir, repo)

    assert state.pinned_problems == [
        repo_review_state.PinnedProblem(
            title="Round-2 repeats deadlock",
            first_seen="2026-06-20T12:00:00+00:00",
            occurrences=3,
            notes="needs human triage",
        )
    ]
    assert state.pinned_problems[0].to_dict()["last_seen"] == "2026-06-20T12:00:00+00:00"


def test_state_file_path_sanitizes_repo_slash(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    repo = "stranske/Example"

    path = repo_review_state.state_file_path(output_dir, repo)

    assert path == output_dir / "round2" / "stranske__Example" / "state.json"


def test_begin_and_finish_attempt_tracks_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        repo_review_state,
        "now_iso",
        _freeze_time(
            "2026-06-27T12:00:00+00:00",
            "2026-06-27T12:01:00+00:00",
            "2026-06-27T12:02:00+00:00",
            "2026-06-27T12:03:00+00:00",
            "2026-06-27T12:04:00+00:00",
            "2026-06-27T12:05:00+00:00",
        ),
    )
    output_dir = tmp_path / "repo-review"
    repo = "stranske/Example"
    state = repo_review_state.load_state(output_dir, repo)

    first = repo_review_state.begin_attempt(state, phase="round-1", agent="codex")
    repo_review_state.finish_attempt(state, first, succeeded=True, notes="round-1 ok")
    second = repo_review_state.begin_attempt(state, phase="round-2", agent="runner")
    repo_review_state.finish_attempt(state, second, succeeded=False, notes="deadlocked")

    repo_review_state.save_state(output_dir, state)
    loaded = repo_review_state.load_state(output_dir, repo)

    assert loaded.last_attempt == second
    assert [attempt.to_dict() for attempt in loaded.attempts] == [
        {
            "started_at": "2026-06-27T12:01:00+00:00",
            "completed_at": "2026-06-27T12:02:00+00:00",
            "phase": "round-1",
            "agent": "codex",
            "succeeded": True,
            "notes": "round-1 ok",
        },
        {
            "started_at": "2026-06-27T12:03:00+00:00",
            "completed_at": "2026-06-27T12:04:00+00:00",
            "phase": "round-2",
            "agent": "runner",
            "succeeded": False,
            "notes": "deadlocked",
        },
    ]


def test_transition_updates_status_and_note(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(repo_review_state, "now_iso", lambda: "2026-06-27T12:00:00+00:00")
    output_dir = tmp_path / "repo-review"
    repo = "stranske/Example"
    state = repo_review_state.load_state(output_dir, repo)

    repo_review_state.transition(state, status="round1-running", note="starting codex")
    repo_review_state.save_state(output_dir, state)
    loaded = repo_review_state.load_state(output_dir, repo)

    assert loaded.status == "round1-running"
    assert loaded.notes == "starting codex"


def test_transition_rejects_invalid_status() -> None:
    state = repo_review_state.RepoReviewState(
        schema_version=repo_review_state.STATE_SCHEMA_VERSION,
        repo="stranske/Example",
        status="fresh",
        cycle_started_at="2026-06-27T12:00:00+00:00",
        cycle_updated_at="2026-06-27T12:00:00+00:00",
    )

    with pytest.raises(ValueError, match="unknown status.*not-a-status"):
        repo_review_state.transition(state, status="not-a-status")


def test_add_pinned_problem_increments_existing_title(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        repo_review_state,
        "now_iso",
        _freeze_time(
            "2026-06-27T12:00:00+00:00",
            "2026-06-27T12:05:00+00:00",
            "2026-06-27T12:10:00+00:00",
            "2026-06-27T12:15:00+00:00",
            "2026-06-27T12:20:00+00:00",
        ),
    )
    output_dir = tmp_path / "repo-review"
    repo = "stranske/Example"
    state = repo_review_state.load_state(output_dir, repo)

    repo_review_state.add_pinned_problem(
        state,
        title="Round-2 repeats deadlock",
        notes="first sighting",
    )
    repo_review_state.add_pinned_problem(
        state,
        title="Round-2 repeats deadlock",
        notes="seen again",
    )
    repo_review_state.add_pinned_problem(
        state,
        title="Codex emits empty test_refs",
    )
    repo_review_state.save_state(output_dir, state)
    loaded = repo_review_state.load_state(output_dir, repo)

    assert len(loaded.pinned_problems) == 2
    assert loaded.pinned_problems[0].to_dict() == {
        "title": "Round-2 repeats deadlock",
        "first_seen": "2026-06-27T12:05:00+00:00",
        "last_seen": "2026-06-27T12:10:00+00:00",
        "occurrences": 2,
        "notes": "seen again",
    }
    assert loaded.pinned_problems[1].to_dict() == {
        "title": "Codex emits empty test_refs",
        "first_seen": "2026-06-27T12:15:00+00:00",
        "last_seen": "2026-06-27T12:15:00+00:00",
        "occurrences": 1,
        "notes": "",
    }


def test_record_finding_and_converged_paths_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(repo_review_state, "now_iso", lambda: "2026-06-27T12:00:00+00:00")
    output_dir = tmp_path / "repo-review"
    repo = "stranske/Example"
    findings_path = tmp_path / "round1" / "codex" / "findings.json"
    converged_path = tmp_path / "round2" / "converged.json"
    findings_path.parent.mkdir(parents=True)
    converged_path.parent.mkdir(parents=True)
    findings_path.write_text("{}\n", encoding="utf-8")
    converged_path.write_text("{}\n", encoding="utf-8")

    state = repo_review_state.load_state(output_dir, repo)
    repo_review_state.record_round1_finding(state, "codex", findings_path)
    repo_review_state.record_round2_converged(state, converged_path)
    repo_review_state.save_state(output_dir, state)
    loaded = repo_review_state.load_state(output_dir, repo)

    assert loaded.round1_findings == {"codex": str(findings_path.resolve())}
    assert loaded.round2_converged_path == str(converged_path.resolve())
