from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import model_profile_trial_contract as contract

PINNED_REF = "stranske/Workflows/.github/workflows/reusable-model-profile-trial.yml@" + ("1" * 40)


def _registries():
    registry = {
        "model_profile_trial_contract": {
            "mode": "read-only",
            "artifact_schema": contract.ARTIFACT_SCHEMA,
            "identity_authority": contract.IDENTITY_AUTHORITY,
            "collector_identity_authority": contract.COLLECTOR_IDENTITY_AUTHORITY,
            "runner_ref": PINNED_REF,
            "cli_version": contract.EXPECTED_CLI_VERSION,
            "runtime_fallback_allowed": False,
            "auxiliary_evaluator_allowed": False,
        },
        "execution_profiles": {},
    }
    models = {"models": []}
    for profile_id, model in contract.EXPECTED_PROFILES.items():
        registry["execution_profiles"][profile_id] = {
            "agent": "codex",
            "model": model,
            "fallback_model": "gpt-5.5",
            "runner": "reusable-model-profile-trial",
            "runner_ref": PINNED_REF,
            "capacity_pool": "codex-standard",
            "safety": "read-only",
            "lifecycle": "trial",
            "reasoning_effort": "high",
            "permission_mode": "read-only",
        }
        models["models"].append(
            {
                "model_id": model,
                "provider": "openai",
                "worker_profile": True,
                "lifecycle": "trial",
            }
        )
    return registry, models


def _session(tmp_path: Path, *, model: str = "gpt-5.6-sol", effort: str = "high"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    thread_id = "019f-trial-thread"
    stream = tmp_path / "stream.jsonl"
    stream.write_text(json.dumps({"type": "thread.started", "thread_id": thread_id}) + "\n")
    codex_home = tmp_path / "codex-home"
    rollout = codex_home / "sessions" / "2026" / "07" / "10" / "rollout.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_meta", "payload": {"id": thread_id}}),
                json.dumps(
                    {
                        "type": "turn_context",
                        "payload": {"model": model, "effort": effort},
                    }
                ),
            ]
        )
        + "\n"
    )
    return stream, codex_home, thread_id


def _artifact(tmp_path: Path, **overrides):
    packet_hash = "sha256:" + "a" * 64
    source_sha = "b" * 40
    stream, codex_home, _thread_id = _session(
        tmp_path,
        model=overrides.pop("reported_model", "gpt-5.6-sol"),
        effort=overrides.pop("reported_effort", "high"),
    )
    final_message = tmp_path / "final.txt"
    final_message.write_text(
        f"packet_hash={packet_hash} source_sha={source_sha} "
        "profile_id=codex-5.6-sol-high trial_run_id=trial-run:one\n"
    )
    values = {
        "trial_id": "trial:canary",
        "request_id": "trial-request:one",
        "request_hash": "sha256:" + "c" * 64,
        "trial_run_id": "trial-run:one",
        "profile_id": "codex-5.6-sol-high",
        "launch_ordinal": 2,
        "packet_hash": packet_hash,
        "expected_source_sha": source_sha,
        "source_sha_before": source_sha,
        "source_sha_after": source_sha,
        "source_manifest_sha256_before": "sha256:" + "d" * 64,
        "source_manifest_sha256_after": "sha256:" + "d" * 64,
        "requested_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high",
        "runner_version": PINNED_REF,
        "cli_version": "codex-cli 0.153.2",
        "session_stream": stream,
        "codex_home": codex_home,
        "final_message": final_message,
        "exit_code": 0,
        "source_clean": True,
        "github_repository": contract.EXPECTED_REPOSITORY,
        "github_workflow_ref": contract.EXPECTED_WORKFLOW_REF,
        "github_workflow_sha": source_sha,
        "github_run_id": 12345,
        "github_run_attempt": 2,
        "artifact_name": "model-trial-12345-2",
    }
    values.update(overrides)
    return contract.build_artifact(**values)


def test_resolve_profile_requires_exact_read_only_pinned_contract():
    registry, models = _registries()
    resolved = contract.resolve_profile(registry, models, "codex-5.6-terra-high")
    assert resolved == {
        "profile_id": "codex-5.6-terra-high",
        "model": "gpt-5.6-terra",
        "reasoning_effort": "high",
        "permission_mode": "read-only",
        "capacity_pool": "codex-standard",
        "runner_ref": PINNED_REF,
        "identity_authority": contract.IDENTITY_AUTHORITY,
    }

    registry["execution_profiles"]["codex-5.6-terra-high"]["permission_mode"] = "workspace-write"
    with pytest.raises(contract.ContractError, match="permission_mode mismatch"):
        contract.resolve_profile(registry, models, "codex-5.6-terra-high")


def test_success_artifact_uses_session_turn_context_and_keeps_provider_null(tmp_path):
    artifact = _artifact(tmp_path)
    assert set(artifact) == contract.ARTIFACT_FIELDS
    assert artifact["status"] == "success"
    assert artifact["reported_model"] == "gpt-5.6-sol"
    assert artifact["provider_resolved_provider"] is None
    assert artifact["provider_resolved_model"] is None
    assert artifact["fallback_reason"] is None
    assert artifact["thread_id"] == "019f-trial-thread"
    assert artifact["source_sha_before"] == artifact["source_sha_after"]
    assert artifact["source_manifest_sha256_before"] == artifact["source_manifest_sha256_after"]
    assert artifact["launch_ordinal"] == 2
    assert artifact["version"] == 2
    assert artifact["requested_reasoning_effort"] == "high"
    assert artifact["reported_reasoning_effort"] == "high"
    assert artifact["github_workflow_ref"] == contract.EXPECTED_WORKFLOW_REF


def test_artifact_fails_closed_on_model_effort_or_source_drift(tmp_path):
    mismatch = _artifact(tmp_path / "model", reported_model="gpt-5.5")
    assert mismatch["status"] == "failed"
    assert mismatch["fallback_reason"] == "reported_model_mismatch"

    effort = _artifact(tmp_path / "effort", reported_effort="medium")
    assert effort["status"] == "failed"
    assert effort["fallback_reason"] == "reported_reasoning_effort_mismatch"

    source = _artifact(tmp_path / "source", source_sha_after="d" * 40)
    assert source["status"] == "failed"
    assert source["fallback_reason"] == "source_sha_changed"

    manifest = _artifact(
        tmp_path / "manifest",
        source_manifest_sha256_after="sha256:" + "e" * 64,
    )
    assert manifest["status"] == "failed"
    assert manifest["fallback_reason"] == "source_manifest_changed"


def test_thread_identity_must_come_from_exact_matching_rollout(tmp_path):
    artifact = _artifact(tmp_path)
    assert artifact["reported_model"] == "gpt-5.6-sol"
    rollout = next((tmp_path / "codex-home" / "sessions").glob("**/*.jsonl"))
    rollout.write_text(
        json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "high"}})
        + "\n"
    )
    packet_hash = "sha256:" + "a" * 64
    source_sha = "b" * 40
    final_message = tmp_path / "final.txt"
    final_message.write_text(
        f"packet_hash={packet_hash} source_sha={source_sha} "
        "profile_id=codex-5.6-sol-high trial_run_id=trial-run:one\n"
    )
    broken = contract.build_artifact(
        trial_id="trial:canary",
        request_id="trial-request:one",
        request_hash="sha256:" + "c" * 64,
        trial_run_id="trial-run:one",
        profile_id="codex-5.6-sol-high",
        launch_ordinal=1,
        packet_hash=packet_hash,
        expected_source_sha=source_sha,
        source_sha_before=source_sha,
        source_sha_after=source_sha,
        source_manifest_sha256_before="sha256:" + "d" * 64,
        source_manifest_sha256_after="sha256:" + "d" * 64,
        requested_model="gpt-5.6-sol",
        requested_reasoning_effort="high",
        runner_version=PINNED_REF,
        cli_version="codex-cli 0.153.2",
        session_stream=tmp_path / "stream.jsonl",
        codex_home=tmp_path / "codex-home",
        final_message=final_message,
        exit_code=0,
        source_clean=True,
        github_repository=contract.EXPECTED_REPOSITORY,
        github_workflow_ref=contract.EXPECTED_WORKFLOW_REF,
        github_workflow_sha=source_sha,
        github_run_id=12345,
        github_run_attempt=1,
        artifact_name="model-trial-12345-1",
    )
    assert broken["reported_model"] is None
    assert broken["fallback_reason"] == "reported_model_missing"


def test_failed_cli_with_malformed_stream_still_emits_failure_artifact(tmp_path):
    packet_hash = "sha256:" + "a" * 64
    source_sha = "b" * 40
    stream = tmp_path / "broken-stream.jsonl"
    stream.write_text("not-json\n")
    final_message = tmp_path / "final.txt"
    final_message.write_text("")
    artifact = contract.build_artifact(
        trial_id="trial:canary",
        request_id="trial-request:one",
        request_hash="sha256:" + "c" * 64,
        trial_run_id="trial-run:one",
        profile_id="codex-5.6-sol-high",
        launch_ordinal=1,
        packet_hash=packet_hash,
        expected_source_sha=source_sha,
        source_sha_before=source_sha,
        source_sha_after=source_sha,
        source_manifest_sha256_before="sha256:" + "d" * 64,
        source_manifest_sha256_after="sha256:" + "d" * 64,
        requested_model="gpt-5.6-sol",
        requested_reasoning_effort="high",
        runner_version=PINNED_REF,
        cli_version="codex-cli 0.153.2",
        session_stream=stream,
        codex_home=tmp_path / "codex-home",
        final_message=final_message,
        exit_code=1,
        source_clean=True,
        github_repository=contract.EXPECTED_REPOSITORY,
        github_workflow_ref=contract.EXPECTED_WORKFLOW_REF,
        github_workflow_sha=source_sha,
        github_run_id=12345,
        github_run_attempt=1,
        artifact_name="model-trial-12345-1",
    )
    assert artifact["status"] == "failed"
    assert artifact["fallback_reason"] == "codex_cli_failed"
    assert set(artifact) == contract.ARTIFACT_FIELDS


def test_artifact_rejects_non_authoritative_github_provenance(tmp_path):
    with pytest.raises(contract.ContractError, match="github_workflow_ref"):
        _artifact(
            tmp_path,
            github_workflow_ref=(
                "stranske/Workflows/.github/workflows/agents-model-profile-trial.yml@refs/pull/1/merge"
            ),
        )


def test_source_manifest_is_stable_and_detects_ignored_file_changes(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    ignored = checkout / ".trial-local"
    ignored.write_text("before\n", encoding="utf-8")

    before = contract.source_manifest(checkout)
    assert before["file_count"] == 2
    assert before == contract.source_manifest(checkout)

    ignored.write_text("after\n", encoding="utf-8")
    after = contract.source_manifest(checkout)
    assert before["aggregate_sha256"] != after["aggregate_sha256"]


def test_live_catalog_and_execution_registry_resolve_every_trial_arm():
    import yaml

    root = Path(__file__).resolve().parents[2]
    registry = yaml.safe_load((root / ".github/agents/registry.yml").read_text())
    models = json.loads((root / "config/model_registry.json").read_text())
    for profile_id, expected_model in contract.EXPECTED_PROFILES.items():
        result = contract.resolve_profile(registry, models, profile_id)
        assert result["model"] == expected_model
        assert result["permission_mode"] == "read-only"
