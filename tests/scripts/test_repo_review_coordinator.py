import json
from pathlib import Path
from types import SimpleNamespace

from scripts import repo_review_coordinator as coordinator
from scripts import repo_review_state


def _candidate(title: str = "Keep approved repo-local work") -> dict[str, object]:
    return {
        "title": title,
        "gap": "A reviewed design commitment still lacks executable coverage.",
        "design_refs": ["docs/design.md"],
    }


def _write_round1_findings(
    output_dir: Path,
    repo: str,
    agent: str,
    candidates: list[dict[str, object]],
) -> None:
    safe = repo.replace("/", "__")
    path = output_dir / "round1" / agent / safe / "findings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "agent": agent,
                "repo": repo,
                "candidates": candidates,
                "no_new_work_justification": "",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_prior_converged(
    output_dir: Path,
    repo: str,
    candidates: list[dict[str, object]],
) -> None:
    safe = repo.replace("/", "__")
    path = output_dir / "archive" / "2026-05-01" / "round2" / safe / "converged.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "repo": repo,
                "turns_completed": 1,
                "round1_sources": [],
                "converged_candidates": candidates,
                "deadlocked_candidates": [],
                "dropped_candidates": [],
                "meta_candidate": None,
                "meta_status": "absent",
                "deadlocked_meta": None,
                "no_new_work_justifications": [],
                "negotiation_log": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_should_skip_cycle_when_round1_fingerprint_matches_prior_cycle(tmp_path: Path) -> None:
    repo = "stranske/Example"
    output_dir = tmp_path / "repo-review"
    candidates = [_candidate("Codex candidate"), _candidate("Claude candidate")]
    _write_prior_converged(output_dir, repo, candidates)
    _write_round1_findings(output_dir, repo, "codex", [candidates[0]])
    _write_round1_findings(output_dir, repo, "claude", [candidates[1]])

    should_skip, reason = coordinator.should_skip_cycle(
        output_dir,
        repo,
        ["codex", "claude"],
    )

    assert should_skip is True
    assert "fingerprint matches prior cycle" in reason


def test_coordinate_repo_writes_skip_converged_and_round2_state(
    tmp_path: Path, monkeypatch
) -> None:
    repo = "stranske/Example"
    output_dir = tmp_path / "repo-review"
    candidates = [_candidate("Codex candidate"), _candidate("Claude candidate")]
    _write_prior_converged(output_dir, repo, candidates)

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        _write_round1_findings(output_dir, repo, "codex", [candidates[0]])
        _write_round1_findings(output_dir, repo, "claude", [candidates[1]])
        return coordinator.StepResult(name=name, succeeded=True, duration_seconds=0.01)

    monkeypatch.setattr(coordinator, "run_subprocess", fake_run_subprocess)

    report = coordinator.coordinate_repo(
        repo=repo,
        output_dir=output_dir,
        workflows_steward_root=tmp_path,
        registry_path=tmp_path / "config" / "repo_review_registry.json",
        agents=["codex", "claude"],
        log_dir=output_dir / "logs" / "coordinator",
        round1_timeout=30,
        round2_timeout=30,
        skip_gate_enabled=True,
    )

    state = repo_review_state.load_state(output_dir, repo)
    converged = json.loads(
        (output_dir / "round2" / "stranske__Example" / "converged.json").read_text(encoding="utf-8")
    )
    assert report["skip_gate_fired"] is True
    assert state.status == "round2-converged"
    assert converged["synthesized_via_skip_gate"] is True


def test_coordinate_repo_allows_mocked_round1_to_round2_state_progression(
    tmp_path: Path, monkeypatch
) -> None:
    repo = "stranske/Example"
    output_dir = tmp_path / "repo-review"
    seen_steps: list[str] = []

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        state = repo_review_state.load_state(output_dir, repo)
        if name == "round-1":
            repo_review_state.transition(state, status="round1-running")
            repo_review_state.save_state(output_dir, state)
            state = repo_review_state.load_state(output_dir, repo)
            repo_review_state.transition(state, status="round1-complete")
            repo_review_state.save_state(output_dir, state)
        elif name == "round-2":
            repo_review_state.transition(state, status="round2-running")
            repo_review_state.save_state(output_dir, state)
            state = repo_review_state.load_state(output_dir, repo)
            repo_review_state.transition(state, status="round2-converged")
            repo_review_state.save_state(output_dir, state)
        seen_steps.append(name)
        return coordinator.StepResult(name=name, succeeded=True, duration_seconds=0.01)

    monkeypatch.setattr(coordinator, "run_subprocess", fake_run_subprocess)

    report = coordinator.coordinate_repo(
        repo=repo,
        output_dir=output_dir,
        workflows_steward_root=tmp_path,
        registry_path=tmp_path / "config" / "repo_review_registry.json",
        agents=["codex", "claude"],
        log_dir=output_dir / "logs" / "coordinator",
        round1_timeout=30,
        round2_timeout=30,
        skip_gate_enabled=False,
    )

    state = repo_review_state.load_state(output_dir, repo)
    assert seen_steps == ["round-1", "round-2", "body-writer"]
    assert report["round1"]["succeeded"] is True
    assert report["round2"]["succeeded"] is True
    assert report["body_writer"]["succeeded"] is True
    assert state.status == "round2-converged"


def test_run_orders_docs_drift_between_backlog_and_notify(tmp_path: Path, monkeypatch) -> None:
    registry_path = tmp_path / "config" / "repo_review_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "source_of_truth_docs.yml").write_text("repos: []\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    monkeypatch.setattr(
        coordinator,
        "load_registry",
        lambda _path: (
            tmp_path,
            [],
            [SimpleNamespace(repo="stranske/Example", status="active")],
            [],
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "coordinate_repo",
        lambda **_: {
            "repo": "stranske/Example",
            "round1": {"succeeded": True, "duration_seconds": 0.01},
            "round2": {"succeeded": True, "duration_seconds": 0.01},
            "skip_gate_fired": False,
        },
    )

    calls: list[tuple[str, int]] = []

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        calls.append((name, timeout))
        if name == "docs-drift-scan":
            Path(cmd[cmd.index("--out") + 1]).write_text("[]\n", encoding="utf-8")
        return coordinator.StepResult(name=name, succeeded=True, duration_seconds=0.01)

    monkeypatch.setattr(coordinator, "run_subprocess", fake_run_subprocess)

    args = SimpleNamespace(
        output_dir=str(output_dir),
        registry=str(registry_path),
        repos=[],
        agents=["codex", "claude"],
        skip_preflight=False,
        skip_gitnexus_preflight=False,
        round1_timeout=30,
        round2_timeout=30,
        disable_skip_gate=True,
        skip_auto_archive=True,
    )
    rc = coordinator.run(args)

    assert rc == 0
    call_names = [name for name, _timeout in calls]
    assert call_names == [
        "preflight",
        "final-evaluator",
        "backlog-scan",
        "docs-drift-scan",
        "notify",
    ]
    assert dict(calls)["docs-drift-scan"] == dict(calls)["backlog-scan"] == 300


def test_run_keeps_docs_drift_failure_non_fatal(tmp_path: Path, monkeypatch) -> None:
    registry_path = tmp_path / "config" / "repo_review_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "source_of_truth_docs.yml").write_text("repos: []\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    monkeypatch.setattr(
        coordinator,
        "load_registry",
        lambda _path: (
            tmp_path,
            [],
            [SimpleNamespace(repo="stranske/Example", status="active")],
            [],
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "coordinate_repo",
        lambda **_: {
            "repo": "stranske/Example",
            "round1": {"succeeded": True, "duration_seconds": 0.01},
            "round2": {"succeeded": True, "duration_seconds": 0.01},
            "skip_gate_fired": False,
        },
    )

    calls: list[str] = []

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        calls.append(name)
        if name == "docs-drift-scan":
            return coordinator.StepResult(
                name=name, succeeded=False, duration_seconds=0.01, notes="exit 1"
            )
        return coordinator.StepResult(name=name, succeeded=True, duration_seconds=0.01)

    monkeypatch.setattr(coordinator, "run_subprocess", fake_run_subprocess)

    args = SimpleNamespace(
        output_dir=str(output_dir),
        registry=str(registry_path),
        repos=[],
        agents=["codex", "claude"],
        skip_preflight=False,
        skip_gitnexus_preflight=False,
        round1_timeout=30,
        round2_timeout=30,
        disable_skip_gate=True,
        skip_auto_archive=True,
    )
    rc = coordinator.run(args)

    assert rc == 0
    assert calls[-1] == "notify"
