from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import subprocess
import types
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
import scripts.runner_lib.core as runner_core
from scripts.runner_lib import (
    UNPRODUCTIVE_COMPLETION_COOLDOWN_SECONDS,
    UNPRODUCTIVE_COMPLETION_RETRY_LIMIT,
    CapabilityEffectEvidence,
    RunnerResult,
    assemble_prompt,
    normalize_capability_effect_evidence,
    parse_runner_output,
    record_completion,
    should_dispatch,
)
from scripts.runner_lib.core import PrCommentRunnerStorage, materialize_reference_packs


class MemoryRunnerStorage:
    def __init__(self) -> None:
        self.records: dict[tuple[int, str], dict[str, Any]] = {}
        self.writes: list[dict[str, Any]] = []

    def read_record(self, pr_number: int, provider: str) -> dict[str, Any] | None:
        record = self.records.get((pr_number, provider))
        return dict(record) if record else None

    def write_record(self, pr_number: int, provider: str, record: dict[str, Any]) -> None:
        self.records[(pr_number, provider)] = dict(record)
        self.writes.append(dict(record))


def _task_snapshot(completed: int, *, total: int = 2, fingerprint: str = "a" * 64):
    return {
        "schema": 1,
        "total": total,
        "completed": completed,
        "fingerprint": fingerprint,
    }


def test_completed_task_delta_marks_unchanged_head_productive() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(
        42,
        "aaa",
        "codex",
        storage=storage,
        task_progress_before=_task_snapshot(0),
    )

    completed = record_completion(
        42,
        "aaa",
        "codex",
        {"success": True},
        storage=storage,
        observed_head_sha="aaa",
        task_progress_after=_task_snapshot(1),
    )

    assert completed["productive"] is True
    assert completed["tasks_completed_delta"] == 1
    assert completed["task_progress_reason"] == "measured"
    assert should_dispatch(42, "aaa", "codex", storage=storage).reason == "duplicate-completed"


def test_unchanged_head_without_task_delta_keeps_bounded_retry() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(
        42,
        "aaa",
        "codex",
        storage=storage,
        task_progress_before=_task_snapshot(1),
    )
    completed = record_completion(
        42,
        "aaa",
        "codex",
        {"success": True},
        storage=storage,
        observed_head_sha="aaa",
        task_progress_after=_task_snapshot(1),
    )

    assert completed["productive"] is False
    assert completed["tasks_completed_delta"] == 0
    assert should_dispatch(42, "aaa", "codex", storage=storage).reason == (
        "retry-unproductive-completion"
    )


@pytest.mark.parametrize(
    ("before", "after", "reason"),
    [
        (None, _task_snapshot(1), "baseline-missing"),
        (_task_snapshot(0), "not-json", "after-missing"),
        (_task_snapshot(0), _task_snapshot(1, fingerprint="b" * 64), "task-set-changed"),
    ],
)
def test_unknown_or_changed_task_sets_never_manufacture_progress(before, after, reason) -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage, task_progress_before=before)
    completed = record_completion(
        42,
        "aaa",
        "codex",
        {"success": True},
        storage=storage,
        observed_head_sha="aaa",
        task_progress_after=after,
    )

    assert "productive" not in completed
    assert completed["task_progress_reason"] == reason


def test_changed_head_is_productive_without_task_measurement() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    completed = record_completion(
        42,
        "aaa",
        "codex",
        {"success": True},
        storage=storage,
        observed_head_sha="bbb",
        task_progress_after="not-json",
    )

    assert completed["productive"] is True
    assert completed["observed_head_sha"] == "bbb"
    assert completed["task_progress_reason"] == "head-changed"


def test_completion_replay_preserves_first_task_observation() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(
        42,
        "aaa",
        "codex",
        storage=storage,
        task_progress_before=_task_snapshot(0),
    )
    first = record_completion(
        42,
        "aaa",
        "codex",
        {"success": True},
        storage=storage,
        observed_head_sha="aaa",
        task_progress_after=_task_snapshot(1),
    )
    replay = record_completion(
        42,
        "aaa",
        "codex",
        {"success": True},
        storage=storage,
        observed_head_sha="aaa",
        task_progress_after=_task_snapshot(2),
    )

    assert replay["tasks_completed_delta"] == first["tasks_completed_delta"] == 1
    assert replay["tasks_completed_after"] == first["tasks_completed_after"] == 1


def test_completion_replay_preserves_unmeasured_task_observation() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(
        42,
        "aaa",
        "codex",
        storage=storage,
        task_progress_before=_task_snapshot(0),
    )
    first = record_completion(
        42,
        "aaa",
        "codex",
        {"success": True},
        storage=storage,
        observed_head_sha="aaa",
        task_progress_after="not-json",
    )
    replay = record_completion(
        42,
        "aaa",
        "codex",
        {"success": True},
        storage=storage,
        observed_head_sha="aaa",
        task_progress_after=_task_snapshot(1),
    )

    assert "productive" not in first
    assert "productive" not in replay
    assert replay["task_progress_reason"] == first["task_progress_reason"] == "after-missing"
    assert "tasks_completed_after" not in replay


def test_each_retry_reservation_replaces_task_baseline() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(
        42,
        "aaa",
        "codex",
        storage=storage,
        task_progress_before=_task_snapshot(0),
    )
    record_completion(
        42,
        "aaa",
        "codex",
        {"success": True},
        storage=storage,
        observed_head_sha="aaa",
        task_progress_after=_task_snapshot(0),
    )
    should_dispatch(
        42,
        "aaa",
        "codex",
        storage=storage,
        task_progress_before=_task_snapshot(1),
    )

    assert storage.records[(42, "codex")]["tasks_completed_before"] == 1


def _signed_challenge_environment(monkeypatch):
    fingerprint = "a" * 64
    nonce = "b" * 64
    payload = "\n".join(
        [
            "keepalive-authority-claim:v1",
            "repository=owner/repo",
            "pr=42",
            f"fingerprint={fingerprint}",
            f"nonce={nonce}",
            "sweep_run_id=90",
            "sweep_run_attempt=1",
        ]
    )
    signature = hmac.new(b"test-key", payload.encode(), hashlib.sha256).hexdigest()
    for key, value in {
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "100",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_ACTOR": "github-actions[bot]",
        "AUTHORITY_CHALLENGE_FINGERPRINT": fingerprint,
        "AUTHORITY_CHALLENGE_SIGNING_KEY": "test-key",
        "AUTHORITY_CHALLENGE_CLAIM": json.dumps(
            {
                "nonce": nonce,
                "sweep_run_id": "90",
                "sweep_run_attempt": "1",
                "signature": signature,
            }
        ),
    }.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("prior_status", [None, "completed", "pending"])
def test_signed_challenge_reserves_own_attempt_and_records_completion(monkeypatch, prior_status):
    _signed_challenge_environment(monkeypatch)
    monkeypatch.setattr(
        runner_core,
        "_authority_challenge_command",
        lambda command, *_: {"prepared": True} if command == "prepare" else {"granted": True},
    )
    primary = MemoryRunnerStorage()
    fallback = MemoryRunnerStorage()
    storage = runner_core.FallbackRunnerStorage(primary, fallback)
    if prior_status:
        primary.records[(42, "codex")] = {
            "status": prior_status,
            "head_sha": "aaa",
            "workflow_attempt_id": "old:1:1",
        }
        if prior_status == "pending":
            primary.records[(42, "codex")]["started_at"] = "2000-01-01T00:00:00Z"
    decision = should_dispatch(42, "aaa", "codex", storage=storage, authority_challenge=True)
    assert decision.should_dispatch
    assert decision.reason == "due-authority-challenge"
    assert primary.records[(42, "codex")]["status"] == "pending"
    assert primary.records[(42, "codex")]["workflow_attempt_id"] == "owner/repo:100:2"
    completed = record_completion(42, "aaa", "codex", {"success": True}, storage=storage)
    assert completed["status"] == "completed"
    assert completed.get("completion_recorded") is not False
    assert primary.records[(42, "codex")] == completed
    assert not fallback.writes


@pytest.mark.parametrize("location", ["primary", "fallback"])
@pytest.mark.parametrize("head_sha", ["aaa", "bbb"])
@pytest.mark.parametrize("started_at", [None, "not-a-timestamp", "2999-01-01T00:00:00Z"])
def test_signed_challenge_preserves_live_pending_without_preparing(
    monkeypatch, location, head_sha, started_at
):
    _signed_challenge_environment(monkeypatch)
    commands = []
    monkeypatch.setattr(
        runner_core,
        "_authority_challenge_command",
        lambda command, *_: commands.append(command),
    )
    primary, fallback = MemoryRunnerStorage(), MemoryRunnerStorage()
    owner = primary if location == "primary" else fallback
    record = {
        "status": "pending",
        "head_sha": head_sha,
        "workflow_attempt_id": "other:1:1",
    }
    if started_at is not None:
        record["started_at"] = started_at
    owner.records[(42, "codex")] = dict(record)

    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(primary, fallback),
        authority_challenge=True,
    )

    assert not decision.should_dispatch
    assert decision.reason == "duplicate-pending"
    assert owner.records[(42, "codex")] == record
    assert not primary.writes and not fallback.writes
    assert commands == []


def test_signed_challenge_preserves_pending_that_arrives_during_prepare(monkeypatch):
    _signed_challenge_environment(monkeypatch)
    commands = []
    primary, fallback = MemoryRunnerStorage(), MemoryRunnerStorage()
    arriving = {
        "status": "pending",
        "head_sha": "bbb",
        "started_at": "2999-01-01T00:00:00Z",
        "workflow_attempt_id": "other:1:1",
    }

    def authority(command, *_):
        commands.append(command)
        if command == "prepare":
            primary.records[(42, "codex")] = dict(arriving)
            return {"prepared": True}
        return {"released": True}

    monkeypatch.setattr(runner_core, "_authority_challenge_command", authority)
    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(primary, fallback),
        authority_challenge=True,
    )

    assert not decision.should_dispatch
    assert decision.reason == "duplicate-pending"
    assert primary.records[(42, "codex")] == arriving
    assert not primary.writes and not fallback.writes
    assert commands == ["prepare", "release"]


@pytest.mark.parametrize("release_result", [None, {}, {"released": False}])
def test_signed_challenge_fails_closed_when_pending_release_is_uncertain(
    monkeypatch, release_result
):
    _signed_challenge_environment(monkeypatch)
    commands = []
    primary, fallback = MemoryRunnerStorage(), MemoryRunnerStorage()

    def authority(command, *_):
        commands.append(command)
        if command == "prepare":
            primary.records[(42, "codex")] = {
                "status": "pending",
                "head_sha": "bbb",
                "started_at": "2999-01-01T00:00:00Z",
            }
            return {"prepared": True}
        return release_result

    monkeypatch.setattr(runner_core, "_authority_challenge_command", authority)
    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(primary, fallback),
        authority_challenge=True,
    )

    assert not decision.should_dispatch
    assert decision.reason == "authoritative-storage-unavailable"
    assert not primary.writes and not fallback.writes
    assert commands == ["prepare", "release"]


def test_signed_challenge_fails_closed_when_post_prepare_read_is_unavailable(monkeypatch):
    _signed_challenge_environment(monkeypatch)
    commands = []

    class FailsSecondRead(MemoryRunnerStorage):
        reads = 0

        def read_record(self, pr_number, provider):
            self.reads += 1
            if self.reads == 2:
                raise RuntimeError("primary read unavailable")
            return super().read_record(pr_number, provider)

    def authority(command, *_):
        commands.append(command)
        return {"prepared": True}

    monkeypatch.setattr(runner_core, "_authority_challenge_command", authority)
    primary, fallback = FailsSecondRead(), MemoryRunnerStorage()
    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(primary, fallback),
        authority_challenge=True,
    )

    assert not decision.should_dispatch
    assert decision.reason == "authoritative-storage-unavailable"
    assert not primary.writes and not fallback.writes
    assert commands == ["prepare"]


def test_signed_challenge_prepares_then_reserves_then_consumes(monkeypatch):
    _signed_challenge_environment(monkeypatch)
    events = []

    class OrderedStorage(MemoryRunnerStorage):
        def write_record(self, pr_number, provider, record):
            events.append("reserve")
            super().write_record(pr_number, provider, record)

    def authority(command, *_):
        events.append(command)
        return {"prepared": True} if command == "prepare" else {"granted": True}

    monkeypatch.setattr(runner_core, "_authority_challenge_command", authority)
    primary = OrderedStorage()
    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(primary, MemoryRunnerStorage()),
        authority_challenge=True,
    )
    assert decision.should_dispatch
    assert events == ["prepare", "reserve", "finalize"]


def test_signed_challenge_denies_when_reservation_changes_during_finalize(monkeypatch):
    _signed_challenge_environment(monkeypatch)
    events = []

    class OrderedStorage(MemoryRunnerStorage):
        def write_record(self, pr_number, provider, record):
            events.append("reserve")
            super().write_record(pr_number, provider, record)

    primary = OrderedStorage()

    def authority(command, *_):
        events.append(command)
        if command == "finalize":
            primary.records.pop((42, "codex"), None)
            return {"granted": True}
        return {"prepared": True}

    monkeypatch.setattr(runner_core, "_authority_challenge_command", authority)
    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(primary, MemoryRunnerStorage()),
        authority_challenge=True,
    )
    assert not decision.should_dispatch
    assert decision.reason == "authority-reservation-changed"
    assert events == ["prepare", "reserve", "finalize"]


def test_challenge_cannot_reserve_without_authoritative_consumption(monkeypatch):
    _signed_challenge_environment(monkeypatch)
    monkeypatch.setattr(runner_core, "_authority_challenge_command", lambda *args: None)
    primary, fallback = MemoryRunnerStorage(), MemoryRunnerStorage()
    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(primary, fallback),
        authority_challenge=True,
    )
    assert not decision.should_dispatch
    assert decision.reason == "invalid-or-consumed-authority-challenge"
    assert not primary.writes and not fallback.writes


@pytest.mark.parametrize(
    "key,value",
    [
        ("GITHUB_ACTOR", "untrusted"),
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_RUN_ATTEMPT", ""),
    ],
)
def test_challenge_consumption_rejects_untrusted_workflow_context(monkeypatch, key, value):
    _signed_challenge_environment(monkeypatch)
    monkeypatch.setenv(key, value)
    assert not runner_core._authority_challenge_command("prepare", 42, "a" * 40, "codex")


@pytest.mark.parametrize(
    "returncode,stdout,expected,diagnostic",
    [
        (0, b'{"prepared":true}', {"prepared": True}, ""),
        (0, b'{"prepared":false}', {"prepared": False}, ""),
        (7, b"", None, "exited 7"),
        (0, b"not-json", None, "invalid JSON"),
    ],
)
def test_authority_bridge_hands_v2_claim_to_node_and_fails_closed(
    monkeypatch, capsys, returncode, stdout, expected, diagnostic
):
    _signed_challenge_environment(monkeypatch)
    captured = {}

    def fake_run(args, **kwargs):
        captured.update(args=args, **kwargs)
        return subprocess.CompletedProcess(args, returncode, stdout, b"sensitive helper detail")

    monkeypatch.setattr(runner_core.subprocess, "run", fake_run)
    assert runner_core._authority_challenge_command("prepare", 42, "a" * 40, "codex") == expected
    assert captured["args"] == ["node", ".github/scripts/keepalive_authority_state.js", "prepare"]
    assert captured["env"]["AUTHORITY_CHALLENGE_CLAIM"]
    assert captured["env"]["AUTHORITY_PR_NUMBER"] == "42"
    assert captured["env"]["AUTHORITY_HEAD_SHA"] == "a" * 40
    assert captured["env"]["AUTHORITY_PROVIDER"] == "codex"
    assert diagnostic in capsys.readouterr().err


@pytest.mark.parametrize("operation", ["read_record", "write_record"])
def test_signed_challenge_storage_failure_never_dispatches(monkeypatch, operation):
    _signed_challenge_environment(monkeypatch)
    commands = []

    def authority(command, *_):
        commands.append(command)
        return {"prepared": True} if command == "prepare" else {"released": True}

    monkeypatch.setattr(runner_core, "_authority_challenge_command", authority)
    primary, fallback = MemoryRunnerStorage(), MemoryRunnerStorage()

    def fail(*args):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(primary, operation, fail)
    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(primary, fallback),
        authority_challenge=True,
    )
    assert not decision.should_dispatch
    assert decision.reason == "authoritative-storage-unavailable"
    assert not primary.writes and not fallback.writes
    if operation == "write_record":
        assert commands == ["prepare", "release"]


@pytest.mark.parametrize("release_result", [None, {}, {"released": False}])
def test_signed_challenge_write_failure_reports_uncertain_release(monkeypatch, release_result):
    _signed_challenge_environment(monkeypatch)
    commands = []

    def authority(command, *_):
        commands.append(command)
        return {"prepared": True} if command == "prepare" else release_result

    primary, fallback = MemoryRunnerStorage(), MemoryRunnerStorage()
    monkeypatch.setattr(runner_core, "_authority_challenge_command", authority)
    monkeypatch.setattr(
        primary,
        "write_record",
        lambda *_: (_ for _ in ()).throw(RuntimeError("write failed before persistence")),
    )

    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(primary, fallback),
        authority_challenge=True,
    )

    assert not decision.should_dispatch
    assert decision.reason == "authoritative-storage-unavailable"
    assert commands == ["prepare", "release"]
    assert not primary.records and not fallback.writes


def test_signed_challenge_uncertain_reservation_write_does_not_release(monkeypatch):
    _signed_challenge_environment(monkeypatch)
    commands = []

    def authority(command, *_):
        commands.append(command)
        return {"prepared": True}

    class UncertainStorage(MemoryRunnerStorage):
        reads = 0

        def read_record(self, pr_number, provider):
            self.reads += 1
            if self.reads == 1:
                return None
            raise RuntimeError("primary readback unavailable")

        def write_record(self, pr_number, provider, record):
            raise RuntimeError("primary write outcome unknown")

    monkeypatch.setattr(runner_core, "_authority_challenge_command", authority)
    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(UncertainStorage(), MemoryRunnerStorage()),
        authority_challenge=True,
    )
    assert not decision.should_dispatch
    assert decision.reason == "authoritative-storage-unavailable"
    assert commands == ["prepare"]


def test_signed_challenge_recovers_persisted_reservation_after_write_error(monkeypatch):
    _signed_challenge_environment(monkeypatch)
    commands = []

    def authority(command, *_):
        commands.append(command)
        return {"prepared": True} if command == "prepare" else {"granted": True}

    class PersistedThenErroredStorage(MemoryRunnerStorage):
        def write_record(self, pr_number, provider, record):
            super().write_record(pr_number, provider, record)
            raise RuntimeError("response lost after persistence")

    monkeypatch.setattr(runner_core, "_authority_challenge_command", authority)
    primary = PersistedThenErroredStorage()
    decision = should_dispatch(
        42,
        "aaa",
        "codex",
        storage=runner_core.FallbackRunnerStorage(primary, MemoryRunnerStorage()),
        authority_challenge=True,
    )
    assert decision.should_dispatch
    assert decision.reason == "due-authority-challenge"
    assert commands == ["prepare", "finalize"]


def test_capability_effect_evidence_is_optional_and_empty() -> None:
    evidence = normalize_capability_effect_evidence()

    assert set(evidence.github_outputs().values()) == {""}


def test_capability_effect_evidence_normalizes_provider_neutral_fields() -> None:
    evidence = normalize_capability_effect_evidence(
        capability_id=" CAPABILITY:CONSUMER-SYNC ",
        effect_fingerprint="SHA256:" + "a" * 64,
        evidence_artifact_ref="github-actions:owner/repo:123:consumer-sync-plan",
        supervision_mode="HUMAN-ON-EXCEPTION",
        capability_evidence_status="ACCEPTED",
        terminal_disposition="SUCCESS",
    )

    assert evidence.github_outputs() == {
        "capability-id": "capability:consumer-sync",
        "effect-fingerprint": "sha256:" + "a" * 64,
        "evidence-artifact-ref": "github-actions:owner/repo:123:consumer-sync-plan",
        "supervision-mode": "human-on-exception",
        "capability-evidence-status": "accepted",
        "terminal-disposition": "success",
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"effect_fingerprint": "sha256:" + "a" * 64}, "partial capability evidence"),
        ({"capability_id": "consumer sync"}, "partial capability evidence"),
    ],
)
def test_capability_effect_evidence_rejects_partial_records(
    overrides: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_capability_effect_evidence(**overrides)


def test_capability_effect_evidence_rejects_spoofed_or_secret_bearing_values() -> None:
    valid = {
        "capability_id": "capability:consumer-sync",
        "effect_fingerprint": "sha256:" + "b" * 64,
        "evidence_artifact_ref": "artifact:consumer-sync:123",
        "supervision_mode": "shadow",
        "capability_evidence_status": "accepted",
        "terminal_disposition": "no-change",
    }
    with pytest.raises(ValueError, match="lowercase sha256"):
        normalize_capability_effect_evidence(
            **{**valid, "effect_fingerprint": "sha256:not-a-digest"}
        )
    for invalid_capability_id in (
        "capability:Consumer_Sync",
        "capability:foo-",
        "capability:foo--bar",
    ):
        with pytest.raises(ValueError, match="capability_id"):
            normalize_capability_effect_evidence(
                **{**valid, "capability_id": invalid_capability_id}
            )
    with pytest.raises(ValueError, match="partial capability evidence"):
        CapabilityEffectEvidence(capability_id="capability:consumer-sync")
    with pytest.raises(ValueError, match="secret-like"):
        normalize_capability_effect_evidence(
            **{**valid, "evidence_artifact_ref": "artifact:secret-token:123"}
        )
    for credential_like_ref in (
        "ghp_example",
        "github_pat_example",
        "sk-example",
        "artifact:ghp_example",
        "github-actions:owner/repo:sk-example",
    ):
        with pytest.raises(ValueError, match="credential-like prefix"):
            normalize_capability_effect_evidence(
                **{**valid, "evidence_artifact_ref": credential_like_ref}
            )
    assert (
        normalize_capability_effect_evidence(
            **{**valid, "evidence_artifact_ref": "github-actions:owner/repo:123:task-skipped"}
        ).evidence_artifact_ref
        == "github-actions:owner/repo:123:task-skipped"
    )
    with pytest.raises(ValueError, match="supervision_mode"):
        normalize_capability_effect_evidence(**{**valid, "supervision_mode": "owner-will-fix-it"})


@pytest.mark.parametrize("invalid_value", [None, False])
def test_capability_effect_evidence_rejects_non_string_direct_values(invalid_value: Any) -> None:
    with pytest.raises(ValueError, match="fields must be strings"):
        CapabilityEffectEvidence(capability_id=invalid_value)


def test_normalize_evidence_cli_writes_github_outputs(tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    command = [
        "python3",
        "-m",
        "scripts.runner_lib",
        "normalize-evidence",
        "--capability-id",
        "capability:consumer-sync",
        "--effect-fingerprint",
        "sha256:" + "c" * 64,
        "--evidence-artifact-ref",
        "artifact:consumer-sync:123",
        "--supervision-mode",
        "shadow",
        "--capability-evidence-status",
        "accepted",
        "--terminal-disposition",
        "no-change",
    ]
    completed = subprocess.run(
        command,
        cwd=Path(__file__).parents[2],
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["capability-id"] == "capability:consumer-sync"
    assert "effect-fingerprint=sha256:" in output.read_text(encoding="utf-8")


def _write_prompt_fixture(root: Path) -> None:
    (root / ".github" / "codex").mkdir(parents=True)
    (root / ".github" / "claude").mkdir(parents=True)
    (root / ".github" / "codex" / "AGENT_INSTRUCTIONS.md").write_text(
        "Codex instructions\n", encoding="utf-8"
    )
    (root / ".github" / "claude" / "AGENT_INSTRUCTIONS.md").write_text(
        "Claude instructions\n", encoding="utf-8"
    )
    (root / ".github" / "codex" / "prompts").mkdir(parents=True)
    (root / ".github" / "codex" / "prompts" / "task.md").write_text(
        "Fix the issue.\n", encoding="utf-8"
    )
    (root / ".reference").mkdir()
    (root / ".reference" / "REFERENCE_PACKS.md").write_text(
        "## baseline\n- `README.md`\n", encoding="utf-8"
    )


def test_assemble_prompt_formats_codex_prompt(tmp_path: Path) -> None:
    _write_prompt_fixture(tmp_path)

    prompt = assemble_prompt(
        "baseline",
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
            "appendix": "PR #123 context",
            "pr_number": "123",
        },
        "codex",
    )

    assert prompt.file == "codex-prompt-123.md"
    assert "Codex instructions" in prompt.text
    assert "## Task Prompt" in prompt.text
    assert "Fix the issue." in prompt.text
    assert "## Run context" in prompt.text
    assert "PR #123 context" in prompt.text
    assert "## Reference Packs" in prompt.text
    assert (tmp_path / "codex-prompt-123.md").read_text(encoding="utf-8") == prompt.text


def test_assemble_prompt_skips_stale_orchestrator_skill_section_when_summary_exists(
    tmp_path: Path,
) -> None:
    _write_prompt_fixture(tmp_path)
    orchestrator_summary = tmp_path / ".reference" / "ORCHESTRATOR_SKILL.md"
    orchestrator_summary.write_text(
        "Read and apply the materialized Orchestrator skill files before coordinating work.\n",
        encoding="utf-8",
    )

    prompt = assemble_prompt(
        None,
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
        },
        "codex",
    )

    assert "## Orchestrator Skill Context" not in prompt.text
    assert "Read and apply the materialized Orchestrator skill files" not in prompt.text


def test_assemble_prompt_includes_orchestrator_skill_section_when_materialized(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _write_prompt_fixture(tmp_path)

    def fake_materialize_orchestrator_skill(*_args: Any, **_kwargs: Any) -> Path:
        orchestrator_summary = tmp_path / ".reference" / "ORCHESTRATOR_SKILL.md"
        orchestrator_summary.write_text(
            "Read and apply the materialized Orchestrator skill files before coordinating work.\n",
            encoding="utf-8",
        )
        return orchestrator_summary

    monkeypatch.setattr(
        runner_core,
        "materialize_orchestrator_skill",
        fake_materialize_orchestrator_skill,
    )

    prompt = assemble_prompt(
        None,
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
            "materialize_orchestrator_skill": True,
        },
        "codex",
    )

    assert "## Orchestrator Skill Context" in prompt.text
    assert "Read and apply the materialized Orchestrator skill files" in prompt.text


def test_assemble_prompt_skips_orchestrator_skill_section_when_summary_missing(
    tmp_path: Path,
) -> None:
    _write_prompt_fixture(tmp_path)

    prompt = assemble_prompt(
        None,
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
        },
        "codex",
    )

    assert "## Orchestrator Skill Context" not in prompt.text


def test_assemble_prompt_rejects_orchestrator_summary_outside_workspace(
    tmp_path: Path,
) -> None:
    _write_prompt_fixture(tmp_path)
    outside = tmp_path.parent / "outside-summary.md"
    outside.write_text("outside\n", encoding="utf-8")

    with pytest.raises(ValueError, match="orchestrator_skill_summary_path"):
        assemble_prompt(
            None,
            {
                "workspace": tmp_path,
                "base_prompt_file": ".github/codex/prompts/task.md",
                "orchestrator_skill_summary_path": outside,
            },
            "codex",
        )


def test_assemble_prompt_resolves_relative_orchestrator_summary_from_workspace(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _write_prompt_fixture(tmp_path)
    summary = tmp_path / ".reference" / "ORCHESTRATOR_SKILL.md"
    summary.write_text("orchestrator context\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path.parent)

    prompt = assemble_prompt(
        None,
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
            "orchestrator_skill_summary_path": ".reference/ORCHESTRATOR_SKILL.md",
        },
        "codex",
    )

    assert "orchestrator context" in prompt.text


def test_assemble_prompt_formats_claude_prompt(tmp_path: Path) -> None:
    _write_prompt_fixture(tmp_path)

    prompt = assemble_prompt(
        "baseline",
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
            "appendix": "Claude context",
        },
        "claude",
    )

    assert prompt.file == "claude-prompt.md"
    assert "Claude instructions" in prompt.text
    assert "Codex instructions" not in prompt.text
    assert "Claude context" in prompt.text


def test_assemble_prompt_formats_cursor_prompt(tmp_path: Path) -> None:
    _write_prompt_fixture(tmp_path)

    prompt = assemble_prompt(
        "baseline",
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
            "appendix": "Cursor context",
        },
        "cursor",
    )

    assert prompt.file == "cursor-prompt.md"
    assert prompt.provider == "cursor"
    assert "Cursor context" in prompt.text


def test_parse_cursor_text_output_success() -> None:
    result = parse_runner_output("cursor", "Implemented the change and ran tests.\n")

    assert result.success is True
    assert "Implemented the change" in result.final_message
    assert result.error is None


def test_assemble_prompt_formats_gemini_prompt(tmp_path: Path) -> None:
    _write_prompt_fixture(tmp_path)

    prompt = assemble_prompt(
        "baseline",
        {
            "workspace": tmp_path,
            "base_prompt_file": ".github/codex/prompts/task.md",
            "appendix": "Gemini context",
        },
        "gemini",
    )

    assert prompt.file == "gemini-prompt.md"
    assert prompt.provider == "gemini"
    assert "Gemini context" in prompt.text


def test_parse_gemini_text_output_success() -> None:
    result = parse_runner_output("gemini", "Implemented the change and ran tests.\n")

    assert result.success is True
    assert "Implemented the change" in result.final_message
    assert result.error is None


def test_parse_codex_jsonl_success() -> None:
    raw = "\n".join(
        [
            json.dumps({"type": "step", "message": "working"}),
            json.dumps({"type": "final", "message": "Done"}),
        ]
    )

    result = parse_runner_output("codex", raw)

    assert result.success is True
    assert result.final_message == "Done"
    assert result.summary == "Done"
    assert result.error is None


def test_parse_codex_jsonl_error_without_message_uses_error_summary() -> None:
    raw = json.dumps(
        {
            "type": "turn.failed",
            "error": "Codex CLI exited before writing final output",
        }
    )

    result = parse_runner_output("codex", raw)

    assert result.success is False
    assert "Codex CLI exited before writing final output" in result.summary
    assert result.final_message == result.error


def test_parse_codex_jsonl_error_prefers_error_over_progress() -> None:
    raw = "\n".join(
        [
            json.dumps({"type": "step", "message": "Inspecting repository"}),
            json.dumps({"type": "turn.failed", "error": "Codex auth failed"}),
        ]
    )

    result = parse_runner_output("codex", raw)

    assert result.success is False
    assert result.error == "Codex auth failed"
    assert result.final_message == "Codex auth failed"
    assert result.summary == "Codex auth failed"


def test_parse_codex_jsonl_error_extracts_dict_message() -> None:
    raw = json.dumps(
        {
            "type": "turn.failed",
            "error": {"message": "Codex auth failed with status 401"},
        }
    )

    result = parse_runner_output("codex", raw)

    assert result.success is False
    assert result.error == "Codex auth failed with status 401"
    assert result.final_message == "Codex auth failed with status 401"
    assert result.summary == "Codex auth failed with status 401"


def test_parse_runner_output_detects_error() -> None:
    result = parse_runner_output("claude", "Error: auth failed\n")

    assert result.success is False
    assert result.error == "Error: auth failed"
    assert result.summary == "Error: auth failed"


def test_parse_runner_output_detects_multiline_error_annotation() -> None:
    result = parse_runner_output("claude", "Starting work\n::error:: auth failed\n")

    assert result.success is False
    assert result.error == "::error:: auth failed"


def test_parse_runner_output_marks_truncated_output() -> None:
    result = parse_runner_output("claude", "x" * 65000)

    assert result.truncated is True
    assert len(result.final_message) == 64000


def test_should_dispatch_first_duplicate_and_sha_changed() -> None:
    storage = MemoryRunnerStorage()

    first = should_dispatch(42, "aaa", "codex", storage=storage)
    duplicate = should_dispatch(42, "aaa", "codex", storage=storage)
    changed = should_dispatch(42, "bbb", "codex", storage=storage)

    assert first.should_dispatch is True
    assert first.reason == "first-dispatch"
    assert duplicate.should_dispatch is False
    assert duplicate.reason == "duplicate-pending"
    assert changed.should_dispatch is True
    assert changed.reason == "head-sha-changed"


def test_should_dispatch_allows_stale_pending_record() -> None:
    storage = MemoryRunnerStorage()
    storage.records[(42, "codex")] = {
        "provider": "codex",
        "pr_number": 42,
        "head_sha": "aaa",
        "status": "pending",
        "started_at": "2026-05-06T00:00:00Z",
    }

    decision = should_dispatch(42, "aaa", "codex", storage=storage)

    assert decision.should_dispatch is True
    assert decision.reason == "stale-pending"


def test_should_dispatch_uses_specific_retry_reason_for_error_status() -> None:
    storage = MemoryRunnerStorage()
    storage.records[(42, "codex")] = {
        "provider": "codex",
        "pr_number": 42,
        "head_sha": "aaa",
        "status": "error",
    }

    decision = should_dispatch(42, "aaa", "codex", storage=storage)

    assert decision.should_dispatch is True
    assert decision.reason == "retry-error"


def test_record_completion_is_idempotent_for_same_key() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "claude", storage=storage)
    result = parse_runner_output("claude", "Done")

    first = record_completion(42, "aaa", "claude", result, storage=storage)
    second = record_completion(42, "aaa", "claude", result, storage=storage)

    assert first["status"] == "completed"
    assert second["status"] == "completed"
    assert second["completed_at"] == first["completed_at"]
    assert storage.records[(42, "claude")]["result"]["summary"] == "Done"


def test_record_completion_stores_compact_result_payload() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    result = parse_runner_output("codex", "x" * 10000)

    record = record_completion(42, "aaa", "codex", result, storage=storage)

    assert record["result"]["summary"] == "x" * 500
    assert "final_message" not in record["result"]
    assert len(record["result"]["final_message_sha256"]) == 64
    assert record["result"]["final_message_chars"] == 10000


def test_record_completion_stores_compact_marker_safe_result() -> None:
    storage = MemoryRunnerStorage()
    result = {
        "provider": "claude",
        "success": True,
        "final_message": "full output --> with marker closer",
        "summary": "summary --> closer",
        "error": None,
        "truncated": False,
    }

    record = record_completion(42, "aaa", "claude", result, storage=storage)

    stored_result = storage.records[(42, "claude")]["result"]
    assert record["result"] == stored_result
    assert stored_result["schema"] == "runner-result-summary/v1"
    assert stored_result["summary"] == "summary --\\u003e closer"
    assert "final_message" not in stored_result
    assert stored_result["final_message_chars"] == len(result["final_message"])
    assert len(stored_result["final_message_sha256"]) == 64
    assert "-->" not in json.dumps(stored_result)


def test_record_completion_preserves_falsy_result_text() -> None:
    storage = MemoryRunnerStorage()
    result = {
        "provider": "claude",
        "success": False,
        "final_message": False,
        "summary": 0,
        "error": False,
        "truncated": False,
    }

    record = record_completion(42, "aaa", "claude", result, storage=storage)

    assert record["result"]["summary"] == "0"
    assert record["result"]["error"] == "False"
    assert record["result"]["final_message_chars"] == len("False")
    assert len(record["result"]["final_message_sha256"]) == 64


def test_materialize_reference_packs_keeps_token_out_of_git_argv(
    tmp_path: Path, monkeypatch: Any
) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "reference_packs.json").write_text(
        json.dumps(
            {
                "baseline": {
                    "repo": "owner/private",
                    "ref": "main",
                    "paths": ["README.md"],
                }
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_check_call(cmd: list[str], **kwargs: Any) -> int:
        env = kwargs.get("env") or {}
        calls.append((cmd, env))
        assert "secret-token" not in " ".join(cmd)
        if cmd[:2] == ["git", "clone"]:
            clone_dir = Path(cmd[-1])
            clone_dir.mkdir(parents=True)
            (clone_dir / "README.md").write_text("reference\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    summary = materialize_reference_packs(tmp_path, token="secret-token")

    assert summary == tmp_path / ".reference" / "REFERENCE_PACKS.md"
    assert (tmp_path / ".reference" / "baseline" / "README.md").is_file()
    assert calls
    assert all(env.get("GIT_ASKPASS_PASSWORD") == "secret-token" for _cmd, env in calls)


def test_materialize_orchestrator_skill_clears_stale_pack_checkout(
    tmp_path: Path, monkeypatch: Any
) -> None:
    checkout = tmp_path / ".reference" / "orchestrator"
    checkout.mkdir(parents=True)
    stale_file = checkout / "removed-upstream.md"
    stale_file.write_text("stale\n", encoding="utf-8")

    plan = types.SimpleNamespace(name="orchestrator", checkout_path=".reference/orchestrator")
    fake_reference_packs = types.SimpleNamespace(
        load_reference_packs=lambda _workspace: types.SimpleNamespace(packs=[plan]),
        build_checkout_plan=lambda _packs: [plan],
    )

    def fake_load_reference_packs_module() -> Any:
        return fake_reference_packs

    def fake_materialize_reference_packs(*_args: Any, **_kwargs: Any) -> Path:
        assert not stale_file.exists()
        checkout.mkdir(parents=True, exist_ok=True)
        (checkout / "SKILL.md").write_text("# Fresh skill\n", encoding="utf-8")
        return tmp_path / ".reference" / "REFERENCE_PACKS.md"

    monkeypatch.setattr(
        runner_core,
        "_load_reference_packs_module",
        fake_load_reference_packs_module,
    )
    monkeypatch.setattr(
        runner_core,
        "materialize_reference_packs",
        fake_materialize_reference_packs,
    )

    summary = runner_core.materialize_orchestrator_skill(
        tmp_path,
        pack_override="orchestrator",
        enabled_override=True,
    )

    assert summary == tmp_path / ".reference" / "ORCHESTRATOR_SKILL.md"
    assert not stale_file.exists()
    assert (checkout / "SKILL.md").read_text(encoding="utf-8") == "# Fresh skill\n"
    assert "`SKILL.md`" in summary.read_text(encoding="utf-8")


def test_materialize_orchestrator_skill_surfaces_stale_checkout_cleanup_errors(
    tmp_path: Path, monkeypatch: Any
) -> None:
    plan = types.SimpleNamespace(name="orchestrator", checkout_path=".reference/orchestrator")
    fake_reference_packs = types.SimpleNamespace(
        load_reference_packs=lambda _workspace: types.SimpleNamespace(packs=[plan]),
        build_checkout_plan=lambda _packs: [plan],
    )

    def fake_load_reference_packs_module() -> Any:
        return fake_reference_packs

    def fake_rmtree(_path: Path) -> None:
        raise PermissionError("locked checkout")

    monkeypatch.setattr(
        runner_core,
        "_load_reference_packs_module",
        fake_load_reference_packs_module,
    )
    monkeypatch.setattr(runner_core.shutil, "rmtree", fake_rmtree)

    with pytest.raises(PermissionError, match="locked checkout"):
        runner_core.materialize_orchestrator_skill(
            tmp_path,
            pack_override="orchestrator",
            enabled_override=True,
        )


@pytest.mark.parametrize("checkout_path", [".reference/.", ".reference/.."])
def test_materialize_orchestrator_skill_rejects_unsafe_pack_checkout(
    tmp_path: Path,
    monkeypatch: Any,
    checkout_path: str,
) -> None:
    plan = types.SimpleNamespace(name="orchestrator", checkout_path=checkout_path)
    fake_reference_packs = types.SimpleNamespace(
        load_reference_packs=lambda _workspace: types.SimpleNamespace(packs=[plan]),
        build_checkout_plan=lambda _packs: [plan],
    )

    def fake_load_reference_packs_module() -> Any:
        return fake_reference_packs

    monkeypatch.setattr(
        runner_core,
        "_load_reference_packs_module",
        fake_load_reference_packs_module,
    )

    with pytest.raises(ValueError, match="reference checkout path"):
        runner_core.materialize_orchestrator_skill(
            tmp_path,
            pack_override="orchestrator",
            enabled_override=True,
        )


def test_pr_comment_marker_round_trips_nested_result_payload() -> None:
    result = parse_runner_output("claude", "Done")
    record = {
        "provider": "claude",
        "pr_number": 42,
        "head_sha": "aaa",
        "status": "completed",
        "result": {
            "summary": result.summary,
            "nested": {"value": "inner"},
            "final_message": "contains --> comment closer",
        },
    }

    marker = runner_core._build_marker(42, "claude", record)
    parsed = runner_core._extract_record(marker, 42, "claude")

    assert parsed == record


def test_pr_comment_marker_rejects_invalid_base64_payload() -> None:
    marker = "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 base64:!!!not-base64!!! -->"

    assert runner_core._extract_record(marker, 42, "codex") is None


def test_pr_comment_marker_rejects_invalid_utf8_payload() -> None:
    marker = "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 base64://8= -->"

    assert runner_core._extract_record(marker, 42, "codex") is None


def test_prompt_cli_rejects_non_prompt_provider() -> None:
    parser = runner_core.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "assemble-prompt",
                "--provider",
                "autofix",
                "--base-prompt",
                ".github/codex/prompts/task.md",
            ]
        )


def test_parse_output_cli_accepts_autofix_provider() -> None:
    parser = runner_core.build_parser()

    args = parser.parse_args(["parse-output", "--provider", "autofix"])

    assert args.provider == "autofix"


def _graphql_comments(comments: list[dict[str, Any]], request: dict[str, Any]) -> dict[str, Any]:
    cursor = request["variables"]["cursor"]
    ordered = sorted(comments, key=lambda item: item["id"])
    if cursor is not None:
        ordered = [item for item in ordered if item["id"] < int(cursor)]
    page = ordered[-100:]
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "comments": {
                        "nodes": [
                            {
                                "databaseId": item["id"],
                                "fullDatabaseId": str(item["id"]),
                                "body": item["body"],
                                "author": item.get("user"),
                                "authorAssociation": item.get("author_association"),
                            }
                            for item in page
                        ],
                        "pageInfo": {
                            "hasPreviousPage": len(ordered) > len(page),
                            "startCursor": str(page[0]["id"]) if page else None,
                            "hasNextPage": False,
                            "endCursor": str(page[-1]["id"]) if page else None,
                        },
                    }
                }
            }
        }
    }


def test_pr_comment_storage_accepts_full_width_graphql_ids() -> None:
    comment_id = 5_807_299_200

    class FakeApi:
        repo = "owner/repo"

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            assert method == "POST" and path == "/graphql" and body is not None
            assert "fullDatabaseId" in body["query"]
            assert "databaseId" not in body["query"]
            response = _graphql_comments([{"body": "marker", "id": comment_id}], body)
            node = response["data"]["repository"]["pullRequest"]["comments"]["nodes"][0]
            node["databaseId"] = None
            return response

    storage = PrCommentRunnerStorage(FakeApi())  # type: ignore[arg-type]
    assert [comment["id"] for comment in storage._iter_comments(42)] == [comment_id]


def test_pr_comment_storage_retries_legacy_query_only_for_missing_full_id_field() -> None:
    class FakeApi:
        repo = "owner/repo"

        def __init__(self) -> None:
            self.queries: list[str] = []

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            assert method == "POST" and path == "/graphql" and body is not None
            query = body["query"]
            self.queries.append(query)
            if "fullDatabaseId" in query:
                return {
                    "errors": [
                        {"message": "Field 'fullDatabaseId' doesn't exist on type 'IssueComment'"}
                    ]
                }
            response = _graphql_comments([{"body": "marker", "id": 41}], body)
            del response["data"]["repository"]["pullRequest"]["comments"]["nodes"][0][
                "fullDatabaseId"
            ]
            return response

    api = FakeApi()
    storage = PrCommentRunnerStorage(api)  # type: ignore[arg-type]
    assert [comment["id"] for comment in storage._iter_comments(42)] == [41]
    assert len(api.queries) == 2
    assert "fullDatabaseId" in api.queries[0]
    assert "fullDatabaseId" not in api.queries[1]
    assert "databaseId" in api.queries[1]


def test_pr_comment_storage_does_not_retry_unrelated_graphql_error() -> None:
    class FakeApi:
        repo = "owner/repo"

        def __init__(self) -> None:
            self.calls = 0

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            self.calls += 1
            return {"errors": [{"message": "Resource not accessible by integration"}]}

    api = FakeApi()
    storage = PrCommentRunnerStorage(api)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="GraphQL error"):
        list(storage._iter_comments(42))
    assert api.calls == 1


def test_pr_comment_storage_stops_when_marker_found() -> None:
    class FakeApi:
        repo = "owner/repo"

        def __init__(self) -> None:
            self.paths: list[str] = []

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            self.paths.append(path)
            assert method == "POST" and path == "/graphql" and body is not None
            return _graphql_comments(
                [
                    {"body": "ordinary comment", "id": 1},
                    {
                        "body": (
                            "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                            '{"provider":"codex","head_sha":"abc"} -->'
                        ),
                        "id": 2,
                    },
                ],
                body,
            )

    api = FakeApi()
    storage = PrCommentRunnerStorage(api)  # type: ignore[arg-type]

    record = storage.read_record(42, "codex")

    assert record == {"provider": "codex", "head_sha": "abc"}
    assert len(api.paths) == 1


def test_pr_comment_storage_normalizes_direction_case() -> None:
    class FakeApi:
        repo = "owner/repo"

        def __init__(self) -> None:
            self.paths: list[str] = []

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            self.paths.append(path)
            assert method == "POST" and path == "/graphql" and body is not None
            return _graphql_comments([], body)

    api = FakeApi()
    storage = PrCommentRunnerStorage(api)  # type: ignore[arg-type]

    assert list(storage._iter_comments(42, direction="DESC")) == []
    assert api.paths[0] == "/graphql"


def test_pr_comment_storage_selects_newest_marker_from_newest_page() -> None:
    class FakeApi:
        repo = "owner/repo"

        def __init__(self) -> None:
            self.paths: list[str] = []

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            assert method == "POST" and path == "/graphql" and body is not None
            self.paths.append(path)
            return _graphql_comments(
                [
                    {
                        "body": (
                            "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                            '{"provider":"codex","head_sha":"old"} -->'
                        ),
                        "id": 1,
                    },
                    {
                        "body": (
                            "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                            '{"provider":"codex","head_sha":"new"} -->'
                        ),
                        "id": 101,
                    },
                ],
                body,
            )

    api = FakeApi()
    storage = PrCommentRunnerStorage(api)  # type: ignore[arg-type]

    assert storage.read_record(42, "codex") == {"provider": "codex", "head_sha": "new"}
    assert len(api.paths) == 1


def test_pr_comment_storage_ignores_untrusted_marker_comments() -> None:
    class FakeApi:
        repo = "owner/repo"

        def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            assert method == "POST" and path == "/graphql" and body is not None
            return _graphql_comments(
                [
                    {
                        "body": (
                            "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                            '{"provider":"codex","head_sha":"spoofed"} -->'
                        ),
                        "id": 1,
                        "user": {"login": "drive-by-commenter"},
                        "author_association": "NONE",
                    },
                    {
                        "body": (
                            "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                            '{"provider":"codex","head_sha":"trusted"} -->'
                        ),
                        "id": 2,
                        "user": {"login": "github-actions", "__typename": "Bot"},
                        "author_association": "NONE",
                    },
                    {
                        "body": (
                            "Runner dispatch state\n\n<!-- runner-dispatch:codex:42:v1 "
                            '{"provider":"codex","head_sha":"spoofed-user"} -->'
                        ),
                        "id": 3,
                        "user": {"login": "github-actions", "__typename": "User"},
                        "author_association": "NONE",
                    },
                ],
                body,
            )

    storage = PrCommentRunnerStorage(FakeApi())  # type: ignore[arg-type]

    assert storage.read_record(42, "codex") == {"provider": "codex", "head_sha": "trusted"}


def test_materialize_reference_packs_import_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_import(name: str) -> Any:
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr(runner_core.importlib, "import_module", fail_import)

    with pytest.raises(RuntimeError, match="reference packs are not supported"):
        runner_core.materialize_reference_packs(".")


def test_materialize_reference_packs_does_not_put_token_in_git_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = "ghp_secret_token"
    plan = types.SimpleNamespace(
        name="baseline",
        repo="stranske/private-reference",
        ref="main",
        paths=["README.md"],
        checkout_path=".reference/baseline",
    )
    fake_reference_packs = types.SimpleNamespace(
        load_reference_packs=lambda _workspace: types.SimpleNamespace(exists=True, packs=[plan]),
        build_checkout_plan=lambda _packs: [plan],
    )
    calls: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_import(name: str) -> Any:
        assert name == "scripts.reference_packs"
        return fake_reference_packs

    def fail_check_call(
        args: list[str],
        stdout: Any = None,
        stderr: Any = None,
        env: dict[str, str] | None = None,
    ) -> None:
        calls.append((args, env))
        raise subprocess.CalledProcessError(128, args)

    monkeypatch.setattr(runner_core.importlib, "import_module", fake_import)
    monkeypatch.setattr(runner_core.subprocess, "check_call", fail_check_call)

    with pytest.raises(RuntimeError) as exc_info:
        runner_core.materialize_reference_packs(tmp_path, token=token)

    assert token not in str(exc_info.value)
    assert calls
    clone_cmd, clone_env = calls[0]
    assert all(token not in part for part in clone_cmd)
    assert clone_env is not None
    assert clone_env["GIT_ASKPASS_PASSWORD"] == token
    assert Path(clone_env["GIT_ASKPASS"]).exists() is False


@pytest.mark.parametrize(
    ("prior", "expected"),
    [
        (None, False),
        ({}, False),
        ({"productive": None}, False),
        ({"productive": True}, False),
        ({"productive": False}, True),
        ({"productive": 0}, False),
        ({"productive": "false"}, False),
    ],
)
def test_completion_productivity_requires_explicit_false(
    prior: dict[str, Any] | None, expected: bool
) -> None:
    assert runner_core._completion_was_unproductive(prior) is expected


@pytest.mark.parametrize(
    "new_run,new_attempt,new_head", [("200", "1", "aaa"), ("100", "2", "aaa"), ("200", "1", "bbb")]
)
def test_stale_workflow_completion_cannot_replace_new_reservation(
    monkeypatch: pytest.MonkeyPatch, new_run: str, new_attempt: str, new_head: str
) -> None:
    storage = MemoryRunnerStorage()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    should_dispatch(42, "aaa", "codex", storage=storage)
    record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )
    monkeypatch.setenv("GITHUB_RUN_ID", new_run)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", new_attempt)
    assert should_dispatch(42, new_head, "codex", storage=storage).should_dispatch
    pending = dict(storage.records[(42, "codex")])
    writes = len(storage.writes)

    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    ignored = record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )

    assert ignored["completion_recorded"] is False
    assert ignored["completion_reason"] == "stale-attempt"
    assert storage.records[(42, "codex")] == pending
    assert len(storage.writes) == writes


@pytest.mark.parametrize("completion_run", ["100", "200"])
def test_productive_head_change_requires_owning_attempt(
    monkeypatch: pytest.MonkeyPatch, completion_run: str
) -> None:
    storage = MemoryRunnerStorage()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    should_dispatch(42, "aaa", "codex", storage=storage)
    pending = dict(storage.records[(42, "codex")])
    monkeypatch.setenv("GITHUB_RUN_ID", completion_run)

    result = record_completion(
        42, "bbb", "codex", _unproductive_result(), storage=storage, produced_work=True
    )

    if completion_run == "100":
        assert result["head_sha"] == "bbb"
        assert result["workflow_attempt_id"] == "owner/repo:100:1"
        assert result["productive"] is True
        assert result["unproductive_completions"] == 0
        assert len(storage.writes) == 2
    else:
        assert result["completion_recorded"] is False
        assert result["completion_reason"] == "stale-attempt"
        assert storage.records[(42, "codex")] == pending
        assert len(storage.writes) == 1


@pytest.mark.parametrize("operation", ["read", "write"])
@pytest.mark.parametrize("has_identity", [True, False])
@pytest.mark.parametrize("previous_fallback", [True, False])
def test_auto_dispatch_requires_primary_storage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: str,
    has_identity: bool,
    previous_fallback: bool,
) -> None:
    primary = MemoryRunnerStorage()
    fallback = MemoryRunnerStorage()
    storage = runner_core.FallbackRunnerStorage(primary, fallback)
    # A reused adapter must not retain an earlier fallback-write selection.
    storage._use_fallback = previous_fallback
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    if not has_identity:
        monkeypatch.delenv("GITHUB_RUN_ID")
    original = getattr(primary, f"{operation}_record")
    secret = "private-response-and-token"

    def fail(*_: Any) -> Any:
        raise RuntimeError(secret) from HTTPError(
            "https://example.invalid/" + secret, 403, secret, {}, None
        )

    monkeypatch.setattr(primary, f"{operation}_record", fail)
    decision = should_dispatch(42, "aaa", "codex", storage=storage)

    assert decision.should_dispatch is False
    assert decision.reason == "authoritative-storage-unavailable"
    assert "primary" in decision.drainable
    assert not primary.writes
    assert not fallback.writes
    error = capsys.readouterr().err
    assert f"authoritative reservation {operation} failed" in error
    assert "http_status=403" in error
    assert secret not in error

    # Recovery requires only healthy storage, not a new head or manual state cleanup.
    monkeypatch.setattr(primary, f"{operation}_record", original)
    assert should_dispatch(42, "aaa", "codex", storage=storage).should_dispatch
    assert primary.records[(42, "codex")]["status"] == "pending"
    completed = record_completion(42, "aaa", "codex", _unproductive_result(), storage=storage)
    assert completed["status"] == "completed"
    assert primary.records[(42, "codex")] == completed
    assert not fallback.writes


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_auto_dispatch_checks_real_legacy_backend_access(
    status: int, capsys: pytest.CaptureFixture[str]
) -> None:
    class DeniedApi:
        repo = "owner/repo"

        def request(self, method: str, path: str) -> Any:
            assert method == "GET"
            assert "/actions/variables/" in path
            raise RuntimeError(f"GitHub API GET failed: {status} private-response") from HTTPError(
                "https://example.invalid/private-response", status, "private-response", {}, None
            )

    primary = MemoryRunnerStorage()
    fallback = runner_core.RepoVariableRunnerStorage(DeniedApi())  # type: ignore[arg-type]
    decision = should_dispatch(
        42, "aaa", "codex", storage=runner_core.FallbackRunnerStorage(primary, fallback)
    )

    if status == 404:
        assert decision.should_dispatch is True
        assert primary.records[(42, "codex")]["status"] == "pending"
        assert capsys.readouterr().err == ""
    else:
        assert decision.should_dispatch is False
        assert decision.reason == "authoritative-storage-unavailable"
        assert not primary.writes
        error = capsys.readouterr().err
        assert f"http_status={status}" in error
        assert "private-response" not in error


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_explicit_repo_variable_read_retains_compatibility(status: int) -> None:
    class DeniedApi:
        repo = "owner/repo"

        def request(self, method: str, path: str) -> Any:
            raise RuntimeError(f"GitHub API GET failed: {status} denied")

    storage = runner_core.RepoVariableRunnerStorage(DeniedApi())  # type: ignore[arg-type]
    if status in (401, 403, 404):
        assert storage.read_record(42, "codex") is None
    else:
        with pytest.raises(RuntimeError, match="500"):
            storage.read_record(42, "codex")


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("operation", ["reserve", "complete"])
def test_repo_variable_denied_write_cannot_report_success(status, operation, capsys):
    class DeniedWriteApi:
        repo = "owner/repo"

        def request(self, method, path, payload=None):
            if method == "GET":
                return {}
            assert method == "PATCH"
            raise RuntimeError(f"GitHub API PATCH failed: {status} private-response")

    storage = runner_core.RepoVariableRunnerStorage(DeniedWriteApi())
    with pytest.raises(RuntimeError, match="Repository-variable write failed") as raised:
        if operation == "reserve":
            should_dispatch(42, "aaa", "codex", storage=storage)
        else:
            record_completion(42, "aaa", "codex", {"success": True}, storage=storage)
    assert "private-response" not in capsys.readouterr().err
    assert str(status) in str(raised.value.__cause__)


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("command", ["should-dispatch", "record-completion"])
@pytest.mark.parametrize("create", [False, True])
def test_repo_variable_cli_does_not_log_write_response(
    status, command, create, monkeypatch, capsys, tmp_path
):
    class DeniedApi:
        repo = "owner/repo"

        def request(self, method, path, payload=None):
            if method == "GET":
                return {}
            if create and method == "PATCH":
                raise RuntimeError("GitHub API PATCH failed: 404 absent")
            raise RuntimeError(f"GitHub API write failed: {status} private-response")

    monkeypatch.setattr(
        runner_core,
        "_storage_from_name",
        lambda _: runner_core.RepoVariableRunnerStorage(DeniedApi()),
    )
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert (
        runner_core.main(
            [
                command,
                "--provider",
                "codex",
                "--pr-number",
                "42",
                "--head-sha",
                "aaa",
                "--storage",
                "repo-variable",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "Repository-variable" in captured.err
    assert "private-response" not in captured.err
    assert not captured.out
    assert not output.exists()


def test_repo_variable_missing_write_creates_variable():
    calls = []

    class CreateApi:
        repo = "owner/repo"

        def request(self, method, path, payload=None):
            calls.append((method, path, payload))
            if method == "PATCH":
                raise RuntimeError("GitHub API PATCH failed: 404 missing")
            return {}

    storage = runner_core.RepoVariableRunnerStorage(CreateApi())
    record = {"status": "pending"}
    storage.write_record(42, "codex", record)
    assert [call[0] for call in calls] == ["PATCH", "POST"]
    assert json.loads(calls[1][2]["value"]) == record


def test_auto_dispatch_cli_refuses_unreadable_legacy_state(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    primary = MemoryRunnerStorage()
    fallback = MemoryRunnerStorage()

    def fail(*_: Any) -> Any:
        raise RuntimeError("private legacy state")

    monkeypatch.setattr(fallback, "read_record", fail)
    monkeypatch.setattr(
        runner_core,
        "_storage_from_name",
        lambda _: runner_core.FallbackRunnerStorage(primary, fallback),
    )
    outputs = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    assert (
        runner_core.main(
            ["should-dispatch", "--provider", "codex", "--pr-number", "42", "--head-sha", "aaa"]
        )
        == 0
    )
    captured = capsys.readouterr()
    decision = json.loads(captured.out)
    assert decision["should_dispatch"] == "false"
    assert decision["reason"] == "authoritative-storage-unavailable"
    assert "legacy-state" in decision["drainable"]
    assert "should_dispatch=false" in outputs.read_text()
    assert "private legacy state" not in captured.err
    assert not primary.writes
    assert not fallback.writes


def test_auto_dispatch_ambiguous_primary_write_recovers_exact_reservation_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = MemoryRunnerStorage()
    fallback = MemoryRunnerStorage()
    storage = runner_core.FallbackRunnerStorage(primary, fallback)
    original = primary.write_record

    def ambiguous_write(pr_number: int, provider: str, record: dict[str, Any]) -> None:
        original(pr_number, provider, record)
        raise RuntimeError("response lost after server persisted reservation")

    monkeypatch.setattr(primary, "write_record", ambiguous_write)
    assert should_dispatch(42, "aaa", "codex", storage=storage).should_dispatch is True
    assert primary.records[(42, "codex")]["status"] == "pending"
    assert not fallback.writes
    monkeypatch.setattr(primary, "write_record", original)
    assert should_dispatch(42, "aaa", "codex", storage=storage).reason == "duplicate-pending"
    primary.records[(42, "codex")]["started_at"] = "2000-01-01T00:00:00Z"
    assert should_dispatch(42, "aaa", "codex", storage=storage).should_dispatch is True
    assert not fallback.writes


def test_auto_dispatch_failed_primary_write_without_persistence_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = MemoryRunnerStorage()
    fallback = MemoryRunnerStorage()
    storage = runner_core.FallbackRunnerStorage(primary, fallback)

    def failed_write(pr_number: int, provider: str, record: dict[str, Any]) -> None:
        raise RuntimeError("write failed before commit")

    monkeypatch.setattr(primary, "write_record", failed_write)
    decision = should_dispatch(42, "aaa", "codex", storage=storage)
    assert decision.should_dispatch is False
    assert decision.reason == "authoritative-storage-unavailable"
    assert not primary.records
    assert not fallback.writes


def test_auto_dispatch_preserves_live_legacy_fallback_then_migrates_stale_reservation() -> None:
    primary = MemoryRunnerStorage()
    fallback = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=fallback)
    storage = runner_core.FallbackRunnerStorage(primary, fallback)

    decision = should_dispatch(42, "aaa", "codex", storage=storage)
    assert decision.should_dispatch is False
    assert decision.reason == "duplicate-pending"
    assert not primary.writes
    fallback.records[(42, "codex")]["started_at"] = "2000-01-01T00:00:00Z"
    prior = dict(fallback.records[(42, "codex")])

    assert should_dispatch(42, "aaa", "codex", storage=storage).reason == "stale-pending"
    assert primary.records[(42, "codex")]["status"] == "pending"
    completed = record_completion(42, "aaa", "codex", _unproductive_result(), storage=storage)
    assert completed["status"] == "completed"
    assert primary.records[(42, "codex")] == completed
    assert fallback.records[(42, "codex")] == prior
    assert len(fallback.writes) == 1


def test_auto_dispatch_uses_primary_when_fallback_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = MemoryRunnerStorage()
    fallback = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=primary)
    record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=primary, produced_work=False
    )

    def fail(*_: Any) -> Any:
        raise AssertionError("fallback must not be read or written")

    monkeypatch.setattr(fallback, "read_record", fail)
    monkeypatch.setattr(fallback, "write_record", fail)
    storage = runner_core.FallbackRunnerStorage(primary, fallback)
    storage._use_fallback = True
    decision = should_dispatch(42, "aaa", "codex", storage=storage)
    assert decision.should_dispatch is True
    assert decision.reason == "retry-unproductive-completion"
    assert primary.records[(42, "codex")]["status"] == "pending"


@pytest.mark.parametrize("operation", ["read", "write"])
def test_single_store_dispatch_errors_still_propagate(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    storage = MemoryRunnerStorage()
    error = RuntimeError("single-store failure")

    def fail(*_: Any) -> Any:
        raise error

    monkeypatch.setattr(storage, f"{operation}_record", fail)
    with pytest.raises(RuntimeError) as caught:
        should_dispatch(42, "aaa", "codex", storage=storage)
    assert caught.value is error


@pytest.mark.parametrize("primary_state", ["unavailable", "missing"])
@pytest.mark.parametrize("fallback_state", ["empty", "stale"])
@pytest.mark.parametrize("has_identity", [True, False])
def test_auto_completion_requires_authoritative_reservation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    primary_state: str,
    fallback_state: str,
    has_identity: bool,
) -> None:
    primary = MemoryRunnerStorage()
    fallback = MemoryRunnerStorage()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    if fallback_state == "stale":
        should_dispatch(42, "aaa", "codex", storage=fallback)
    monkeypatch.setenv("GITHUB_RUN_ID", "200")
    should_dispatch(42, "aaa", "codex", storage=primary)
    primary_before = dict(primary.records)
    fallback_before = dict(fallback.records)
    writes = (len(primary.writes), len(fallback.writes))

    def read_primary(*_: Any) -> dict[str, Any] | None:
        if primary_state == "unavailable":
            raise RuntimeError("primary unavailable")
        return None

    monkeypatch.setattr(primary, "read_record", read_primary)
    storage = runner_core.FallbackRunnerStorage(primary, fallback)
    monkeypatch.setattr(runner_core, "_storage_from_name", lambda _: storage)
    if has_identity:
        monkeypatch.setenv("GITHUB_RUN_ID", "100")
    else:
        monkeypatch.delenv("GITHUB_RUN_ID")
    assert (
        runner_core.main(
            [
                "record-completion",
                "--provider",
                "codex",
                "--pr-number",
                "42",
                "--head-sha",
                "aaa",
                "--summary",
                "Done",
                "--produced-work",
                "true",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["recorded"] == "false"
    assert output["reason"] == (
        "authoritative-storage-unavailable"
        if primary_state == "unavailable"
        else "authoritative-reservation-missing"
    )
    assert output["status"] == "unknown"
    assert primary.records == primary_before
    assert fallback.records == fallback_before
    assert (len(primary.writes), len(fallback.writes)) == writes


@pytest.mark.parametrize("write_fails", [True, False])
def test_auto_completion_never_writes_fallback(
    monkeypatch: pytest.MonkeyPatch, write_fails: bool
) -> None:
    primary = MemoryRunnerStorage()
    fallback = MemoryRunnerStorage()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    should_dispatch(42, "aaa", "codex", storage=primary)
    pending = dict(primary.records[(42, "codex")])
    storage = runner_core.FallbackRunnerStorage(primary, fallback)
    # A reused adapter's prior fallback selection must not redirect completion.
    storage._use_fallback = True
    if write_fails:

        def fail_write(*_: Any) -> None:
            raise RuntimeError("primary unavailable")

        monkeypatch.setattr(primary, "write_record", fail_write)
    result = record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )
    assert not fallback.writes
    if write_fails:
        assert result["completion_recorded"] is False
        assert result["completion_reason"] == "authoritative-storage-unavailable"
        assert primary.records[(42, "codex")] == pending
        assert len(primary.writes) == 1
    else:
        assert result["status"] == "completed"
        assert primary.records[(42, "codex")] == result
        assert len(primary.writes) == 2


@pytest.mark.parametrize("operation", ["read", "write"])
@pytest.mark.parametrize("failure", ["http", "network", "other"])
def test_auto_completion_logs_safe_storage_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: str,
    failure: str,
) -> None:
    primary = MemoryRunnerStorage()
    fallback = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=primary)
    pending = dict(primary.records[(42, "codex")])
    secret = "private-response-and-token"
    cause: Exception
    if failure == "http":
        cause = HTTPError("https://example.invalid/" + secret, 403, secret, {}, None)
    elif failure == "network":
        cause = URLError(secret)
    else:
        cause = ValueError(secret)

    def fail(*_: Any) -> Any:
        raise RuntimeError(secret) from cause

    monkeypatch.setattr(primary, f"{operation}_record", fail)
    result = record_completion(
        42,
        "aaa",
        "codex",
        _unproductive_result(),
        storage=runner_core.FallbackRunnerStorage(primary, fallback),
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"authoritative completion {operation} failed" in captured.err
    assert "error_type=RuntimeError" in captured.err
    assert f"cause_type={type(cause).__name__}" in captured.err
    assert f"http_status={'403' if failure == 'http' else 'unknown'}" in captured.err
    assert secret not in captured.err
    assert "https://" not in captured.err
    assert result["completion_recorded"] is False
    assert result["completion_reason"] == "authoritative-storage-unavailable"
    assert primary.records[(42, "codex")] == pending
    assert len(primary.writes) == 1
    assert not fallback.writes


@pytest.mark.parametrize("operation", ["read", "write"])
def test_single_store_completion_errors_still_propagate(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    error = RuntimeError("single-store failure")

    def fail(*_: Any) -> Any:
        raise error

    monkeypatch.setattr(storage, f"{operation}_record", fail)
    with pytest.raises(RuntimeError) as caught:
        record_completion(42, "aaa", "codex", _unproductive_result(), storage=storage)
    assert caught.value is error
    assert len(storage.writes) == 1


def test_missing_workflow_identity_cannot_complete_bound_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = MemoryRunnerStorage()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    should_dispatch(42, "aaa", "codex", storage=storage)
    writes = len(storage.writes)
    monkeypatch.delenv("GITHUB_RUN_ID")
    result = record_completion(42, "aaa", "codex", _unproductive_result(), storage=storage)
    assert result["completion_recorded"] is False
    assert len(storage.writes) == writes


def test_cli_reports_stale_completion_without_writing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    storage = MemoryRunnerStorage()
    monkeypatch.setattr(runner_core, "_storage_from_name", lambda _: storage)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "200")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    common = ["--provider", "codex", "--pr-number", "42", "--head-sha", "aaa"]
    assert runner_core.main(["should-dispatch", *common]) == 0
    capsys.readouterr()
    writes = len(storage.writes)
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    assert runner_core.main(["record-completion", *common, "--summary", "Done"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["recorded"] == "false"
    assert output["reason"] == "stale-attempt"
    assert len(storage.writes) == writes


def test_cli_unrecorded_completion_reports_current_key_and_unknown_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    storage = MemoryRunnerStorage()
    monkeypatch.setattr(runner_core, "_storage_from_name", lambda _: storage)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "200")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    common = ["--provider", "codex", "--pr-number", "42"]
    assert runner_core.main(["should-dispatch", *common, "--head-sha", "aaa"]) == 0
    capsys.readouterr()
    writes = len(storage.writes)

    assert (
        runner_core.main(["record-completion", *common, "--head-sha", "bbb", "--summary", "Done"])
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "key": runner_core._runner_key(42, "bbb", "codex"),
        "productive": "",
        "reason": "stale-attempt",
        "recorded": "false",
        "status": "unknown",
    }
    assert len(storage.writes) == writes


def test_same_attempt_completion_across_jobs_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = MemoryRunnerStorage()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_JOB", "reserve")
    should_dispatch(42, "aaa", "codex", storage=storage)
    monkeypatch.setenv("GITHUB_JOB", "complete")
    first = record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )
    second = record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )
    assert first == second
    assert second["status"] == "completed"
    assert second["unproductive_completions"] == 1


def test_unmeasured_retry_preserves_bounded_unproductive_streak() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )
    for _ in range(UNPRODUCTIVE_COMPLETION_RETRY_LIMIT):
        assert should_dispatch(42, "aaa", "codex", storage=storage).should_dispatch
        record_completion(42, "aaa", "codex", _unproductive_result(), storage=storage)
    assert storage.records[(42, "codex")]["productive"] is False
    assert should_dispatch(42, "aaa", "codex", storage=storage).reason == "unproductive-cooldown"


def test_new_head_does_not_inherit_unproductive_classification() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )
    should_dispatch(42, "bbb", "codex", storage=storage)
    record_completion(42, "bbb", "codex", _unproductive_result(), storage=storage)
    assert "productive" not in storage.records[(42, "codex")]
    assert should_dispatch(42, "bbb", "codex", storage=storage).reason == "duplicate-completed"


def _unproductive_result() -> RunnerResult:
    """A run that exits 0 having done nothing — the shape the codex sandbox failure takes."""
    return RunnerResult(
        provider="codex",
        success=True,
        final_message="bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted",
        summary="Blocked by the execution environment. No files changed, no commits created.",
    )


def test_unproductive_completion_is_retried_on_the_same_head() -> None:
    """The #3433 deadlock: a zero-output run must not burn the head's dispatch key.

    Clearing a `duplicate-completed` refusal requires a new head commit, and only the agent
    being refused could push one — so refusing forever on an unproductive completion means the
    gate can only be opened by the action it forbids.
    """
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )

    decision = should_dispatch(42, "aaa", "codex", storage=storage)

    assert decision.should_dispatch is True
    assert decision.reason == "retry-unproductive-completion"


def test_unproductive_retries_expire_into_a_cooldown_not_a_latch() -> None:
    """Spent retries must expire into a WAIT, never into "only a new head commit will do".

    Refusing until the head changes would reinstate the original #3433 deadlock one step
    further out, because only the agent being refused could push that commit. A cooldown is
    cleared by time alone, which the hourly keepalive sweep then wakes.
    """
    storage = MemoryRunnerStorage()
    for _ in range(UNPRODUCTIVE_COMPLETION_RETRY_LIMIT + 1):
        should_dispatch(42, "aaa", "codex", storage=storage)
        record_completion(
            42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
        )

    cooling = should_dispatch(42, "aaa", "codex", storage=storage)

    assert cooling.should_dispatch is False
    assert cooling.reason == "unproductive-cooldown"
    assert "time: retry at" in cooling.drainable
    # The drainable path must be time, not an action the refused agent alone could take.
    assert "head commit" not in cooling.drainable


def test_dispatch_resumes_once_the_cooldown_has_elapsed() -> None:
    storage = MemoryRunnerStorage()
    for _ in range(UNPRODUCTIVE_COMPLETION_RETRY_LIMIT + 1):
        should_dispatch(42, "aaa", "codex", storage=storage)
        record_completion(
            42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
        )
    assert should_dispatch(42, "aaa", "codex", storage=storage).should_dispatch is False

    stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        seconds=UNPRODUCTIVE_COMPLETION_COOLDOWN_SECONDS + 60
    )
    record = storage.records[(42, "codex")]
    record["status"] = "completed"
    record["completed_at"] = stale.isoformat().replace("+00:00", "Z")

    resumed = should_dispatch(42, "aaa", "codex", storage=storage)

    assert resumed.should_dispatch is True
    assert resumed.reason == "retry-after-unproductive-cooldown"


def test_unmeasurable_cooldown_fails_toward_motion() -> None:
    """A gate that cannot measure itself must not stay shut on that basis."""
    storage = MemoryRunnerStorage()
    for _ in range(UNPRODUCTIVE_COMPLETION_RETRY_LIMIT + 1):
        should_dispatch(42, "aaa", "codex", storage=storage)
        record_completion(
            42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
        )
    record = storage.records[(42, "codex")]
    record["status"] = "completed"
    record["completed_at"] = "not-a-timestamp"

    decision = should_dispatch(42, "aaa", "codex", storage=storage)

    assert decision.should_dispatch is True


def test_productive_completion_still_burns_the_head_key() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    record_completion(
        42,
        "aaa",
        "codex",
        parse_runner_output("codex", "Done"),
        storage=storage,
        produced_work=True,
    )

    decision = should_dispatch(42, "aaa", "codex", storage=storage)

    assert decision.should_dispatch is False
    assert decision.reason == "duplicate-completed"
    assert decision.drainable == "a new head commit"


def test_unmeasured_completion_keeps_pre_3433_behavior() -> None:
    """No productivity verdict means unmeasured, which must stay terminal.

    Callers that have not been taught to measure (autofix) must not silently get a looser
    debounce as a side effect of this fix.
    """
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    record_completion(42, "aaa", "codex", _unproductive_result(), storage=storage)

    decision = should_dispatch(42, "aaa", "codex", storage=storage)

    assert decision.should_dispatch is False
    assert decision.reason == "duplicate-completed"


def test_productive_run_resets_the_unproductive_tally() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )
    should_dispatch(42, "aaa", "codex", storage=storage)
    record_completion(
        42,
        "bbb",
        "codex",
        parse_runner_output("codex", "Done"),
        storage=storage,
        produced_work=True,
    )

    assert storage.records[(42, "codex")]["unproductive_completions"] == 0


def test_pending_refusal_names_its_drainable_quantity() -> None:
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)

    decision = should_dispatch(42, "aaa", "codex", storage=storage)

    assert decision.should_dispatch is False
    assert decision.reason == "duplicate-pending"
    assert "ageing past" in decision.drainable


def test_granted_dispatch_reports_no_drainable_quantity() -> None:
    """The drained rendering must be reachable: an unblocked decision prints an empty string.

    A field that only ever renders a blocked state is the reporting half of a latched gate.
    """
    storage = MemoryRunnerStorage()

    assert should_dispatch(42, "aaa", "codex", storage=storage).drainable == ""


def test_rerunning_the_completion_job_does_not_spend_another_retry() -> None:
    """record_completion is idempotent for a dispatch key, tally included.

    The completion job can re-run for the same key without any additional agent run having
    happened; a counter that advanced on a rerun would quietly exhaust the retry allowance.
    """
    storage = MemoryRunnerStorage()
    should_dispatch(42, "aaa", "codex", storage=storage)
    record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )
    record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )

    assert storage.records[(42, "codex")]["unproductive_completions"] == 1
    assert should_dispatch(42, "aaa", "codex", storage=storage).should_dispatch is True


def test_each_zero_output_run_after_the_cooldown_arms_a_fresh_one() -> None:
    """Expiry must re-arm, not latch open — and the tally must stay capped while it does.

    Without this, two regressions look identical to the expiry test: a tally that keeps
    climbing (so the cooldown is measured from an ever-staler completion), and an expired
    window that never closes again (so a permanently broken runner is re-dispatched forever).
    """
    storage = MemoryRunnerStorage()
    for _ in range(UNPRODUCTIVE_COMPLETION_RETRY_LIMIT + 1):
        should_dispatch(42, "aaa", "codex", storage=storage)
        record_completion(
            42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
        )

    stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        seconds=UNPRODUCTIVE_COMPLETION_COOLDOWN_SECONDS + 60
    )
    record = storage.records[(42, "codex")]
    record["status"] = "completed"
    record["completed_at"] = stale.isoformat().replace("+00:00", "Z")

    assert should_dispatch(42, "aaa", "codex", storage=storage).should_dispatch is True

    # The retry produces nothing either. That must start a NEW cooldown from now.
    record_completion(
        42, "aaa", "codex", _unproductive_result(), storage=storage, produced_work=False
    )
    rearmed = should_dispatch(42, "aaa", "codex", storage=storage)

    assert rearmed.should_dispatch is False
    assert rearmed.reason == "unproductive-cooldown"
    # The tally is capped, so the window is measured from the newest completion rather than
    # from a completion that keeps receding into the past.
    assert (
        storage.records[(42, "codex")]["unproductive_completions"]
        == UNPRODUCTIVE_COMPLETION_RETRY_LIMIT + 1
    )
