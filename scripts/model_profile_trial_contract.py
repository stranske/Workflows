#!/usr/bin/env python3
"""Validate and emit the read-only Codex model-profile trial contract.

This helper is intentionally deterministic.  It resolves a single registry
profile before provider execution and turns Codex's own persisted session
``turn_context`` into a strict, quarantine-only attempt artifact afterwards.
It does not call a provider, score an answer, write GitHub state, or infer
provider-resolved identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

ARTIFACT_SCHEMA = "workflows.model-profile-trial-result/v2"
IDENTITY_AUTHORITY = "workflows-read-only-trial-artifact/v2"
COLLECTOR_IDENTITY_AUTHORITY = "github-actions-api/workflows-read-only-trial-artifact/v2"
EXPECTED_CLI_VERSION = "0.144.1"
EXPECTED_REPOSITORY = "stranske/Workflows"
EXPECTED_WORKFLOW_REF = (
    "stranske/Workflows/.github/workflows/agents-model-profile-trial.yml@refs/heads/main"
)
MAX_SOURCE_FILES = 20_000
MAX_SOURCE_BYTES = 200 * 1024 * 1024
SOURCE_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
EXPECTED_PROFILES = {
    "codex-6-astra-high": "gpt-6-astra",
    "codex-5.6-sol-high": "gpt-5.6-sol",
    "codex-5.6-terra-high": "gpt-5.6-terra",
    "codex-5.6-luna-high": "gpt-5.6-luna",
}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PINNED_RUNNER_RE = re.compile(
    r"^stranske/Workflows/\.github/workflows/" r"reusable-model-profile-trial\.yml@[0-9a-f]{40}$"
)
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,200}$")

ARTIFACT_FIELDS = {
    "schema",
    "version",
    "trial_id",
    "request_id",
    "request_hash",
    "run_id",
    "profile_id",
    "launch_ordinal",
    "packet_hash",
    "acknowledged",
    "status",
    "requested_model",
    "selected_model",
    "reported_model",
    "provider_resolved_provider",
    "provider_resolved_model",
    "fallback_reason",
    "identity_authority",
    "operation_role",
    "runner_version",
    "cli_version",
    "thread_id",
    "requested_reasoning_effort",
    "reported_reasoning_effort",
    "source_sha_before",
    "source_sha_after",
    "source_manifest_sha256_before",
    "source_manifest_sha256_after",
    "source_clean",
    "exit_code",
    "github_repository",
    "github_workflow_ref",
    "github_workflow_sha",
    "github_run_id",
    "github_run_attempt",
    "artifact_name",
}


class ContractError(ValueError):
    """The frozen trial contract was missing, malformed, or inconsistent."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"unable to read strict JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"JSON root must be an object: {path}")
    return value


def _require_safe_id(label: str, value: str) -> str:
    text = str(value or "").strip()
    if not SAFE_ID_RE.fullmatch(text):
        raise ContractError(f"{label} must be a bounded stable identifier")
    return text


def _require_hash(label: str, value: str) -> str:
    text = str(value or "").strip()
    if not SHA256_RE.fullmatch(text):
        raise ContractError(f"{label} must be sha256:<64 lowercase hex>")
    return text


def _require_source_sha(label: str, value: str) -> str:
    text = str(value or "").strip()
    if not SOURCE_SHA_RE.fullmatch(text):
        raise ContractError(f"{label} must be a full lowercase Git SHA")
    return text


def _require_positive_int(label: str, value: int | str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise ContractError(f"{label} must be a positive integer")
    return parsed


def source_manifest(root: Path) -> dict[str, Any]:
    """Hash a bounded checkout without following symlinks or reading Git metadata."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ContractError(f"source manifest root is not a directory: {root}")
    rows: list[dict[str, Any]] = []
    total_bytes = 0
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in SOURCE_SKIP_DIRS)
        base = Path(current)
        for name in sorted(files):
            path = base / name
            rel = path.relative_to(root).as_posix()
            if len(rows) >= MAX_SOURCE_FILES:
                raise ContractError("source manifest file limit exceeded")
            if path.is_symlink():
                target = os.readlink(path)
                payload = target.encode("utf-8", errors="surrogateescape")
                kind = "symlink"
            elif path.is_file():
                size = path.stat().st_size
                if total_bytes + size > MAX_SOURCE_BYTES:
                    raise ContractError("source manifest byte limit exceeded")
                payload = path.read_bytes()
                total_bytes += size
                kind = "file"
            else:
                continue
            rows.append(
                {
                    "path": rel,
                    "kind": kind,
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema": "workflows.source-manifest/v1",
        "version": 1,
        "file_count": len(rows),
        "total_bytes": total_bytes,
        "aggregate_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def resolve_profile(
    registry: dict[str, Any], model_registry: dict[str, Any], profile_id: str
) -> dict[str, Any]:
    """Return the exact single-arm execution contract or fail closed."""
    profile_id = _require_safe_id("profile_id", profile_id)
    expected_model = EXPECTED_PROFILES.get(profile_id)
    if expected_model is None:
        raise ContractError(f"profile_id is not a Sol/Terra/Luna trial profile: {profile_id}")

    profiles = registry.get("execution_profiles")
    if not isinstance(profiles, dict) or not isinstance(profiles.get(profile_id), dict):
        raise ContractError(f"execution profile missing from registry: {profile_id}")
    profile = dict(profiles[profile_id])
    contract = registry.get("model_profile_trial_contract")
    if not isinstance(contract, dict):
        raise ContractError("model_profile_trial_contract missing from registry")

    expected_profile = {
        "agent": "codex",
        "model": expected_model,
        "fallback_model": "gpt-5.5",
        "runner": "reusable-model-profile-trial",
        "capacity_pool": "codex-standard",
        "safety": "read-only",
        "lifecycle": "trial",
        "reasoning_effort": "high",
        "permission_mode": "read-only",
    }
    for field, expected in expected_profile.items():
        if profile.get(field) != expected:
            raise ContractError(
                f"execution profile {profile_id} {field} mismatch: " f"expected {expected!r}"
            )

    expected_contract = {
        "mode": "read-only",
        "artifact_schema": ARTIFACT_SCHEMA,
        "identity_authority": IDENTITY_AUTHORITY,
        "collector_identity_authority": COLLECTOR_IDENTITY_AUTHORITY,
        "cli_version": EXPECTED_CLI_VERSION,
        "runtime_fallback_allowed": False,
        "auxiliary_evaluator_allowed": False,
    }
    for field, expected in expected_contract.items():
        if contract.get(field) != expected:
            raise ContractError(f"trial contract {field} mismatch: expected {expected!r}")

    runner_ref = str(contract.get("runner_ref") or "")
    if not PINNED_RUNNER_RE.fullmatch(runner_ref):
        raise ContractError("trial contract runner_ref is not this immutable reusable workflow")
    if profile.get("runner_ref") != runner_ref:
        raise ContractError(f"execution profile {profile_id} runner_ref drifted")

    models = model_registry.get("models")
    if not isinstance(models, list):
        raise ContractError("model registry missing models array")
    matches = [
        row for row in models if isinstance(row, dict) and row.get("model_id") == expected_model
    ]
    if len(matches) != 1:
        raise ContractError(f"model registry must contain one exact row for {expected_model}")
    model = matches[0]
    if model.get("provider") != "openai":
        raise ContractError(f"model registry provider mismatch for {expected_model}")
    if model.get("worker_profile") is not True or model.get("lifecycle") != "trial":
        raise ContractError(f"model registry trial-worker metadata mismatch for {expected_model}")

    return {
        "profile_id": profile_id,
        "model": expected_model,
        "reasoning_effort": "high",
        "permission_mode": "read-only",
        "capacity_pool": "codex-standard",
        "runner_ref": runner_ref,
        "identity_authority": IDENTITY_AUTHORITY,
    }


def _iter_jsonl(path: Path):
    if not path.is_file():
        return
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContractError(f"invalid JSONL at {path}:{line_number}") from exc
        if isinstance(value, dict):
            yield value


def extract_thread_id(session_stream: Path) -> str | None:
    values = {
        str(event.get("thread_id"))
        for event in _iter_jsonl(session_stream) or ()
        if event.get("type") == "thread.started" and event.get("thread_id")
    }
    if len(values) > 1:
        raise ContractError("Codex stream contains multiple thread ids")
    return next(iter(values), None)


def extract_reported_identity(
    codex_home: Path, thread_id: str | None
) -> tuple[str | None, str | None]:
    """Read model and effort only from the matching persisted turn_context."""
    if not thread_id:
        return None, None
    matching_files: list[Path] = []
    for path in sorted((codex_home / "sessions").glob("**/*.jsonl")):
        for event in _iter_jsonl(path) or ():
            payload = event.get("payload") if event.get("type") == "session_meta" else None
            if isinstance(payload, dict) and payload.get("id") == thread_id:
                matching_files.append(path)
                break
    if len(matching_files) != 1:
        return None, None

    models: set[str] = set()
    efforts: set[str] = set()
    for event in _iter_jsonl(matching_files[0]) or ():
        if event.get("type") != "turn_context" or not isinstance(event.get("payload"), dict):
            continue
        payload = event["payload"]
        if payload.get("model"):
            models.add(str(payload["model"]))
        effort = payload.get("effort")
        if not effort:
            settings = (payload.get("collaboration_mode") or {}).get("settings") or {}
            effort = settings.get("reasoning_effort")
        if effort:
            efforts.add(str(effort))
    if len(models) != 1 or len(efforts) != 1:
        return None, None
    return next(iter(models)), next(iter(efforts))


def _cli_version_number(cli_version: str) -> str | None:
    match = re.search(r"(?:^|\s)(\d+\.\d+\.\d+)(?:\s|$)", str(cli_version or ""))
    return match.group(1) if match else None


def build_artifact(
    *,
    trial_id: str,
    request_id: str,
    request_hash: str,
    trial_run_id: str,
    profile_id: str,
    launch_ordinal: int,
    packet_hash: str,
    expected_source_sha: str,
    source_sha_before: str,
    source_sha_after: str,
    source_manifest_sha256_before: str,
    source_manifest_sha256_after: str,
    requested_model: str,
    requested_reasoning_effort: str,
    runner_version: str,
    cli_version: str,
    session_stream: Path,
    codex_home: Path,
    final_message: Path,
    exit_code: int,
    source_clean: bool,
    github_repository: str,
    github_workflow_ref: str,
    github_workflow_sha: str,
    github_run_id: int,
    github_run_attempt: int,
    artifact_name: str,
) -> dict[str, Any]:
    """Build one strict attempt artifact, including failed canaries."""
    trial_id = _require_safe_id("trial_id", trial_id)
    request_id = _require_safe_id("request_id", request_id)
    trial_run_id = _require_safe_id("trial_run_id", trial_run_id)
    profile_id = _require_safe_id("profile_id", profile_id)
    request_hash = _require_hash("request_hash", request_hash)
    packet_hash = _require_hash("packet_hash", packet_hash)
    expected_source_sha = _require_source_sha("expected_source_sha", expected_source_sha)
    source_sha_before = _require_source_sha("source_sha_before", source_sha_before)
    source_sha_after = _require_source_sha("source_sha_after", source_sha_after)
    source_manifest_sha256_before = _require_hash(
        "source_manifest_sha256_before", source_manifest_sha256_before
    )
    source_manifest_sha256_after = _require_hash(
        "source_manifest_sha256_after", source_manifest_sha256_after
    )
    if profile_id not in EXPECTED_PROFILES or requested_model != EXPECTED_PROFILES[profile_id]:
        raise ContractError("requested model does not match the exact profile")
    if not 1 <= int(launch_ordinal) <= 3:
        raise ContractError("launch_ordinal must be between 1 and 3")
    if not PINNED_RUNNER_RE.fullmatch(runner_version):
        raise ContractError("runner_version is not an immutable reusable trial workflow")
    if requested_reasoning_effort != "high":
        raise ContractError("requested_reasoning_effort must be high")
    if github_repository != EXPECTED_REPOSITORY:
        raise ContractError("github_repository is not the authoritative Workflows repo")
    github_workflow_sha = _require_source_sha("github_workflow_sha", github_workflow_sha)
    github_run_id = _require_positive_int("github_run_id", github_run_id)
    github_run_attempt = _require_positive_int("github_run_attempt", github_run_attempt)
    if github_workflow_ref != EXPECTED_WORKFLOW_REF:
        raise ContractError("github_workflow_ref is not the authoritative main-branch shim")
    artifact_name = _require_safe_id("artifact_name", artifact_name)

    identity_parse_failed = False
    try:
        thread_id = extract_thread_id(session_stream)
        reported_model, reported_effort = extract_reported_identity(codex_home, thread_id)
    except (ContractError, OSError, UnicodeDecodeError):
        # Provider/CLI failures may leave a partial stream. Preserve a strict
        # failure artifact instead of losing the attempt to parser noise.
        identity_parse_failed = True
        thread_id = None
        reported_model = None
        reported_effort = None
    final_text = final_message.read_text(encoding="utf-8") if final_message.is_file() else ""
    acknowledgement_tokens = (
        f"packet_hash={packet_hash}",
        f"source_sha={expected_source_sha}",
        f"profile_id={profile_id}",
        f"trial_run_id={trial_run_id}",
    )
    acknowledged = all(token in final_text for token in acknowledgement_tokens)

    failures: list[str] = []
    if exit_code != 0:
        failures.append("codex_cli_failed")
    if identity_parse_failed:
        failures.append("session_identity_invalid")
    if _cli_version_number(cli_version) != EXPECTED_CLI_VERSION:
        failures.append("cli_version_mismatch")
    if source_sha_before != expected_source_sha:
        failures.append("source_sha_before_mismatch")
    if source_sha_after != expected_source_sha or source_sha_after != source_sha_before:
        failures.append("source_sha_changed")
    if not source_clean:
        failures.append("source_tree_changed")
    if source_manifest_sha256_after != source_manifest_sha256_before:
        failures.append("source_manifest_changed")
    if not acknowledged:
        failures.append("packet_not_acknowledged")
    if not thread_id:
        failures.append("thread_id_missing")
    if not reported_model:
        failures.append("reported_model_missing")
    elif reported_model != requested_model:
        failures.append("reported_model_mismatch")
    if not reported_effort:
        failures.append("reported_reasoning_effort_missing")
    elif reported_effort != "high":
        failures.append("reported_reasoning_effort_mismatch")

    fallback_reason = failures[0] if failures else None
    artifact = {
        "schema": ARTIFACT_SCHEMA,
        "version": 2,
        "trial_id": trial_id,
        "request_id": request_id,
        "request_hash": request_hash,
        "run_id": trial_run_id,
        "profile_id": profile_id,
        "launch_ordinal": int(launch_ordinal),
        "packet_hash": packet_hash,
        "acknowledged": acknowledged,
        "status": "failed" if failures else "success",
        "requested_model": requested_model,
        "selected_model": requested_model,
        "reported_model": reported_model,
        "provider_resolved_provider": None,
        "provider_resolved_model": None,
        "fallback_reason": fallback_reason,
        "identity_authority": IDENTITY_AUTHORITY,
        "operation_role": "worker",
        "runner_version": runner_version,
        "cli_version": cli_version,
        "thread_id": thread_id,
        "requested_reasoning_effort": requested_reasoning_effort,
        "reported_reasoning_effort": reported_effort,
        "source_sha_before": source_sha_before,
        "source_sha_after": source_sha_after,
        "source_manifest_sha256_before": source_manifest_sha256_before,
        "source_manifest_sha256_after": source_manifest_sha256_after,
        "source_clean": bool(source_clean),
        "exit_code": int(exit_code),
        "github_repository": github_repository,
        "github_workflow_ref": github_workflow_ref,
        "github_workflow_sha": github_workflow_sha,
        "github_run_id": github_run_id,
        "github_run_attempt": github_run_attempt,
        "artifact_name": artifact_name,
    }
    if set(artifact) != ARTIFACT_FIELDS:
        raise AssertionError("strict trial artifact schema drifted")
    return artifact


def _write_github_output(values: dict[str, Any]) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _resolve_command(args: argparse.Namespace) -> int:
    registry = _load_json(Path(args.registry_json))
    models = _load_json(Path(args.model_registry))
    resolved = resolve_profile(registry, models, args.profile_id)
    Path(args.output).write_text(json.dumps(resolved, indent=2, sort_keys=True) + "\n")
    _write_github_output({key.replace("_", "-"): value for key, value in resolved.items()})
    return 0


def _artifact_command(args: argparse.Namespace) -> int:
    artifact = build_artifact(
        trial_id=args.trial_id,
        request_id=args.request_id,
        request_hash=args.request_hash,
        trial_run_id=args.trial_run_id,
        profile_id=args.profile_id,
        launch_ordinal=args.launch_ordinal,
        packet_hash=args.packet_hash,
        expected_source_sha=args.expected_source_sha,
        source_sha_before=args.source_sha_before,
        source_sha_after=args.source_sha_after,
        source_manifest_sha256_before=args.source_manifest_sha256_before,
        source_manifest_sha256_after=args.source_manifest_sha256_after,
        requested_model=args.requested_model,
        requested_reasoning_effort=args.requested_reasoning_effort,
        runner_version=args.runner_version,
        cli_version=args.cli_version,
        session_stream=Path(args.session_stream),
        codex_home=Path(args.codex_home),
        final_message=Path(args.final_message),
        exit_code=args.exit_code,
        source_clean=args.source_clean == "true",
        github_repository=args.github_repository,
        github_workflow_ref=args.github_workflow_ref,
        github_workflow_sha=args.github_workflow_sha,
        github_run_id=args.github_run_id,
        github_run_attempt=args.github_run_attempt,
        artifact_name=args.artifact_name,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    _write_github_output(
        {
            "status": artifact["status"],
            "fallback-reason": artifact["fallback_reason"] or "",
            "thread-id": artifact["thread_id"] or "",
            "reported-model": artifact["reported_model"] or "",
            "artifact-name": artifact["artifact_name"],
        }
    )
    return 0


def _bound_stream_command(args: argparse.Namespace) -> int:
    """Drain stdin while retaining only a bounded diagnostic prefix."""
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    remaining = int(args.max_bytes)
    with output.open("wb") as handle:
        while True:
            chunk = os.sys.stdin.buffer.read(8192)
            if not chunk:
                break
            if remaining > 0:
                retained = chunk[:remaining]
                handle.write(retained)
                remaining -= len(retained)
    return 0


def _source_manifest_command(args: argparse.Namespace) -> int:
    manifest = source_manifest(Path(args.root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_github_output({"aggregate-sha256": manifest["aggregate_sha256"]})
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--registry-json", required=True)
    resolve.add_argument("--model-registry", required=True)
    resolve.add_argument("--profile-id", required=True)
    resolve.add_argument("--output", required=True)
    resolve.set_defaults(func=_resolve_command)

    artifact = subparsers.add_parser("artifact")
    for name in (
        "trial-id",
        "request-id",
        "request-hash",
        "trial-run-id",
        "profile-id",
        "packet-hash",
        "expected-source-sha",
        "source-sha-before",
        "source-sha-after",
        "source-manifest-sha256-before",
        "source-manifest-sha256-after",
        "requested-model",
        "requested-reasoning-effort",
        "runner-version",
        "cli-version",
        "session-stream",
        "codex-home",
        "final-message",
        "source-clean",
        "github-repository",
        "github-workflow-ref",
        "github-workflow-sha",
        "github-run-id",
        "github-run-attempt",
        "artifact-name",
        "output",
    ):
        artifact.add_argument(f"--{name}", required=True)
    artifact.add_argument("--launch-ordinal", required=True, type=int)
    artifact.add_argument("--exit-code", required=True, type=int)
    artifact.set_defaults(func=_artifact_command)

    bound_stream = subparsers.add_parser("bound-stream")
    bound_stream.add_argument("--output", required=True)
    bound_stream.add_argument("--max-bytes", type=int, default=65536)
    bound_stream.set_defaults(func=_bound_stream_command)
    manifest = subparsers.add_parser("source-manifest")
    manifest.add_argument("--root", required=True)
    manifest.add_argument("--output", required=True)
    manifest.set_defaults(func=_source_manifest_command)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        return int(args.func(args))
    except ContractError as exc:
        print(f"model-profile-trial contract error: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
