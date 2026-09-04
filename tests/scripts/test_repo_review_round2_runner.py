import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import repo_review_round2_runner as runner


def test_invoke_codex_uses_supported_approval_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="Usage: codex exec [OPTIONS]\n  --approve-for-me",
            stderr="",
        ),
    )

    def fake_heartbeat(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(
            succeeded=True,
            stuck=False,
            timed_out=False,
            returncode=0,
            note="ok",
        )

    monkeypatch.setattr(runner, "run_with_heartbeat", fake_heartbeat)
    ok, _message = runner.invoke_codex(
        "prompt", cwd=tmp_path, log_file=tmp_path / "codex.log", timeout=30
    )

    assert ok is True
    assert "--approve-for-me" in captured["cmd"]
    assert "--full-auto" not in captured["cmd"]


def test_invoke_codex_falls_back_to_full_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="Usage: codex exec [OPTIONS]\n  --full-auto", stderr=""
        ),
    )
    monkeypatch.setattr(
        runner,
        "run_with_heartbeat",
        lambda cmd, **_kwargs: (
            captured.setdefault("cmd", cmd)
            and SimpleNamespace(
                succeeded=True, stuck=False, timed_out=False, returncode=0, note="ok"
            )
        ),
    )

    ok, _message = runner.invoke_codex(
        "prompt", cwd=tmp_path, log_file=tmp_path / "codex.log", timeout=30
    )

    assert ok is True
    assert "--full-auto" in captured["cmd"]


def test_invoke_codex_rejects_missing_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner.shutil, "which", lambda _name: None)
    ok, message = runner.invoke_codex(
        "prompt", cwd=tmp_path, log_file=tmp_path / "codex.log", timeout=30
    )
    assert ok is False
    assert "not on PATH" in message


@pytest.mark.parametrize(
    ("help_result", "expected"),
    [
        (SimpleNamespace(returncode=1, stdout="", stderr="failed"), "--help failed"),
        (
            SimpleNamespace(returncode=0, stdout="Usage: codex exec", stderr=""),
            "no supported non-interactive approval flag",
        ),
    ],
)
def test_invoke_codex_rejects_bad_capability_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    help_result: SimpleNamespace,
    expected: str,
) -> None:
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(runner.subprocess, "run", lambda *_args, **_kwargs: help_result)
    ok, message = runner.invoke_codex(
        "prompt", cwd=tmp_path, log_file=tmp_path / "codex.log", timeout=30
    )
    assert ok is False
    assert expected in message


def test_invoke_codex_reports_capability_probe_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")

    def raise_oserror(*_args, **_kwargs):
        raise OSError("probe unavailable")

    monkeypatch.setattr(runner.subprocess, "run", raise_oserror)
    ok, message = runner.invoke_codex(
        "prompt", cwd=tmp_path, log_file=tmp_path / "codex.log", timeout=30
    )
    assert ok is False
    assert "probe unavailable" in message


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


def test_claude_capacity_reset_at_parses_stated_timezone(tmp_path: Path) -> None:
    log = tmp_path / "claude.log"
    log.write_text(
        "You've hit your session limit · resets 8pm (America/Chicago)\n",
        encoding="utf-8",
    )

    reset = runner.claude_capacity_reset_at(
        log,
        now=datetime(2026, 9, 4, 22, 42, tzinfo=UTC),
    )

    assert reset == datetime(2026, 9, 5, 1, 0, tzinfo=UTC)


def test_claude_capacity_reset_at_ignores_ordinary_failure(tmp_path: Path) -> None:
    log = tmp_path / "claude.log"
    log.write_text("authentication failed\n", encoding="utf-8")

    assert runner.claude_capacity_reset_at(log) is None


def test_defer_for_claude_capacity_preserves_evidence_and_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "claude.log"
    log.write_text("You've hit your session limit · resets 8pm (America/Chicago)\n")
    now = datetime(2026, 9, 4, 22, 42, tzinfo=UTC)
    slept: list[int] = []
    monkeypatch.setattr(runner, "provider_capacity_wait_max_seconds", lambda: 600)
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: slept.append(seconds))

    ok, _note = runner.defer_for_claude_capacity(
        log,
        now + timedelta(seconds=30),
        now=now,
    )

    assert ok is True
    assert slept == [30 + runner.PROVIDER_CAPACITY_WAIT_GRACE_SECONDS]
    status = json.loads(runner.capacity_wait_path(log).read_text(encoding="utf-8"))
    assert status["state"] == "resuming"
    assert Path(status["preserved_log"]).read_text(encoding="utf-8") == log.read_text(
        encoding="utf-8"
    )


def test_invoke_claude_defers_capacity_without_returning_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "claude.log"
    calls: list[int] = []
    deferred: list[datetime] = []
    reset_at = datetime(2026, 9, 5, 1, 0, tzinfo=UTC)
    monkeypatch.setattr(runner, "_resolve_claude_binary", lambda: "/usr/local/bin/claude")
    monkeypatch.setattr(runner, "_build_claude_env", lambda: {})

    def fake_heartbeat(_cmd, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            kwargs["log_file"].write_text(
                "You've hit your session limit · resets 8pm (America/Chicago)\n",
                encoding="utf-8",
            )
            return SimpleNamespace(
                succeeded=False,
                stuck=False,
                timed_out=False,
                returncode=1,
                note="exited rc=1",
            )
        return SimpleNamespace(
            succeeded=True,
            stuck=False,
            timed_out=False,
            returncode=0,
            note="exited rc=0",
        )

    monkeypatch.setattr(runner, "run_with_heartbeat", fake_heartbeat)
    monkeypatch.setattr(runner, "claude_capacity_reset_at", lambda _log: reset_at)
    monkeypatch.setattr(
        runner,
        "defer_for_claude_capacity",
        lambda _log, reset: (deferred.append(reset) or True, "deferred"),
    )

    ok, _message = runner.invoke_claude(
        "prompt",
        cwd=tmp_path,
        additional_dirs=[tmp_path],
        log_file=log,
        timeout=30,
    )

    assert ok is True
    assert len(calls) == 2
    assert deferred == [reset_at]


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


def test_steward_root_resolves_from_env_or_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.repo_review_round2_runner as mod

    # --- env-set branch ---
    monkeypatch.setenv("REPO_REVIEW_STEWARD_ROOT", str(tmp_path))
    reloaded = importlib.reload(mod)
    assert tmp_path == reloaded.WORKFLOWS_STEWARD

    # --- env-unset branch ---
    monkeypatch.delenv("REPO_REVIEW_STEWARD_ROOT", raising=False)
    reloaded2 = importlib.reload(mod)
    expected = Path(reloaded2.__file__).resolve().parent.parent
    assert expected == reloaded2.WORKFLOWS_STEWARD


def test_run_one_turn_tracks_turn_output_as_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = "stranske/Example"
    output_dir = tmp_path / "review"
    agents = {
        "codex": tmp_path / "codex-findings.json",
        "claude": tmp_path / "claude-findings.json",
    }
    captured: dict[str, tuple[Path, ...]] = {}
    monkeypatch.setattr(runner, "WORKFLOWS_STEWARD", tmp_path)
    monkeypatch.setattr(runner, "build_prompt", lambda **_kwargs: "prompt")

    def fake_invoke(agent_label, _prompt, **kwargs):
        progress_files = kwargs["progress_files"]
        captured[agent_label] = progress_files
        progress_files[0].write_text("{}\n", encoding="utf-8")
        return True, "ok"

    monkeypatch.setattr(runner, "invoke_agent", fake_invoke)
    results = runner.run_one_turn(
        repo=repo,
        turn=1,
        output_dir=output_dir,
        agents=agents,
        additional_dirs=[tmp_path],
        timeout=30,
        retries=0,
        dry_run=False,
        log_dir=tmp_path / "logs",
    )

    assert set(results) == set(agents)
    assert set(captured) == set(agents)
    assert all(result.succeeded for result in results.values())
    for agent_label, progress_files in captured.items():
        assert progress_files == (runner.round2_turn_path(output_dir, repo, 1, agent_label),)
