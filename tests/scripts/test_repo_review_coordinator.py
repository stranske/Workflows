import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import repo_review_coordinator as coordinator
from scripts import repo_review_state


def _write_docs_drift_output(cmd: list[str], *, scanned: int = 0, errors: int = 0) -> None:
    out = Path(cmd[cmd.index("--out") + 1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "generated_on": "2026-09-05T00:00:00Z",
                "total_docs_scanned": scanned,
                "total_drift_instances": 0,
                "total_accurate_instances": 0,
                "total_errors": errors,
                "by_repo": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )


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
        max_turns=3,
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
        max_turns=3,
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
    (tmp_path / "config" / "source_of_truth_docs.yml").write_text(
        """
repos:
  stranske/Example:
    local_path: Example
    docs:
      - path: README.md
        focus: overview
      - path: AGENTS.md
        focus: guardrails
""",
        encoding="utf-8",
    )
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
            "body_writer": {"succeeded": True, "duration_seconds": 0.01},
            "skip_gate_fired": False,
        },
    )

    calls: list[tuple[str, int]] = []

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        calls.append((name, timeout))
        if name == "docs-drift-scan":
            assert cmd[cmd.index("--timeout") + 1] == "600"
            assert cmd[cmd.index("--repos") + 1 :] == ["stranske/Example"]
            _write_docs_drift_output(cmd, scanned=2)
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
        max_turns=3,
        disable_skip_gate=True,
        skip_auto_archive=True,
    )
    rc = coordinator.run(args)

    assert rc == 0
    call_names = [name for name, _timeout in calls]
    assert call_names == [
        "preflight",
        "scorecard-scan",
        "final-evaluator",
        "backlog-scan",
        "docs-drift-scan",
        "notify",
    ]
    assert dict(calls)["docs-drift-scan"] == 2100
    assert dict(calls)["backlog-scan"] == 300
    assert dict(calls)["scorecard-scan"] == 300


def test_run_filters_explicit_repo_subset_to_active_registry_entries(
    tmp_path: Path, monkeypatch
) -> None:
    registry_path = tmp_path / "config" / "repo_review_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "source_of_truth_docs.yml").write_text(
        """
repos:
  stranske/Active:
    local_path: Active
    docs:
      - path: README.md
        focus: overview
  stranske/Paused:
    local_path: Paused
    docs:
      - path: README.md
        focus: overview
""",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    registry_repos = [
        SimpleNamespace(repo="stranske/Active", status="active"),
        SimpleNamespace(repo="stranske/Paused", status="paused"),
    ]
    monkeypatch.setattr(
        coordinator,
        "load_registry",
        lambda _path: (tmp_path, [], registry_repos, []),
    )
    coordinated: list[str] = []

    def fake_coordinate_repo(**kwargs):
        coordinated.append(kwargs["repo"])
        return {
            "repo": kwargs["repo"],
            "round1": {"succeeded": True, "duration_seconds": 0.01},
            "round2": {"succeeded": True, "duration_seconds": 0.01},
            "body_writer": {"succeeded": True, "duration_seconds": 0.01},
            "skip_gate_fired": False,
        }

    docs_scan_repos: list[str] = []

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        if name == "docs-drift-scan":
            docs_scan_repos.extend(cmd[cmd.index("--repos") + 1 :])
            _write_docs_drift_output(cmd, scanned=1)
        return coordinator.StepResult(name=name, succeeded=True, duration_seconds=0.01)

    monkeypatch.setattr(coordinator, "coordinate_repo", fake_coordinate_repo)
    monkeypatch.setattr(coordinator, "run_subprocess", fake_run_subprocess)
    args = SimpleNamespace(
        output_dir=str(output_dir),
        registry=str(registry_path),
        repos=["stranske/Active", "stranske/Paused"],
        agents=["codex", "claude"],
        skip_preflight=False,
        skip_gitnexus_preflight=False,
        round1_timeout=30,
        round2_timeout=30,
        max_turns=3,
        disable_skip_gate=True,
        skip_auto_archive=True,
    )

    assert coordinator.run(args) == 0
    assert coordinated == ["stranske/Active"]
    assert docs_scan_repos == ["stranske/Active"]
    assert (output_dir / "docs-drift-scan.json").is_file()


def test_run_orders_scorecard_before_final_evaluator(tmp_path: Path, monkeypatch) -> None:
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
            "body_writer": {"succeeded": True, "duration_seconds": 0.01},
            "skip_gate_fired": False,
        },
    )

    calls: list[str] = []

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        calls.append(name)
        if name == "scorecard-scan":
            Path(cmd[cmd.index("--out") + 1]).write_text(
                '{"schema":"repo-review-scorecard-scan/v1","by_repo":[]}\n', encoding="utf-8"
            )
        if name == "docs-drift-scan":
            _write_docs_drift_output(cmd)
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
        max_turns=3,
        disable_skip_gate=True,
        skip_auto_archive=True,
    )
    rc = coordinator.run(args)

    assert rc == 0
    assert calls.index("scorecard-scan") < calls.index("final-evaluator")


def test_run_keeps_scorecard_failure_non_fatal(tmp_path: Path, monkeypatch) -> None:
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
            "body_writer": {"succeeded": True, "duration_seconds": 0.01},
            "skip_gate_fired": False,
        },
    )

    calls: list[str] = []

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        calls.append(name)
        if name == "scorecard-scan":
            return coordinator.StepResult(
                name=name, succeeded=False, duration_seconds=0.01, notes="exit 1"
            )
        if name == "docs-drift-scan":
            _write_docs_drift_output(cmd)
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
        max_turns=3,
        disable_skip_gate=True,
        skip_auto_archive=True,
    )
    rc = coordinator.run(args)

    assert rc == 0
    assert calls[-1] == "notify"


def test_run_fails_closed_before_postprocessing_when_final_evaluator_fails(
    tmp_path: Path, monkeypatch
) -> None:
    registry_path = tmp_path / "config" / "repo_review_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    for name in coordinator.AGGREGATE_OUTPUT_NAMES:
        (output_dir / name).write_text("stale\n", encoding="utf-8")

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
            "body_writer": {"succeeded": True, "duration_seconds": 0.01},
            "skip_gate_fired": False,
        },
    )
    calls: list[str] = []

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        calls.append(name)
        return coordinator.StepResult(
            name=name,
            succeeded=name != "final-evaluator",
            duration_seconds=0.01,
            notes="exit 1" if name == "final-evaluator" else "",
        )

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
        max_turns=3,
        disable_skip_gate=True,
        skip_auto_archive=True,
    )

    assert coordinator.run(args) == 1
    assert calls[-1] == "final-evaluator"
    assert "backlog-scan" not in calls
    assert "notify" not in calls
    failure = json.loads((output_dir / "repo-review-run-failure.json").read_text())
    assert failure["repo"] == "cycle"
    assert failure["phase"] == "final-evaluator"
    assert all(not (output_dir / name).exists() for name in coordinator.AGGREGATE_OUTPUT_NAMES)


def test_run_fails_closed_before_notify_when_docs_drift_fails(tmp_path: Path, monkeypatch) -> None:
    registry_path = tmp_path / "config" / "repo_review_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "source_of_truth_docs.yml").write_text("repos: []\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    for name in coordinator.AGGREGATE_OUTPUT_NAMES:
        (output_dir / name).write_text("stale\n", encoding="utf-8")

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
            "body_writer": {"succeeded": True, "duration_seconds": 0.01},
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
        max_turns=3,
        disable_skip_gate=True,
        skip_auto_archive=True,
    )
    rc = coordinator.run(args)

    assert rc == 1
    assert calls[-1] == "docs-drift-scan"
    assert "notify" not in calls
    failure = json.loads((output_dir / "repo-review-run-failure.json").read_text())
    assert failure["repo"] == "cycle"
    assert failure["phase"] == "docs-drift-scan"
    assert len(failure["quarantined_aggregate_outputs"]) == len(coordinator.AGGREGATE_OUTPUT_NAMES)
    assert all(not (output_dir / name).exists() for name in coordinator.AGGREGATE_OUTPUT_NAMES)


def test_docs_drift_timeout_scales_with_selected_document_workload(tmp_path: Path) -> None:
    config = tmp_path / "source_of_truth_docs.yml"
    config.write_text(
        """
repos:
  stranske/A:
    docs:
      - path: README.md
      - path: AGENTS.md
  stranske/B:
    docs:
      - path: README.md
""",
        encoding="utf-8",
    )

    assert coordinator.configured_docs_drift_doc_count(config, ["stranske/A"]) == 2
    assert coordinator.docs_drift_subprocess_timeout(config, ["stranske/A"]) == 2100
    assert coordinator.docs_drift_subprocess_timeout(config, ["stranske/B"]) == 1800

    automation_config = tmp_path / "automation.toml"
    automation_config.write_text(
        """
[automation.timeouts]
docs_drift_per_doc_seconds = 100
docs_drift_minimum_seconds = 50
docs_drift_buffer_seconds = 25
""",
        encoding="utf-8",
    )
    assert (
        coordinator.docs_drift_subprocess_timeout(
            config,
            ["stranske/A"],
            automation_config_path=automation_config,
        )
        == 225
    )


def test_validate_docs_drift_output_rejects_errors_and_incomplete_coverage(
    tmp_path: Path,
) -> None:
    path = tmp_path / "scan.json"
    path.write_text(
        json.dumps(
            {
                "generated_on": "2026-09-05T00:00:00Z",
                "total_docs_scanned": 1,
                "total_errors": 1,
            }
        ),
        encoding="utf-8",
    )

    valid, notes = coordinator.validate_docs_drift_output(path, expected_doc_count=2)
    assert valid is False
    assert "incomplete docs coverage" in notes

    path.write_text(
        json.dumps(
            {
                "generated_on": "2026-09-05T00:00:00Z",
                "total_docs_scanned": 2,
                "total_errors": 1,
            }
        ),
        encoding="utf-8",
    )
    valid, notes = coordinator.validate_docs_drift_output(path, expected_doc_count=2)
    assert valid is False
    assert "recorded 1 error" in notes


def test_round2_subprocess_timeout_covers_multiturn_budget() -> None:
    """The subprocess wrapper timeout must cover the full multi-turn budget.

    Defaults: round2_timeout=2700, max_turns=3, n_agents=2.
    Worst-case runtime = 3 * 2 * 2700 = 16200s.
    """
    result = coordinator.round2_subprocess_timeout(2700, 3, 2)
    assert result >= 3 * 2 * 2700


def test_round2_subprocess_timeout_includes_provider_capacity_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPO_REVIEW_CAPACITY_WAIT_MAX_SECONDS", "123")

    result = coordinator.round2_subprocess_timeout(30, 3, 2, buffer=10)

    assert result == (3 * 2 * 30) + (3 * 123) + 10


def test_coordinate_repo_parent_timeouts_cover_capacity_deferral(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, int] = {}
    monkeypatch.setenv("REPO_REVIEW_CAPACITY_WAIT_MAX_SECONDS", "123")

    def fake_run_subprocess(_cmd, *, cwd, log_path, name, timeout):
        observed[name] = timeout
        return coordinator.StepResult(name=name, succeeded=True, duration_seconds=0.01)

    monkeypatch.setattr(coordinator, "run_subprocess", fake_run_subprocess)
    coordinator.coordinate_repo(
        repo="stranske/Example",
        output_dir=tmp_path / "review",
        workflows_steward_root=tmp_path,
        registry_path=tmp_path / "config" / "repo_review_registry.json",
        agents=["codex", "claude"],
        log_dir=tmp_path / "review" / "logs" / "coordinator",
        round1_timeout=30,
        round2_timeout=40,
        max_turns=3,
        skip_gate_enabled=False,
        repair_attempts=2,
    )

    assert observed["round-1"] == (2 * 30) + 123 + 1500
    assert observed["round-2"] == (3 * 2 * 40) + (3 * 123) + 1500
    assert observed["body-writer"] == (2 * 40) + 123 + 600


def test_configured_repair_attempts_reads_toml_and_rejects_negative(tmp_path: Path) -> None:
    config = tmp_path / "repo_review_automation.toml"
    config.write_text("[automation.timeouts]\nrepair_attempts_per_phase = 4\n", encoding="utf-8")
    assert coordinator.configured_repair_attempts(config) == 4
    with pytest.raises(argparse.ArgumentTypeError, match="greater than or equal to zero"):
        coordinator.nonnegative_int("-1")


def test_repair_io_failure_returns_controlled_failed_step(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        coordinator,
        "run_subprocess",
        lambda *_args, **_kwargs: coordinator.StepResult(
            name="body-writer", succeeded=False, duration_seconds=0.1, notes="exit 1"
        ),
    )

    def fail_repair(**_kwargs):
        raise OSError("repair volume unavailable")

    monkeypatch.setattr(coordinator, "prepare_phase_retry", fail_repair)
    result, attempts, repairs = coordinator.run_subprocess_with_repairs(
        ["false"],
        cwd=tmp_path,
        log_path=tmp_path / "body-writer.log",
        name="body-writer",
        timeout=30,
        repo="stranske/Example",
        output_dir=tmp_path / "out",
        repair_attempts=2,
    )

    assert result.succeeded is False
    assert "repair preparation failed" in result.notes
    assert len(attempts) == 1
    assert repairs[0]["succeeded"] is False


def test_body_writer_head_drift_returns_control_for_full_repo_restart(
    tmp_path: Path, monkeypatch
) -> None:
    calls = 0

    def fail_with_head_drift(_cmd, *, cwd, log_path, name, timeout):
        nonlocal calls
        calls += 1
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "sync check failed: HEAD (abc) does not match origin/main\n",
            encoding="utf-8",
        )
        return coordinator.StepResult(
            name=name, succeeded=False, duration_seconds=0.01, notes="exit 1"
        )

    monkeypatch.setattr(coordinator, "run_subprocess", fail_with_head_drift)
    result, attempts, repairs = coordinator.run_subprocess_with_repairs(
        ["body-writer"],
        cwd=tmp_path,
        log_path=tmp_path / "body-writer.log",
        name="body-writer",
        timeout=30,
        repo="stranske/Example",
        output_dir=tmp_path / "out",
        repair_attempts=2,
        stop_retry_when=coordinator.log_indicates_head_drift,
    )

    assert result.succeeded is False
    assert calls == 1
    assert len(attempts) == 1
    assert repairs == []


def test_coordinate_repo_restarts_round1_after_late_head_drift(tmp_path: Path, monkeypatch) -> None:
    repo = "stranske/Example"
    safe = "stranske__Example"
    output_dir = tmp_path / "review"
    log_dir = output_dir / "logs" / "coordinator"
    calls = 0

    def fake_coordinate_repo(**_kwargs):
        nonlocal calls
        calls += 1
        phase_log = log_dir / safe / "body-writer.log"
        phase_log.parent.mkdir(parents=True, exist_ok=True)
        round1 = output_dir / "round1" / "codex" / safe / "findings.json"
        round1.parent.mkdir(parents=True, exist_ok=True)
        round1.write_text(f'{{"attempt": {calls}}}\n', encoding="utf-8")
        round2 = output_dir / "round2" / safe / "converged.json"
        round2.parent.mkdir(parents=True, exist_ok=True)
        round2.write_text(f'{{"attempt": {calls}}}\n', encoding="utf-8")
        if calls == 1:
            phase_log.write_text(
                "HEAD (old) does not match origin/main\n",
                encoding="utf-8",
            )
            return {
                "repo": repo,
                "round1": {"succeeded": True},
                "round2": {"succeeded": True},
                "body_writer": {"succeeded": False},
                "skip_gate_fired": False,
            }
        phase_log.write_text("complete\n", encoding="utf-8")
        return {
            "repo": repo,
            "round1": {"succeeded": True},
            "round2": {"succeeded": True},
            "body_writer": {"succeeded": True},
            "skip_gate_fired": False,
        }

    monkeypatch.setattr(coordinator, "coordinate_repo", fake_coordinate_repo)
    report = coordinator.coordinate_repo_with_restarts(
        repo=repo,
        output_dir=output_dir,
        workflows_steward_root=tmp_path,
        registry_path=tmp_path / "config" / "repo_review_registry.json",
        agents=["codex", "claude"],
        log_dir=log_dir,
        round1_timeout=30,
        round2_timeout=30,
        max_turns=1,
        skip_gate_enabled=False,
        repair_attempts=2,
    )

    assert calls == 2
    assert report["body_writer"]["succeeded"] is True
    assert len(report["head_drift_restarts"]) == 1
    repair_dir = Path(report["head_drift_restarts"][0]["repair_dir"])
    assert (repair_dir / "round1" / "codex" / "findings.json").is_file()
    assert (repair_dir / "round2" / "converged.json").is_file()
    assert (
        json.loads((output_dir / "round1" / "codex" / safe / "findings.json").read_text())[
            "attempt"
        ]
        == 2
    )


def test_run_returns_nonzero_after_body_writer_repairs_exhausted(
    tmp_path: Path, monkeypatch
) -> None:
    registry_path = tmp_path / "config" / "repo_review_registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    for name in coordinator.AGGREGATE_OUTPUT_NAMES:
        (output_dir / name).write_text("stale\n", encoding="utf-8")
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
    calls: list[str] = []

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        calls.append(name)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"{name}\n", encoding="utf-8")
        return coordinator.StepResult(
            name=name,
            succeeded=name != "body-writer",
            duration_seconds=0.01,
            notes="exit 1" if name == "body-writer" else "",
        )

    monkeypatch.setattr(coordinator, "run_subprocess", fake_run_subprocess)
    args = SimpleNamespace(
        output_dir=str(output_dir),
        registry=str(registry_path),
        repos=[],
        agents=["codex", "claude"],
        skip_preflight=False,
        skip_gitnexus_preflight=True,
        round1_timeout=30,
        round2_timeout=30,
        max_turns=1,
        repair_attempts=2,
        docs_drift_timeout=30,
        disable_skip_gate=True,
        skip_auto_archive=True,
    )

    rc = coordinator.run(args)

    assert rc == 1
    assert calls.count("body-writer") == 3
    assert "final-evaluator" not in calls
    repairs = list((output_dir / "repairs" / "stranske__Example").glob("*/repair.json"))
    assert len(repairs) == 2
    failure = json.loads((output_dir / "repo-review-run-failure.json").read_text())
    assert failure["repo"] == "stranske/Example"
    assert failure["phase"] == "body-writer"
    assert len(failure["quarantined_aggregate_outputs"]) == len(coordinator.AGGREGATE_OUTPUT_NAMES)
    assert all(not (output_dir / name).exists() for name in coordinator.AGGREGATE_OUTPUT_NAMES)
    assert all(
        (output_dir / path).read_text(encoding="utf-8") == "stale\n"
        for path in failure["quarantined_aggregate_outputs"]
    )


def test_run_stops_before_next_repo_when_repairs_are_exhausted(tmp_path: Path, monkeypatch) -> None:
    """A required-phase failure must block later repos and aggregate outputs."""
    registry_path = tmp_path / "config" / "repo_review_registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "out"
    repos = ["stranske/First", "stranske/Second"]
    monkeypatch.setattr(
        coordinator,
        "load_registry",
        lambda _path: (
            tmp_path,
            [],
            [SimpleNamespace(repo=repo, status="active") for repo in repos],
            [],
        ),
    )
    coordinated: list[str] = []

    def fake_coordinate_repo(**kwargs):
        """Record the only repo the fail-closed loop may execute."""
        coordinated.append(kwargs["repo"])
        return {
            "repo": kwargs["repo"],
            "round1": {"succeeded": True},
            "round2": {"succeeded": True},
            "body_writer": {"succeeded": False},
            "skip_gate_fired": False,
        }

    monkeypatch.setattr(coordinator, "coordinate_repo", fake_coordinate_repo)
    monkeypatch.setattr(
        coordinator,
        "run_subprocess",
        lambda _cmd, **kwargs: coordinator.StepResult(
            name=kwargs["name"], succeeded=True, duration_seconds=0.01
        ),
    )
    args = SimpleNamespace(
        output_dir=str(output_dir),
        registry=str(registry_path),
        repos=[],
        agents=["codex", "claude"],
        skip_preflight=False,
        skip_gitnexus_preflight=True,
        round1_timeout=30,
        round2_timeout=30,
        max_turns=1,
        repair_attempts=2,
        docs_drift_timeout=30,
        disable_skip_gate=True,
        skip_auto_archive=True,
    )

    assert coordinator.run(args) == 1
    assert coordinated == ["stranske/First"]


def test_coordinate_repo_repairs_failed_round1_then_retries(tmp_path: Path, monkeypatch) -> None:
    repo = "stranske/Example"
    output_dir = tmp_path / "review"
    calls: list[str] = []

    def fake_run_subprocess(cmd, *, cwd, log_path, name, timeout):
        calls.append(name)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"{name} attempt\n", encoding="utf-8")
        if name == "round-1" and calls.count("round-1") == 1:
            return coordinator.StepResult(
                name=name, succeeded=False, duration_seconds=0.01, notes="exit 1"
            )
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
        max_turns=3,
        skip_gate_enabled=False,
        repair_attempts=2,
    )

    assert calls == ["round-1", "round-1", "round-2", "body-writer"]
    assert report["round1"]["succeeded"] is True
    assert len(report["round1"]["attempts"]) == 2
    assert len(report["round1"]["repairs"]) == 1
    assert list((output_dir / "repairs" / "stranske__Example").glob("*/repair.json"))


def test_prepare_round2_retry_quarantines_poisoned_turn_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "review"
    repo = "stranske/Example"
    repo_dir = output_dir / "round2" / "stranske__Example"
    turn_file = repo_dir / "turn-1" / "codex.json"
    turn_file.parent.mkdir(parents=True)
    turn_file.write_text("{malformed", encoding="utf-8")
    (repo_dir / "converged.json").write_text("{}\n", encoding="utf-8")
    failed_log = output_dir / "logs" / "coordinator" / "round2-runner.log"
    failed_log.parent.mkdir(parents=True)
    failed_log.write_text("schema failure\n", encoding="utf-8")

    repair = coordinator.prepare_phase_retry(
        phase="round-2",
        repo=repo,
        output_dir=output_dir,
        failed_log=failed_log,
        repair_number=1,
    )

    assert not turn_file.exists()
    assert not (repo_dir / "converged.json").exists()
    assert any("turn-1" in path for path in repair["quarantined"])


def test_prepare_body_retry_carries_validator_feedback_into_next_attempt(tmp_path: Path) -> None:
    """The next body attempt receives the exact prior deterministic failure."""
    output_dir = tmp_path / "review"
    repo = "stranske/Example"
    repo_dir = output_dir / "round2" / "stranske__Example"
    repo_dir.mkdir(parents=True)
    converged = repo_dir / "converged.json"
    baseline = repo_dir / "converged.pre-body-writer.json"
    converged.write_text('{"body":"invalid"}\n', encoding="utf-8")
    baseline.write_text('{"body":""}\n', encoding="utf-8")
    failed_log = output_dir / "logs" / "coordinator" / "body-writer.log"
    failed_log.parent.mkdir(parents=True)
    failed_log.write_text(
        "candidate #1: Tasks reference 1 distinct repository paths\n",
        encoding="utf-8",
    )

    coordinator.prepare_phase_retry(
        phase="body-writer",
        repo=repo,
        output_dir=output_dir,
        failed_log=failed_log,
        repair_number=1,
    )

    assert converged.read_text(encoding="utf-8") == baseline.read_text(encoding="utf-8")
    feedback = (repo_dir / "body-writer-repair-feedback.txt").read_text(encoding="utf-8")
    assert "schema-only validation is insufficient" in feedback
    assert "candidate #1: Tasks reference 1 distinct repository paths" in feedback


def test_prepare_body_retry_replaces_invalid_utf8_diagnostics(tmp_path: Path) -> None:
    """Corrupt log bytes become replacement text instead of an I/O failure."""
    output_dir = tmp_path / "review"
    repo = "stranske/Example"
    repo_dir = output_dir / "round2" / "stranske__Example"
    repo_dir.mkdir(parents=True)
    (repo_dir / "converged.json").write_text("{}\n", encoding="utf-8")
    (repo_dir / "converged.pre-body-writer.json").write_text("{}\n", encoding="utf-8")
    failed_log = output_dir / "logs" / "coordinator" / "body-writer.log"
    failed_log.parent.mkdir(parents=True)
    failed_log.write_bytes(b"validator failure: \xff\xfe\n")

    coordinator.prepare_phase_retry(
        phase="body-writer",
        repo=repo,
        output_dir=output_dir,
        failed_log=failed_log,
        repair_number=1,
    )

    feedback = (repo_dir / "body-writer-repair-feedback.txt").read_text(encoding="utf-8")
    assert "validator failure: \ufffd\ufffd" in feedback
