import json
from pathlib import Path

import pytest
from scripts import repo_review_round2_runner as runner


def _candidate(title: str = "Keep approved repo-local work") -> dict[str, object]:
    return {
        "title": title,
        "gap": "A reviewed design commitment is not covered by implementation evidence.",
        "current_state": "The repo has source files, but the reviewed path is untested.",
        "required_change": "Add the focused test or workflow guard named by the candidate.",
        "design_refs": ["docs/design.md"],
        "implementation_refs": ["scripts/example.py"],
        "test_refs": ["tests/scripts/test_example.py"],
        "acceptance_criteria": ["The targeted pytest command passes."],
        "non_goals": ["Do not bundle unrelated cleanup."],
        "tasks": ["Add focused coverage.", "Run the targeted check."],
        "priority": "normal",
        "confidence": "high",
    }


def _write_round1_findings(
    path: Path,
    *,
    agent: str,
    repo: str = "stranske/Example",
    candidates: list[dict[str, object]] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "agent": agent,
                "repo": repo,
                "design_summary": "Example repo design summary.",
                "implementation_classification": [],
                "readiness_summary": "Example readiness summary.",
                "remote_progress_check": "No overlap.",
                "archive_dedup_check": "No overlap.",
                "candidates": candidates if candidates is not None else [_candidate()],
                "no_new_work_justification": "",
                "deeper_review_needed": False,
                "deeper_review_reason": "",
            }
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("contents", "exists", "expected"),
    [
        ("  oauth-token-value\n", True, "oauth-token-value"),
        ("   \n", True, None),
        ("", False, None),
    ],
)
def test_read_claude_oauth_token_uses_configured_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contents: str,
    exists: bool,
    expected: str | None,
) -> None:
    token_path = tmp_path / "claude-oauth-token.txt"
    if exists:
        token_path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(runner, "CLAUDE_OAUTH_TOKEN_FILE", token_path)

    assert runner._read_claude_oauth_token() == expected


def test_compute_convergence_uses_implicit_source_agent_agree_keep() -> None:
    key = runner.CandidateKey("codex", 1)
    marks_by_candidate = {
        key: [
            {
                "from_agent": "claude",
                "turn": 1,
                "mark": "agree-keep",
                "reason": "Counterpart verified the candidate has concrete implementation evidence.",
                "merge_proposal": None,
                "revision_proposal": None,
            }
        ]
    }

    result = runner.compute_convergence(
        [key],
        marks_by_candidate,
        expected_marker_agents={"codex", "claude"},
    )

    assert result[key].status == "converged-keep"


def test_synthesize_converged_surfaces_pending_candidate_as_deadlocked(tmp_path: Path) -> None:
    repo = "stranske/Example"
    output_dir = tmp_path / "review"
    codex_path = output_dir / "round1" / "codex" / "stranske__Example" / "findings.json"
    claude_path = output_dir / "round1" / "claude" / "stranske__Example" / "findings.json"
    _write_round1_findings(codex_path, agent="codex", repo=repo)
    _write_round1_findings(claude_path, agent="claude", repo=repo, candidates=[])

    key = runner.CandidateKey("codex", 1)
    marks_by_candidate = {
        key: [
            {
                "from_agent": "claude",
                "turn": 1,
                "mark": "disagree-drop",
                "reason": "Claude found a merged PR that appears to cover the same behavior.",
                "merge_proposal": None,
                "revision_proposal": None,
            }
        ]
    }
    resolutions = runner.compute_convergence(
        [key],
        marks_by_candidate,
        expected_marker_agents={"codex", "claude"},
    )

    payload = runner.synthesize_converged(
        repo=repo,
        output_dir=output_dir,
        round1_paths={"codex": codex_path, "claude": claude_path},
        turn_outputs=[
            {
                "agent": "claude",
                "turn": 1,
                "marks": [
                    {
                        "source_agent": "codex",
                        "candidate_index": 1,
                        "mark": "disagree-drop",
                        "reason": "Claude found a merged PR that appears to cover the same behavior.",
                    }
                ],
                "meta_candidate_proposal": {"proposed": False, "rationale": "No pattern."},
            }
        ],
        turns_completed=3,
        final_resolutions=resolutions,
        meta_proposal=None,
        meta_status="absent",
        deadlocked_reason_max_turns_exhausted=True,
    )

    assert payload["converged_candidates"] == []
    assert payload["deadlocked_candidates"][0]["title"] == "Keep approved repo-local work"
    assert payload["deadlocked_candidates"][0]["source_agent"] == "codex"
