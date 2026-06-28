import json
from pathlib import Path

import pytest
from scripts import repo_review_state


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
