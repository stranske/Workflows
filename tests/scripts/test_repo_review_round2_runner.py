import importlib
import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import repo_review_body_writer as body_writer
from scripts import repo_review_round2_runner as runner


def test_invoke_codex_uses_supported_approval_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, list[str]] = {}
    monkeypatch.delenv("REPO_REVIEW_CODEX_MODEL", raising=False)
    monkeypatch.delenv("REPO_REVIEW_CODEX_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda cmd, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=(
                "codex-cli 0.153.4"
                if cmd[-1] == "--version"
                else "Usage: codex exec [OPTIONS]\n  --approve-for-me"
            ),
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
    assert captured["cmd"][captured["cmd"].index("--model") + 1] == "gpt-6-astra"
    assert captured["cmd"][captured["cmd"].index("-c") + 1] == ('model_reasoning_effort="high"')


def test_invoke_codex_honors_explicit_repo_review_model_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, list[str]] = {}
    monkeypatch.setenv("REPO_REVIEW_CODEX_MODEL", "gpt-5.6-sol")
    monkeypatch.setenv("REPO_REVIEW_CODEX_REASONING_EFFORT", "medium")
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="--approve-for-me", stderr=""
        ),
    )

    def fake_heartbeat(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(
            succeeded=True, stuck=False, timed_out=False, returncode=0, note="ok"
        )

    monkeypatch.setattr(runner, "run_with_heartbeat", fake_heartbeat)
    ok, _message = runner.invoke_codex(
        "prompt", cwd=tmp_path, log_file=tmp_path / "codex.log", timeout=30
    )

    assert ok is True
    assert captured["cmd"][captured["cmd"].index("--model") + 1] == "gpt-5.6-sol"
    assert captured["cmd"][captured["cmd"].index("-c") + 1] == ('model_reasoning_effort="medium"')


@pytest.mark.parametrize(
    ("body_model", "body_effort", "expected_model", "expected_effort"),
    [
        (None, None, "gpt-5.6-terra", "medium"),
        ("gpt-5.6-luna", "low", "gpt-5.6-luna", "low"),
    ],
)
def test_invoke_codex_separates_body_writer_model_from_reviewer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body_model: str | None,
    body_effort: str | None,
    expected_model: str,
    expected_effort: str,
) -> None:
    captured: dict[str, list[str]] = {}
    monkeypatch.setenv("REPO_REVIEW_CODEX_MODEL", "gpt-6-astra")
    monkeypatch.setenv("REPO_REVIEW_CODEX_REASONING_EFFORT", "high")
    for setting, value in (
        ("REPO_REVIEW_BODY_WRITER_CODEX_MODEL", body_model),
        ("REPO_REVIEW_BODY_WRITER_CODEX_REASONING_EFFORT", body_effort),
    ):
        if value is None:
            monkeypatch.delenv(setting, raising=False)
        else:
            monkeypatch.setenv(setting, value)
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="--approve-for-me", stderr=""
        ),
    )

    def fake_heartbeat(cmd, **_kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(
            succeeded=True, stuck=False, timed_out=False, returncode=0, note="ok"
        )

    monkeypatch.setattr(runner, "run_with_heartbeat", fake_heartbeat)
    ok, _message = runner.invoke_codex(
        "prompt",
        cwd=tmp_path,
        log_file=tmp_path / "codex.log",
        timeout=30,
        purpose="body-writer",
    )

    assert ok is True
    assert captured["cmd"][captured["cmd"].index("--model") + 1] == expected_model
    assert captured["cmd"][captured["cmd"].index("-c") + 1] == (
        f'model_reasoning_effort="{expected_effort}"'
    )


def test_body_writer_routes_codex_with_writing_purpose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(body_writer, "build_prompt", lambda **_kwargs: "prompt")

    def fake_invoke_agent(agent, _prompt, **kwargs):
        captured["agent"] = agent
        captured.update(kwargs)
        return True, "ok"

    monkeypatch.setattr(body_writer, "invoke_agent", fake_invoke_agent)
    ok, _message = body_writer.run_body_writer(
        repo="stranske/Example",
        repo_path=tmp_path / "repo",
        output_dir=tmp_path / "out",
        registry_path=tmp_path / "registry.json",
        workflows_steward_root=tmp_path,
        workspace_root=tmp_path,
        log_dir=tmp_path / "logs",
        timeout=30,
        agent="codex",
    )

    assert ok is True
    assert captured["agent"] == "codex"
    assert captured["codex_purpose"] == "body-writer"


@pytest.mark.parametrize(
    "setting",
    ["REPO_REVIEW_CODEX_MODEL", "REPO_REVIEW_CODEX_REASONING_EFFORT"],
)
def test_invoke_codex_rejects_empty_reviewer_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    monkeypatch.delenv("REPO_REVIEW_CODEX_MODEL", raising=False)
    monkeypatch.delenv("REPO_REVIEW_CODEX_REASONING_EFFORT", raising=False)
    monkeypatch.setenv(setting, " ")
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="--approve-for-me", stderr=""
        ),
    )
    monkeypatch.setattr(
        runner,
        "run_with_heartbeat",
        lambda *_args, **_kwargs: pytest.fail("Codex must not start with an empty setting"),
    )

    ok, message = runner.invoke_codex(
        "prompt", cwd=tmp_path, log_file=tmp_path / "codex.log", timeout=30
    )

    assert ok is False
    assert "must be non-empty" in message


def test_invoke_codex_rejects_astra_with_older_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPO_REVIEW_CODEX_MODEL", raising=False)
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda cmd, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="codex-cli 0.151.0" if cmd[-1] == "--version" else "--approve-for-me",
            stderr="",
        ),
    )
    monkeypatch.setattr(
        runner,
        "run_with_heartbeat",
        lambda *_args, **_kwargs: pytest.fail("incompatible CLI must not start Codex"),
    )

    ok, message = runner.invoke_codex(
        "prompt", cwd=tmp_path, log_file=tmp_path / "codex.log", timeout=30
    )

    assert ok is False
    assert "requires codex-cli >= 0.153.2" in message


def test_invoke_codex_falls_back_to_full_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda cmd, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=(
                "codex-cli 0.153.4"
                if cmd[-1] == "--version"
                else "Usage: codex exec [OPTIONS]\n  --full-auto"
            ),
            stderr="",
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


def _write_round1_provenance(
    path: Path,
    *,
    agent: str,
    repo: str = "stranske/Example",
    source_commit: str = "a" * 40,
) -> None:
    path.with_name("findings.provenance.json").write_text(
        json.dumps(
            {
                "schema": "repo-review-round1-provenance/v1",
                "repo": repo,
                "agent": agent,
                "source_commit": source_commit,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _round2_cache_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, Path, dict[str, Path]]:
    repo = "stranske/Example"
    output_dir = tmp_path / "review"
    agents = {
        "codex": output_dir / "round1" / "codex" / "stranske__Example" / "findings.json",
        "claude": output_dir / "round1" / "claude" / "stranske__Example" / "findings.json",
    }
    for agent, path in agents.items():
        _write_round1_findings(path, agent=agent, repo=repo)
        _write_round1_provenance(path, agent=agent, repo=repo)
    for name in ("prompt", "protocol", "schema"):
        path = tmp_path / f"{name}.md"
        path.write_text(f"{name} v1\n", encoding="utf-8")
        monkeypatch.setattr(runner, f"{name.upper()}_FILE", path)
    return repo, output_dir, agents


def _write_attested_turn_cache(
    *,
    repo: str,
    output_dir: Path,
    agents: dict[str, Path],
    turn: int = 1,
    prior_turn_paths: list[Path] | None = None,
) -> None:
    for agent in agents:
        out_path = runner.round2_turn_path(output_dir, repo, turn, agent)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("{}\n", encoding="utf-8")
        manifest, error = runner.round2_input_manifest(
            repo=repo,
            turn=turn,
            agent=agent,
            round1_paths=agents,
            prior_turn_paths=prior_turn_paths or [],
        )
        assert error == ""
        assert manifest is not None
        runner.write_turn_input_manifest(out_path=out_path, input_manifest=manifest)


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


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "You've hit your weekly limit · resets Sep 5, 8pm (America/Chicago)\n",
            datetime(2026, 9, 6, 1, 0, tzinfo=UTC),
        ),
        (
            "You've hit your usage limit · resets Saturday at 8pm (America/Chicago)\n",
            datetime(2026, 9, 6, 1, 0, tzinfo=UTC),
        ),
        (
            "You've hit your weekly limit · resets 2026-09-05 8pm (America/Chicago)\n",
            datetime(2026, 9, 6, 1, 0, tzinfo=UTC),
        ),
    ],
)
def test_claude_capacity_reset_at_parses_calendar_date_and_weekday(
    tmp_path: Path,
    message: str,
    expected: datetime,
) -> None:
    log = tmp_path / "claude.log"
    log.write_text(message, encoding="utf-8")

    reset = runner.claude_capacity_reset_at(
        log,
        now=datetime(2026, 9, 4, 22, 42, tzinfo=UTC),
    )

    assert reset == expected


def test_claude_capacity_reset_at_ignores_ordinary_failure(tmp_path: Path) -> None:
    log = tmp_path / "claude.log"
    log.write_text("authentication failed\n", encoding="utf-8")

    assert runner.claude_capacity_reset_at(log) is None


def test_defer_for_claude_capacity_preserves_evidence_and_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "claude.log"
    log.write_text(
        "You've hit your session limit · resets 8pm (America/Chicago)\n",
        encoding="utf-8",
    )
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


def test_defer_for_claude_capacity_preserves_rejected_wait_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "claude.log"
    log.write_text(
        "You've hit your weekly limit · resets tomorrow at 8pm (America/Chicago)\n",
        encoding="utf-8",
    )
    now = datetime(2026, 9, 4, 22, 42, tzinfo=UTC)
    monkeypatch.setattr(runner, "provider_capacity_wait_max_seconds", lambda: 60)

    ok, note = runner.defer_for_claude_capacity(
        log,
        now + timedelta(hours=1),
        now=now,
    )

    assert ok is False
    assert "exceeds the configured" in note
    status = json.loads(runner.capacity_wait_path(log).read_text(encoding="utf-8"))
    assert status["state"] == "rejected"
    assert status["reason"] == note
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
        "codex": tmp_path / "codex" / "findings.json",
        "claude": tmp_path / "claude" / "findings.json",
    }
    for agent, findings_path in agents.items():
        _write_round1_findings(findings_path, agent=agent, repo=repo)
        _write_round1_provenance(findings_path, agent=agent, repo=repo)
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
        repo_path=tmp_path / "repo",
        workspace_root=tmp_path,
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


@pytest.mark.parametrize("change", ["findings", "provenance", "protocol", "prior_turn", "output"])
def test_run_one_turn_rejects_receipt_stale_after_peer_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    first_receipt_written = threading.Event()
    first_receipt: str | None = None
    original_write = runner.write_turn_input_manifest
    calls = dict.fromkeys(agents, 0)
    prior = runner.round2_turn_path(output_dir, repo, 1, "codex")
    prior.parent.mkdir(parents=True)
    prior.write_text("{}\n", encoding="utf-8")

    def write_receipt(**kwargs):
        nonlocal first_receipt
        original_write(**kwargs)
        if kwargs["out_path"].stem == "codex":
            first_receipt = runner.round2_input_manifest_path(kwargs["out_path"]).read_text(
                encoding="utf-8"
            )
            first_receipt_written.set()

    def invoke(agent_label, _prompt, **kwargs):
        calls[agent_label] += 1
        if agent_label == "claude":
            assert first_receipt_written.wait(timeout=5), "first production receipt missing"
            if calls[agent_label] == 1:
                if change == "findings":
                    agents["codex"].write_text("changed findings\n", encoding="utf-8")
                elif change == "provenance":
                    for agent, path in agents.items():
                        _write_round1_provenance(
                            path, agent=agent, repo=repo, source_commit="b" * 40
                        )
                elif change == "protocol":
                    runner.PROTOCOL_FILE.write_text("protocol v2\n", encoding="utf-8")
                elif change == "prior_turn":
                    prior.write_text('{"revised": true}\n', encoding="utf-8")
                else:
                    runner.round2_turn_path(output_dir, repo, 2, "codex").write_text(
                        '{"tampered": true}\n', encoding="utf-8"
                    )
        kwargs["progress_files"][0].write_text("{}\n", encoding="utf-8")
        return True, "ok"

    monkeypatch.setattr(runner, "write_turn_input_manifest", write_receipt)
    monkeypatch.setattr(runner, "build_prompt", lambda **_kwargs: "prompt")
    monkeypatch.setattr(runner, "invoke_agent", invoke)
    results = runner.run_one_turn(
        repo=repo,
        turn=2,
        output_dir=output_dir,
        repo_path=tmp_path / "repo",
        workspace_root=tmp_path,
        agents=agents,
        additional_dirs=[tmp_path],
        timeout=30,
        retries=1,
        dry_run=False,
        log_dir=tmp_path / "logs",
    )

    assert calls == {"codex": 1, "claude": 1 if change == "output" else 2}
    assert not results["codex"].succeeded
    assert "pair input binding" in results["codex"].error
    assert results["claude"].succeeded
    assert not results["codex"].output_path.exists()
    preserved = list((output_dir / "repairs" / "round2-stale").glob("**/codex.json"))
    assert preserved, "stale output and its original receipt must be recoverable"
    preserved_receipts = list(
        (output_dir / "repairs" / "round2-stale").glob("**/turn-2-codex.json")
    )
    assert preserved_receipts
    assert first_receipt is not None
    assert preserved_receipts[0].read_text(encoding="utf-8") == first_receipt


def test_run_one_turn_reuses_only_attested_matching_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    _write_attested_turn_cache(repo=repo, output_dir=output_dir, agents=agents)
    monkeypatch.setattr(
        runner,
        "invoke_agent",
        lambda *_args, **_kwargs: pytest.fail("matching cache must be reused"),
    )

    results = runner.run_one_turn(
        repo=repo,
        turn=1,
        output_dir=output_dir,
        repo_path=tmp_path / "repo",
        workspace_root=tmp_path,
        agents=agents,
        additional_dirs=[tmp_path],
        timeout=30,
        retries=0,
        dry_run=False,
        log_dir=tmp_path / "logs",
    )

    assert all(result.succeeded and not result.spawned for result in results.values())


@pytest.mark.parametrize("change", ["findings", "source_commit"])
def test_run_one_turn_regenerates_cache_when_round1_inputs_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    _write_attested_turn_cache(repo=repo, output_dir=output_dir, agents=agents)
    if change == "findings":
        data = json.loads(agents["codex"].read_text(encoding="utf-8"))
        data["design_summary"] = "Changed after the cached turn."
        agents["codex"].write_text(json.dumps(data) + "\n", encoding="utf-8")
    else:
        _write_round1_provenance(agents["codex"], agent="codex", repo=repo, source_commit="b" * 40)
        _write_round1_provenance(
            agents["claude"], agent="claude", repo=repo, source_commit="b" * 40
        )

    invoked: list[str] = []

    def fake_invoke(agent_label, _prompt, **kwargs):
        invoked.append(agent_label)
        kwargs["progress_files"][0].write_text("{}\n", encoding="utf-8")
        return True, "ok"

    monkeypatch.setattr(runner, "WORKFLOWS_STEWARD", tmp_path)
    monkeypatch.setattr(runner, "build_prompt", lambda **_kwargs: "prompt")
    monkeypatch.setattr(runner, "invoke_agent", fake_invoke)

    results = runner.run_one_turn(
        repo=repo,
        turn=1,
        output_dir=output_dir,
        repo_path=tmp_path / "repo",
        workspace_root=tmp_path,
        agents=agents,
        additional_dirs=[tmp_path],
        timeout=30,
        retries=0,
        dry_run=False,
        log_dir=tmp_path / "logs",
    )

    assert set(invoked) == set(agents)
    assert all(result.succeeded and result.spawned for result in results.values())
    assert list((output_dir / "repairs" / "round2-stale").glob("**/codex.json"))
    assert list((output_dir / "repairs" / "round2-stale").glob("**/claude.json"))


@pytest.mark.parametrize("manifest_contents", [None, "{not json"])
def test_run_one_turn_dry_run_rejects_unattested_or_malformed_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manifest_contents: str | None
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    _write_attested_turn_cache(repo=repo, output_dir=output_dir, agents=agents)
    for agent in agents:
        manifest_path = runner.round2_input_manifest_path(
            runner.round2_turn_path(output_dir, repo, 1, agent)
        )
        if manifest_contents is None:
            manifest_path.unlink()
        else:
            manifest_path.write_text(manifest_contents, encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "invoke_agent",
        lambda *_args, **_kwargs: pytest.fail("dry-run must not spawn an agent"),
    )

    results = runner.run_one_turn(
        repo=repo,
        turn=1,
        output_dir=output_dir,
        repo_path=tmp_path / "repo",
        workspace_root=tmp_path,
        agents=agents,
        additional_dirs=[tmp_path],
        timeout=30,
        retries=0,
        dry_run=True,
        log_dir=tmp_path / "logs",
    )

    assert all(not result.succeeded and not result.spawned for result in results.values())
    assert all(
        "dry-run: existing turn output is not reusable" in result.error
        for result in results.values()
    )


def test_verify_turn_input_binding_fails_closed_for_changed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    _write_attested_turn_cache(repo=repo, output_dir=output_dir, agents=agents)
    agents["codex"].write_text("changed findings\n", encoding="utf-8")

    errors = runner.verify_turn_input_binding(
        repo=repo,
        turn=1,
        agent="codex",
        out_path=runner.round2_turn_path(output_dir, repo, 1, "codex"),
        round1_paths=agents,
    )

    assert errors == ["input manifest does not match current round-1/protocol inputs"]


def test_verify_turn_input_binding_rejects_changed_prior_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    _write_attested_turn_cache(repo=repo, output_dir=output_dir, agents=agents, turn=1)
    prior_turn_paths = [runner.round2_turn_path(output_dir, repo, 1, agent) for agent in agents]
    _write_attested_turn_cache(
        repo=repo,
        output_dir=output_dir,
        agents=agents,
        turn=2,
        prior_turn_paths=prior_turn_paths,
    )
    prior_turn_paths[0].write_text('{"changed": true}\n', encoding="utf-8")

    errors = runner.verify_turn_input_binding(
        repo=repo,
        turn=2,
        agent="codex",
        out_path=runner.round2_turn_path(output_dir, repo, 2, "codex"),
        round1_paths=agents,
        prior_turn_paths=prior_turn_paths,
    )

    assert errors == ["input manifest does not match current round-1/protocol inputs"]


def test_verify_turn_input_binding_rejects_replaced_cached_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    _write_attested_turn_cache(repo=repo, output_dir=output_dir, agents=agents)
    out_path = runner.round2_turn_path(output_dir, repo, 1, "codex")
    out_path.write_text('{"replaced": true}\n', encoding="utf-8")

    errors = runner.verify_turn_input_binding(
        repo=repo,
        turn=1,
        agent="codex",
        out_path=out_path,
        round1_paths=agents,
    )

    assert errors == ["cached turn output does not match its input manifest receipt"]


def test_verify_turn_input_binding_survives_output_relocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    _write_attested_turn_cache(repo=repo, output_dir=output_dir, agents=agents, turn=1)
    prior_turn_paths = [runner.round2_turn_path(output_dir, repo, 1, agent) for agent in agents]
    _write_attested_turn_cache(
        repo=repo,
        output_dir=output_dir,
        agents=agents,
        turn=2,
        prior_turn_paths=prior_turn_paths,
    )
    moved_output_dir = tmp_path / "moved-review"
    output_dir.rename(moved_output_dir)
    moved_agents = {
        agent: moved_output_dir / path.relative_to(output_dir) for agent, path in agents.items()
    }
    moved_prior_turns = [
        moved_output_dir / path.relative_to(output_dir) for path in prior_turn_paths
    ]

    errors = runner.verify_turn_input_binding(
        repo=repo,
        turn=2,
        agent="codex",
        out_path=runner.round2_turn_path(moved_output_dir, repo, 2, "codex"),
        round1_paths=moved_agents,
        prior_turn_paths=moved_prior_turns,
    )

    assert errors == []


def _run_args(
    repo: str, output_dir: Path, registry: Path, *, dry_run: bool = True
) -> SimpleNamespace:
    return SimpleNamespace(
        repo=repo,
        output_dir=str(output_dir),
        registry=str(registry),
        agents="codex,claude",
        max_turns=1,
        turn_timeout=30,
        retries=0,
        dry_run=dry_run,
    )


def test_run_synthesizes_empty_round_one_without_spawning_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    for label, path in agents.items():
        _write_round1_findings(path, agent=label, repo=repo, candidates=[])
    repo_path = tmp_path / "reviewed"
    repo_path.mkdir()
    monkeypatch.setattr(
        runner,
        "load_registry",
        lambda _path: (tmp_path, [], [SimpleNamespace(repo=repo, local_path="reviewed")], []),
    )
    monkeypatch.setattr(runner, "resolve_negotiation_agents", lambda *_args: agents)
    monkeypatch.setattr(runner, "validate_reviewed_source_commit", lambda *_args: "")
    monkeypatch.setattr(runner, "validate_converged_set", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        runner,
        "run_one_turn",
        lambda *_args, **_kwargs: pytest.fail("empty findings must skip agent negotiation"),
    )

    assert runner.run(_run_args(repo, output_dir, tmp_path / "registry.json")) == 0
    payload = json.loads(runner.round2_converged_path(output_dir, repo).read_text(encoding="utf-8"))
    assert payload["turns_completed"] == 0
    assert payload["converged_candidates"] == []
    assert {item["agent"] for item in payload["no_new_work_justifications"]} == set(agents)


def test_run_converges_one_turn_and_writes_the_synthesized_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    repo_path = tmp_path / "reviewed"
    repo_path.mkdir()
    monkeypatch.setattr(
        runner,
        "load_registry",
        lambda _path: (tmp_path, [], [SimpleNamespace(repo=repo, local_path="reviewed")], []),
    )
    monkeypatch.setattr(runner, "resolve_negotiation_agents", lambda *_args: agents)
    monkeypatch.setattr(runner, "validate_reviewed_source_commit", lambda *_args: "")
    monkeypatch.setattr(runner, "validate_or_die", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "validate_converged_set", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        runner,
        "run_one_turn",
        lambda **_kwargs: {
            label: runner.AgentTurnResult(label, 1, Path(f"{label}.json"), True, True)
            for label in agents
        },
    )
    turn_outputs = {
        "codex": {
            "agent": "codex",
            "turn": 1,
            "marks": [
                {"source_agent": "codex", "candidate_index": 1, "mark": "agree-keep"},
                {"source_agent": "claude", "candidate_index": 1, "mark": "agree-keep"},
            ],
            "meta_candidate_proposal": {"proposed": False},
        },
        "claude": {
            "agent": "claude",
            "turn": 1,
            "marks": [
                {"source_agent": "codex", "candidate_index": 1, "mark": "agree-keep"},
                {"source_agent": "claude", "candidate_index": 1, "mark": "agree-keep"},
            ],
            "meta_candidate_proposal": {"proposed": False},
        },
    }
    monkeypatch.setattr(runner, "load_turn", lambda path: turn_outputs[path.stem])

    assert runner.run(_run_args(repo, output_dir, tmp_path / "registry.json")) == 0
    payload = json.loads(runner.round2_converged_path(output_dir, repo).read_text(encoding="utf-8"))
    assert payload["turns_completed"] == 1
    assert len(payload["converged_candidates"]) == 2


def test_resolve_negotiation_agents_accepts_one_suffix_and_rejects_ambiguous_or_missing(
    tmp_path: Path,
) -> None:
    repo = "stranske/Example"
    output_dir = tmp_path / "review"
    for agent in ("codex", "pilot-claude"):
        path = runner.round1_findings_path(output_dir, agent, repo)
        _write_round1_findings(path, agent=agent, repo=repo)

    resolved = runner.resolve_negotiation_agents(output_dir, repo, ("codex", "claude"))
    assert set(resolved) == {"codex", "pilot-claude"}

    _write_round1_findings(
        runner.round1_findings_path(output_dir, "alternate-claude", repo),
        agent="alternate-claude",
        repo=repo,
    )
    with pytest.raises(SystemExit, match="ambiguous"):
        runner.resolve_negotiation_agents(output_dir, repo, ("claude",))
    with pytest.raises(SystemExit, match="No round-1 findings"):
        runner.resolve_negotiation_agents(output_dir, repo, ("gemini",))


def test_run_persists_a_completed_round_when_not_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    for label, path in agents.items():
        _write_round1_findings(path, agent=label, repo=repo, candidates=[])
    (tmp_path / "reviewed").mkdir()
    calls: list[str] = []
    monkeypatch.setattr(
        runner,
        "load_registry",
        lambda _path: (tmp_path, [], [SimpleNamespace(repo=repo, local_path="reviewed")], []),
    )
    monkeypatch.setattr(runner, "resolve_negotiation_agents", lambda *_args: agents)
    monkeypatch.setattr(runner, "validate_reviewed_source_commit", lambda *_args: "")
    monkeypatch.setattr(runner, "validate_converged_set", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(runner, "load_state", lambda *_args: {"status": "round1-complete"})
    monkeypatch.setattr(runner, "begin_attempt", lambda *_args, **_kwargs: {"id": "attempt"})
    monkeypatch.setattr(runner, "finish_attempt", lambda *_args, **_kwargs: calls.append("finish"))
    monkeypatch.setattr(runner, "record_round2_converged", lambda *_args: calls.append("record"))
    monkeypatch.setattr(
        runner, "transition", lambda *_args, **kwargs: calls.append(kwargs["status"])
    )
    monkeypatch.setattr(runner, "save_state", lambda *_args: calls.append("save"))
    monkeypatch.setattr(
        runner,
        "run_one_turn",
        lambda *_args, **_kwargs: pytest.fail("empty findings must not run agents"),
    )

    assert runner.run(_run_args(repo, output_dir, tmp_path / "registry.json", dry_run=False)) == 0
    assert calls == ["finish", "record", "round2-converged", "save"]


def test_resolve_claude_binary_prefers_verified_desktop_install_then_path_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desktop_root = tmp_path / "claude-code"
    older = desktop_root / "2.1.45" / "claude.app" / "Contents" / "MacOS" / "claude"
    newer = desktop_root / "2.1.128" / "claude.app" / "Contents" / "MacOS" / "claude"
    for binary in (older, newer):
        binary.parent.mkdir(parents=True)
        binary.write_text("", encoding="utf-8")
    monkeypatch.delenv("CLAUDE_CODE_EXECPATH", raising=False)
    monkeypatch.setattr(runner.os.path, "expanduser", lambda _path: str(desktop_root))
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/path/claude")

    assert runner._resolve_claude_binary() == str(newer)
    monkeypatch.setenv("CLAUDE_CODE_EXECPATH", str(older))
    assert runner._resolve_claude_binary() == str(older)
    monkeypatch.setenv("CLAUDE_CODE_EXECPATH", str(tmp_path / "missing"))
    monkeypatch.setattr(runner.Path, "is_dir", lambda self: False)
    assert runner._resolve_claude_binary() == "/path/claude"


def test_invoke_agent_routes_pilot_labels_and_rejects_unknown_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        runner,
        "invoke_codex",
        lambda *_args, **_kwargs: (calls.append("codex") or True, "ok"),
    )
    monkeypatch.setattr(
        runner,
        "invoke_claude",
        lambda *_args, **_kwargs: (calls.append("claude") or True, "ok"),
    )

    assert runner.invoke_agent(
        "pilot-codex",
        "prompt",
        cwd=tmp_path,
        additional_dirs=[],
        log_file=tmp_path / "x",
        timeout=1,
    ) == (True, "ok")
    assert runner.invoke_agent(
        "pilot-claude",
        "prompt",
        cwd=tmp_path,
        additional_dirs=[],
        log_file=tmp_path / "x",
        timeout=1,
    ) == (True, "ok")
    ok, message = runner.invoke_agent(
        "gemini", "prompt", cwd=tmp_path, additional_dirs=[], log_file=tmp_path / "x", timeout=1
    )
    assert not ok and "unknown agent label" in message
    assert calls == ["codex", "claude"]


@pytest.mark.parametrize(
    ("provenance", "expected"),
    [
        ({}, "schema=None"),
        (
            {
                "schema": "repo-review-round1-provenance/v1",
                "repo": "stranske/Elsewhere",
                "agent": "codex",
                "source_commit": "a" * 40,
            },
            "repo='stranske/Elsewhere'",
        ),
        (
            {
                "schema": "repo-review-round1-provenance/v1",
                "repo": "stranske/Example",
                "agent": "codex",
            },
            "source_commit is missing",
        ),
    ],
)
def test_round2_input_manifest_rejects_invalid_round1_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provenance: dict[str, str],
    expected: str,
) -> None:
    repo, _output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    agents["codex"].with_name("findings.provenance.json").write_text(
        json.dumps(provenance), encoding="utf-8"
    )

    manifest, error = runner.round2_input_manifest(
        repo=repo, turn=1, agent="codex", round1_paths=agents
    )

    assert manifest is None
    assert expected in error


def test_round2_input_manifest_rejects_mismatched_source_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    _write_round1_provenance(agents["claude"], agent="claude", repo=repo, source_commit="b" * 40)

    manifest, error = runner.round2_input_manifest(
        repo=repo, turn=1, agent="codex", round1_paths=agents
    )

    assert manifest is None
    assert error == "round-1 findings provenance source commits do not match"


@pytest.mark.parametrize(
    ("agent_proposals", "expected_status", "expect_proposal"),
    [
        ({}, "absent", False),
        # single-side has two shapes: the other agent's entry is missing (nothing is returned),
        # or present without a proposal (the lone proposal is returned).
        ({"codex": {"proposed": True}}, "single-side", False),
        ({"codex": {"proposed": True}, "claude": {}}, "single-side", True),
        (
            {"codex": {"proposed": True}, "claude": {"proposed": False}},
            "deadlocked",
            True,
        ),
        (
            {
                "codex": {
                    "proposed": True,
                    "supporting_candidate_indexes": [{"agent": "codex", "candidate_index": 1}],
                },
                "claude": {
                    "proposed": True,
                    "supporting_candidate_indexes": [{"agent": "claude", "candidate_index": 2}],
                },
            },
            "deadlocked",
            False,
        ),
    ],
)
def test_converge_meta_handles_absence_single_side_and_disagreement(
    agent_proposals: dict[str, dict[str, object]], expected_status: str, expect_proposal: bool
) -> None:
    proposal, status = runner.converge_meta(agent_proposals, {"codex", "claude"})

    assert status == expected_status
    assert (proposal is not None) is expect_proposal


def test_validate_reviewed_source_commit_rejects_bad_head_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="nope"),
    )
    assert (
        runner.validate_reviewed_source_commit(tmp_path, agents)
        == "cannot resolve reviewed repo HEAD"
    )

    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="b" * 40 + "\n", stderr=""),
    )
    assert "does not match reviewed repo HEAD" in runner.validate_reviewed_source_commit(
        tmp_path, agents
    )


def test_run_returns_failure_for_missing_registry_repo_or_reviewed_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = _run_args("stranske/Example", tmp_path / "out", tmp_path / "registry.json")
    monkeypatch.setattr(runner, "load_registry", lambda _path: (tmp_path, [], [], []))
    assert runner.run(args) == 2

    monkeypatch.setattr(
        runner,
        "load_registry",
        lambda _path: (tmp_path, [], [SimpleNamespace(repo=args.repo, local_path="missing")], []),
    )
    assert runner.run(args) == 2


def test_run_returns_failure_for_source_error_and_failed_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, output_dir, agents = _round2_cache_inputs(tmp_path, monkeypatch)
    (tmp_path / "reviewed").mkdir()
    monkeypatch.setattr(
        runner,
        "load_registry",
        lambda _path: (tmp_path, [], [SimpleNamespace(repo=repo, local_path="reviewed")], []),
    )
    monkeypatch.setattr(runner, "resolve_negotiation_agents", lambda *_args: agents)
    monkeypatch.setattr(runner, "validate_reviewed_source_commit", lambda *_args: "stale source")
    assert runner.run(_run_args(repo, output_dir, tmp_path / "registry.json")) == 2

    monkeypatch.setattr(runner, "validate_reviewed_source_commit", lambda *_args: "")
    monkeypatch.setattr(
        runner,
        "run_one_turn",
        lambda **_kwargs: {
            label: runner.AgentTurnResult(label, 1, Path(label), False, False, "no output")
            for label in agents
        },
    )
    assert runner.run(_run_args(repo, output_dir, tmp_path / "registry.json")) == 2


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            SimpleNamespace(succeeded=False, stuck=True, timed_out=False, returncode=1, note="x"),
            "stuck",
        ),
        (
            SimpleNamespace(succeeded=False, stuck=False, timed_out=True, returncode=1, note="x"),
            "timed out",
        ),
        (
            SimpleNamespace(
                succeeded=False, stuck=False, timed_out=False, returncode=7, note="bad"
            ),
            "exited 7",
        ),
    ],
)
def test_invoke_codex_reports_heartbeat_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: SimpleNamespace, expected: str
) -> None:
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda cmd, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="codex-cli 0.153.4" if cmd[-1] == "--version" else "--approve-for-me",
            stderr="",
        ),
    )
    monkeypatch.setattr(runner, "run_with_heartbeat", lambda *_args, **_kwargs: result)

    ok, message = runner.invoke_codex("prompt", cwd=tmp_path, log_file=tmp_path / "log", timeout=30)

    assert not ok
    assert expected in message


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            SimpleNamespace(succeeded=True, stuck=False, timed_out=False, returncode=0, note="ok"),
            None,
        ),
        (
            SimpleNamespace(succeeded=False, stuck=True, timed_out=False, returncode=1, note="x"),
            "stuck",
        ),
        (
            SimpleNamespace(succeeded=False, stuck=False, timed_out=True, returncode=1, note="x"),
            "timed out",
        ),
        (
            SimpleNamespace(
                succeeded=False, stuck=False, timed_out=False, returncode=7, note="bad"
            ),
            "exited 7",
        ),
    ],
)
def test_invoke_claude_handles_heartbeat_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: SimpleNamespace, expected: str | None
) -> None:
    monkeypatch.setattr(runner, "_resolve_claude_binary", lambda: "/usr/local/bin/claude")
    monkeypatch.setattr(runner, "_build_claude_env", lambda: {"PATH": "/usr/bin"})
    monkeypatch.setattr(runner, "run_with_heartbeat", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(runner, "claude_capacity_reset_at", lambda _path: None)

    ok, message = runner.invoke_claude(
        "prompt", cwd=tmp_path, additional_dirs=[tmp_path], log_file=tmp_path / "log", timeout=30
    )

    assert ok is (expected is None)
    if expected is None:
        assert message == str(tmp_path / "log")
    else:
        assert expected in message


def test_invoke_claude_rejects_missing_binary_and_builds_a_clean_token_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "_resolve_claude_binary", lambda: None)
    ok, message = runner.invoke_claude(
        "prompt", cwd=tmp_path, additional_dirs=[], log_file=tmp_path / "log", timeout=30
    )
    assert not ok
    assert "not found" in message

    monkeypatch.setenv("CLAUDECODE", "host-managed")
    monkeypatch.setenv("USER", "must-not-leak")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(runner, "_read_claude_oauth_token", lambda: "token")
    env = runner._build_claude_env()
    assert env["PATH"] == "/usr/bin"
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "token"
    assert "CLAUDECODE" not in env
    assert "USER" not in env


def test_synthesize_converged_collapses_duplicate_merges_and_surfaces_human_work(
    tmp_path: Path,
) -> None:
    repo = "stranske/Example"
    output_dir = tmp_path / "review"
    codex_path = runner.round1_findings_path(output_dir, "codex", repo)
    claude_path = runner.round1_findings_path(output_dir, "claude", repo)
    _write_round1_findings(
        codex_path,
        agent="codex",
        repo=repo,
        candidates=[_candidate("First"), _candidate("Second"), _candidate("Dropped")],
    )
    _write_round1_findings(claude_path, agent="claude", repo=repo, candidates=[])
    proposal = {"title": "Merged seam", "required_change": "One joined change."}
    resolutions = {
        runner.CandidateKey("codex", 1): runner.CandidateResolution(
            key=runner.CandidateKey("codex", 1),
            status="converged-merge",
            merge_proposal=proposal,
        ),
        runner.CandidateKey("codex", 2): runner.CandidateResolution(
            key=runner.CandidateKey("codex", 2),
            status="converged-merge",
            merge_proposal=proposal,
        ),
        runner.CandidateKey("codex", 3): runner.CandidateResolution(
            key=runner.CandidateKey("codex", 3),
            status="converged-drop",
            drop_reason="Already done.",
        ),
    }
    meta = {
        "title": "Audit recurring seam",
        "pattern": "Shared implementation gap",
        "rationale": "Several candidates point at it.",
        "supporting_candidate_indexes": [{"agent": "codex", "candidate_index": 1}],
        "priority": "low",
        "confidence": "low",
        "__rejected_by": ["claude"],
    }
    payload = runner.synthesize_converged(
        repo=repo,
        output_dir=output_dir,
        round1_paths={"codex": codex_path, "claude": claude_path},
        turn_outputs=[
            {"agent": "codex", "turn": 1, "meta_candidate_proposal": {"proposed": True}},
            {
                "agent": "claude",
                "turn": 1,
                "meta_candidate_proposal": {"proposed": False, "rationale": "Not systemic."},
            },
        ],
        turns_completed=1,
        final_resolutions=resolutions,
        meta_proposal=meta,
        meta_status="deadlocked",
        deadlocked_reason_max_turns_exhausted=False,
    )

    assert [candidate["title"] for candidate in payload["converged_candidates"]] == ["Merged seam"]
    assert payload["converged_candidates"][0]["origin"]["merged_from"] == [
        {"agent": "codex", "round1_index": 1},
        {"agent": "codex", "round1_index": 2},
    ]
    assert payload["dropped_candidates"] == [
        {
            "title": "Dropped",
            "source_agent": "codex",
            "round1_index": 3,
            "drop_reason": "Already done.",
        }
    ]
    assert payload["deadlocked_meta"]["rejection_reasons"] == {"claude": "Not systemic."}


def test_meta_convergence_merges_compatible_proposals_and_inherits_unique_refs() -> None:
    codex = _candidate("Codex candidate")
    codex["design_refs"] = ["docs/shared.md", "docs/codex.md"]
    claude = _candidate("Claude candidate")
    claude["design_refs"] = ["docs/shared.md", "docs/claude.md"]
    index = {
        runner.CandidateKey("codex", 1): codex,
        runner.CandidateKey("claude", 1): claude,
    }
    codex_meta = {
        "proposed": True,
        "title": "Audit shared seam",
        "pattern": "The shared seam needs an audit.",
        "tasks": ["enumerate", "classify", "file"],
        "acceptance_criteria": ["report", "issues", "gate"],
        "supporting_candidate_indexes": [
            {"agent": "codex", "candidate_index": 1},
            "ignore this malformed reference",
        ],
    }
    claude_meta = {
        "proposed": True,
        "title": "Alternative title",
        "pattern": "Short",
        "tasks": ["enumerate"],
        "acceptance_criteria": [],
        "supporting_candidate_indexes": [{"agent": "claude", "candidate_index": 1}],
    }

    merged, status = runner.converge_meta(
        {"codex": codex_meta, "claude": claude_meta}, {"codex", "claude"}
    )

    assert status == "deadlocked"
    assert merged is None

    claude_meta["supporting_candidate_indexes"].append({"agent": "codex", "candidate_index": 1})
    merged, status = runner.converge_meta(
        {"codex": codex_meta, "claude": claude_meta}, {"codex", "claude"}
    )

    assert status == "converged"
    assert merged is not None
    assert merged["primary_source_agent"] == "codex"
    candidate = runner.meta_to_candidate(merged, "codex", index)
    assert candidate["design_refs"] == ["docs/shared.md", "docs/claude.md", "docs/codex.md"]
    assert candidate["scope"] == "audit"


def test_round2_manifest_and_discovery_fail_closed_on_malformed_inputs(tmp_path: Path) -> None:
    repo = "stranske/Example"
    findings = tmp_path / "round1" / "codex" / "stranske__Example" / "findings.json"
    findings.parent.mkdir(parents=True)
    findings.write_text("{}", encoding="utf-8")
    provenance = findings.with_name("findings.provenance.json")
    provenance.write_text("not json", encoding="utf-8")

    manifest, error = runner.round2_input_manifest(
        repo=repo, turn=1, agent="codex", round1_paths={"codex": findings}
    )

    assert manifest is None
    assert "cannot read codex findings provenance" in error
    assert runner.discover_round1_agents(tmp_path, repo) == {"codex": findings}
    (tmp_path / "round1" / "not-an-agent").write_text("file", encoding="utf-8")
    assert runner.discover_round1_agents(tmp_path, repo) == {"codex": findings}


@pytest.mark.parametrize(
    ("purpose", "expected"),
    [("unexpected", "unknown repo-review Codex purpose"), ("review", "could not verify Codex CLI")],
)
def test_invoke_codex_rejects_invalid_purpose_and_unverifiable_astra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, purpose: str, expected: str
) -> None:
    monkeypatch.setenv("REPO_REVIEW_CODEX_MODEL", "gpt-6-astra")
    monkeypatch.setattr(
        runner,
        "run_with_heartbeat",
        lambda *_args, **_kwargs: pytest.fail("invalid invocation must not start Codex"),
    )
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda cmd, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="--approve-for-me" if cmd[-1] == "--help" else "not a version",
            stderr="",
        ),
    )

    ok, message = runner.invoke_codex(
        "prompt", cwd=tmp_path, log_file=tmp_path / "codex.log", timeout=30, purpose=purpose
    )

    assert not ok
    assert expected in message


def test_claude_capacity_parser_and_deferral_fail_closed_on_bad_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "claude.log"
    log.write_text("You've hit your session limit · resets 8pm (Bad/Timezone)\n", encoding="utf-8")
    assert runner.claude_capacity_reset_at(log) is None

    log.write_text("You've hit your session limit · resets 8pm (UTC)\n", encoding="utf-8")
    monkeypatch.setattr(
        runner.shutil, "copy2", lambda *_args: (_ for _ in ()).throw(OSError("disk"))
    )
    ok, message = runner.defer_for_claude_capacity(
        log,
        datetime(2026, 9, 4, 20, 1, tzinfo=UTC),
        now=datetime(2026, 9, 4, 20, 0, tzinfo=UTC),
    )
    assert not ok
    assert "cannot preserve Claude capacity evidence" in message


@pytest.mark.parametrize(
    ("marks", "expected_status"),
    [
        (
            [
                {
                    "from_agent": "codex",
                    "turn": 1,
                    "mark": "agree-merge",
                    "merge_proposal": {"title": "Merge"},
                },
                {
                    "from_agent": "claude",
                    "turn": 1,
                    "mark": "agree-merge",
                    "merge_proposal": {"title": "Merge"},
                },
            ],
            "converged-merge",
        ),
        (
            [
                {"from_agent": "codex", "turn": 1, "mark": "agree-keep"},
                {
                    "from_agent": "claude",
                    "turn": 1,
                    "mark": "agree-merge",
                    "merge_proposal": {"title": "Merge"},
                },
            ],
            "converged-merge",
        ),
        (
            [
                {"from_agent": "codex", "turn": 1, "mark": "disagree-drop", "reason": "Duplicate"},
                {
                    "from_agent": "claude",
                    "turn": 1,
                    "mark": "disagree-drop",
                    "reason": "Already covered",
                },
            ],
            "converged-drop",
        ),
    ],
)
def test_compute_convergence_handles_merge_and_drop_outcomes(
    marks: list[dict[str, object]], expected_status: str
) -> None:
    key = runner.CandidateKey("codex", 1)

    resolution = runner.compute_convergence([key], {key: marks}, {"codex", "claude"})[key]

    assert resolution.status == expected_status
    if expected_status == "converged-drop":
        assert resolution.drop_reason == "Duplicate; Already covered"
    else:
        assert resolution.merge_proposal == {"title": "Merge"}


def test_compute_convergence_waits_for_a_missing_non_source_agent() -> None:
    key = runner.CandidateKey("codex", 1)

    resolution = runner.compute_convergence([key], {key: []}, {"codex", "claude"})[key]

    assert resolution.status == "pending"


def test_parse_args_and_main_preserve_the_cli_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    args = runner.parse_args(
        [
            "--repo",
            "stranske/Example",
            "--output-dir",
            "out",
            "--registry",
            "registry.json",
            "--agents",
            "pilot-codex,pilot-claude",
            "--max-turns",
            "4",
            "--turn-timeout",
            "60",
            "--retries",
            "1",
            "--dry-run",
        ]
    )
    assert (args.repo, args.max_turns, args.dry_run) == ("stranske/Example", 4, True)

    monkeypatch.setattr(
        runner, "run", lambda received: 7 if received.repo == "stranske/Example" else 1
    )
    assert runner.main(["--repo", "stranske/Example", "--output-dir", "out"]) == 7


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (None, runner.DEFAULT_PROVIDER_CAPACITY_WAIT_MAX_SECONDS),
        ("bad", runner.DEFAULT_PROVIDER_CAPACITY_WAIT_MAX_SECONDS),
        ("-5", 0),
        ("42", 42),
    ],
)
def test_provider_capacity_wait_budget_handles_environment_values(
    monkeypatch: pytest.MonkeyPatch, configured: str | None, expected: int
) -> None:
    if configured is None:
        monkeypatch.delenv("REPO_REVIEW_CAPACITY_WAIT_MAX_SECONDS", raising=False)
    else:
        monkeypatch.setenv("REPO_REVIEW_CAPACITY_WAIT_MAX_SECONDS", configured)
    assert runner.provider_capacity_wait_max_seconds() == expected


def test_claude_capacity_parser_handles_tomorrow_and_malformed_dates(tmp_path: Path) -> None:
    log = tmp_path / "claude.log"
    now = datetime(2026, 9, 4, 22, 42, tzinfo=UTC)
    log.write_text(
        "You've hit your session limit · resets tomorrow at 8pm (UTC)\n", encoding="utf-8"
    )
    assert runner.claude_capacity_reset_at(log, now=now) == datetime(2026, 9, 5, 20, 0, tzinfo=UTC)

    log.write_text("You've hit your session limit · resets Feb 30 8pm (UTC)\n", encoding="utf-8")
    assert runner.claude_capacity_reset_at(log, now=now) is None


def test_prompt_and_local_helpers_cover_empty_and_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = runner.build_prompt(
        repo="stranske/Example",
        turn=2,
        my_agent="codex",
        other_agent="claude",
        my_findings=tmp_path / "mine.json",
        other_findings=tmp_path / "other.json",
        repo_path=tmp_path,
        turn_output_path=tmp_path / "out.json",
        prior_turn_paths=[tmp_path / "turn-1" / "codex.json"],
    )
    assert "Prior-turn outputs" in prompt

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="failed schema validation"):
        runner.validate_or_die({}, invalid, "stranske/Example")
    assert runner.load_turn(invalid) == {}

    missing = runner.CandidateResolution(runner.CandidateKey("codex", 1), "converged-keep")
    with pytest.raises(SystemExit, match="missing from index"):
        runner.candidate_for_resolution(missing, {})

    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("git unavailable")),
    )
    assert "cannot resolve reviewed repo HEAD" in runner.validate_reviewed_source_commit(
        tmp_path, {}
    )


def test_preserve_stale_output_moves_the_receipt(tmp_path: Path) -> None:
    out = runner.round2_turn_path(tmp_path, "stranske/Example", 1, "codex")
    out.parent.mkdir(parents=True)
    out.write_text("{}", encoding="utf-8")
    receipt = runner.round2_input_manifest_path(out)
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}", encoding="utf-8")

    assert (
        runner.preserve_stale_turn_output(
            output_dir=tmp_path, repo="stranske/Example", out_path=out
        )
        == ""
    )
    assert not out.exists()
    assert not receipt.exists()
    assert list((tmp_path / "repairs" / "round2-stale").rglob("codex.json"))


@pytest.mark.parametrize(
    ("dry_run", "manifest", "invocation", "expected"),
    [
        (False, None, None, "bad manifest"),
        (True, {"schema": "v1"}, None, "turn output absent"),
        (False, {"schema": "v1"}, (False, "runner failed"), "runner failed"),
    ],
)
def test_run_one_turn_reports_unspawnable_or_missing_agent_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dry_run: bool,
    manifest: dict[str, str] | None,
    invocation: tuple[bool, str] | None,
    expected: str,
) -> None:
    agents = {"codex": tmp_path / "codex.json", "claude": tmp_path / "claude.json"}
    monkeypatch.setattr(
        runner,
        "round2_input_manifest",
        lambda **_kwargs: (manifest, "bad manifest" if manifest is None else ""),
    )
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    if invocation is not None:
        monkeypatch.setattr(runner, "invoke_agent", lambda *_args, **_kwargs: invocation)

    results = runner.run_one_turn(
        repo="stranske/Example",
        turn=1,
        output_dir=tmp_path / "out",
        repo_path=tmp_path,
        workspace_root=tmp_path,
        agents=agents,
        additional_dirs=[],
        timeout=1,
        retries=0,
        dry_run=dry_run,
        log_dir=tmp_path / "logs",
    )

    assert all(not result.succeeded for result in results.values())
    assert all(expected in result.error for result in results.values())


def test_run_rejects_invalid_agent_count_before_loading_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reviewed = tmp_path / "reviewed"
    reviewed.mkdir()
    args = _run_args("stranske/Example", tmp_path / "out", tmp_path / "registry.json")
    args.agents = "codex"
    monkeypatch.setattr(
        runner,
        "load_registry",
        lambda _path: (tmp_path, [], [SimpleNamespace(repo=args.repo, local_path="reviewed")], []),
    )

    with pytest.raises(SystemExit, match="exactly two labels"):
        runner.run(args)


def test_synthesize_converged_builds_a_compatible_meta_candidate(tmp_path: Path) -> None:
    repo = "stranske/Example"
    output_dir = tmp_path / "review"
    codex_path = runner.round1_findings_path(output_dir, "codex", repo)
    _write_round1_findings(codex_path, agent="codex", repo=repo)
    meta = {
        "title": "Audit seam",
        "pattern": "One recurring seam",
        "rationale": "Evidence supports an audit.",
        "supporting_candidate_indexes": [{"agent": "codex", "candidate_index": 1}],
        "tasks": ["enumerate"],
        "acceptance_criteria": ["report"],
    }
    payload = runner.synthesize_converged(
        repo=repo,
        output_dir=output_dir,
        round1_paths={"codex": codex_path},
        turn_outputs=[{"agent": "codex", "turn": 1, "meta_candidate_proposal": {"proposed": True}}],
        turns_completed=1,
        final_resolutions={},
        meta_proposal=meta,
        meta_status="converged",
        deadlocked_reason_max_turns_exhausted=False,
    )

    assert payload["meta_candidate"]["title"] == "Audit seam"
    assert payload["meta_candidate"]["design_refs"] == ["docs/design.md"]
