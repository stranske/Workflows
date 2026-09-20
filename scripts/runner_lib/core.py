"""Shared runner prompt, output parsing, and dispatch debounce utilities."""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import dataclasses
import datetime as dt
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

from scripts.state_fingerprint import GitHubApi, _github_context

MARKER_VERSION = "v1"
MARKER_PREFIX = "runner-dispatch"
PROVIDERS = {"autofix", "claude", "codex", "cursor", "gemini"}
# cursor and gemini use the same plain-text (non-JSONL) prompt/parse path as claude.
PROMPT_PROVIDERS = {"claude", "codex", "cursor", "gemini"}
TERMINAL_STATUSES = {"completed", "error"}
PENDING_STALE_AFTER_SECONDS = 30 * 60
# A runner can exit 0 having produced nothing — the codex sandbox failing to initialize
# (`bwrap: loopback: Failed RTM_NEWADDR`) reports itself as a SUCCESSFUL run with no commit.
# Recording that as a terminal `completed` burned the (head_sha, provider) key, and the only
# thing that clears the key is a new head commit, which only the agent being refused could
# produce: clearing the gate required the action the gate forbade. This many re-dispatches are
# granted on the same head after an unproductive completion (#3433). ONE constant, consumed by
# both the refusal branch and the message it prints, so the two cannot drift apart.
UNPRODUCTIVE_COMPLETION_RETRY_LIMIT = 2
# What happens once those retries are spent. Refusing until the head changes would put the
# ORIGINAL latch back one step further out: a new head commit can only come from the agent
# being refused. So the allowance expires into a cooldown instead — a wait that time alone
# clears, which the hourly keepalive sweep then wakes. Nothing the gate forbids is required
# to open it.
UNPRODUCTIVE_COMPLETION_COOLDOWN_SECONDS = 30 * 60
TRUSTED_MARKER_AUTHORS = {
    "chatgpt-codex-connector",
    "chatgpt-codex-connector[bot]",
    "github-actions[bot]",
    "stranske",
    "stranske-automation-bot",
}
TRUSTED_MARKER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
CAPABILITY_ID_RE = re.compile(r"^capability:(?=[a-z0-9-]{3,128}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EVIDENCE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@-]{0,255}$")
SECRET_LIKE_EVIDENCE_PREFIXES = ("ghp_", "github_pat_", "sk-")
SECRET_LIKE_EVIDENCE_SEGMENT_RE = re.compile(
    r"(?:^|[:/#@])(?:" + "|".join(SECRET_LIKE_EVIDENCE_PREFIXES) + r")",
    re.IGNORECASE,
)
SUPERVISION_MODES = {
    "shadow",
    "human-reviewed",
    "human-on-exception",
    "unattended",
}
CAPABILITY_EVIDENCE_STATUSES = {"accepted", "rejected", "not-evaluated"}
TERMINAL_DISPOSITIONS = {
    "success",
    "failure",
    "no-change",
    "blocked",
    "cancelled",
}


@dataclasses.dataclass(frozen=True)
class RunnerPrompt:
    provider: str
    file: str
    text: str
    reference_pack_name: str | None = None


@dataclasses.dataclass(frozen=True)
class RunnerResult:
    provider: str
    success: bool
    final_message: str
    summary: str
    error: str | None = None
    truncated: bool = False


@dataclasses.dataclass(frozen=True)
class DebounceDecision:
    should_dispatch: bool
    reason: str
    key: str
    prior_status: str | None = None
    prior_head_sha: str | None = None
    # What would clear this refusal. Runtime rule: a gate reports its blocking quantity AND its
    # drainable quantity in the same place, so a refusal can never go silent about what would
    # release it. Empty when nothing is being blocked.
    drainable: str = ""


def _validate_capability_effect_evidence_values(values: dict[str, str]) -> None:
    non_strings = [name for name, value in values.items() if not isinstance(value, str)]
    if non_strings:
        raise ValueError(
            "capability evidence fields must be strings; invalid " + ", ".join(non_strings)
        )
    if not any(values.values()):
        return
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(
            "partial capability evidence is not allowed; missing " + ", ".join(missing)
        )
    if not CAPABILITY_ID_RE.fullmatch(values["capability_id"]):
        raise ValueError("capability_id must match capability:<lowercase-kebab-id>")
    if not SHA256_RE.fullmatch(values["effect_fingerprint"]):
        raise ValueError("effect_fingerprint must be a lowercase sha256 digest")
    artifact_ref = values["evidence_artifact_ref"]
    if not EVIDENCE_REF_RE.fullmatch(artifact_ref):
        raise ValueError("evidence_artifact_ref must be a bounded durable logical reference")
    lowered_ref = artifact_ref.lower()
    if SECRET_LIKE_EVIDENCE_SEGMENT_RE.search(artifact_ref):
        raise ValueError("evidence_artifact_ref has a credential-like prefix")
    if any(
        marker in lowered_ref for marker in ("token", "secret", "password", "api-key", "apikey")
    ):
        raise ValueError("evidence_artifact_ref contains a secret-like marker")
    if values["supervision_mode"] not in SUPERVISION_MODES:
        raise ValueError("unsupported supervision_mode")
    if values["capability_evidence_status"] not in CAPABILITY_EVIDENCE_STATUSES:
        raise ValueError("unsupported capability_evidence_status")
    if values["terminal_disposition"] not in TERMINAL_DISPOSITIONS:
        raise ValueError("unsupported terminal_disposition")


@dataclasses.dataclass(frozen=True)
class CapabilityEffectEvidence:
    """Bounded, provider-neutral evidence carried by a runner result.

    Empty evidence is valid for backwards compatibility. Once any capability
    field is present, the identity, effect fingerprint, durable artifact
    reference, supervision mode, evidence status, and terminal disposition
    must all be present and valid.
    """

    capability_id: str = ""
    effect_fingerprint: str = ""
    evidence_artifact_ref: str = ""
    supervision_mode: str = ""
    capability_evidence_status: str = ""
    terminal_disposition: str = ""

    def __post_init__(self) -> None:
        _validate_capability_effect_evidence_values(
            {
                "capability_id": self.capability_id,
                "effect_fingerprint": self.effect_fingerprint,
                "evidence_artifact_ref": self.evidence_artifact_ref,
                "supervision_mode": self.supervision_mode,
                "capability_evidence_status": self.capability_evidence_status,
                "terminal_disposition": self.terminal_disposition,
            }
        )

    def github_outputs(self) -> dict[str, str]:
        return {
            "capability-id": self.capability_id,
            "effect-fingerprint": self.effect_fingerprint,
            "evidence-artifact-ref": self.evidence_artifact_ref,
            "supervision-mode": self.supervision_mode,
            "capability-evidence-status": self.capability_evidence_status,
            "terminal-disposition": self.terminal_disposition,
        }


def normalize_capability_effect_evidence(
    *,
    capability_id: str = "",
    effect_fingerprint: str = "",
    evidence_artifact_ref: str = "",
    supervision_mode: str = "",
    capability_evidence_status: str = "",
    terminal_disposition: str = "",
) -> CapabilityEffectEvidence:
    """Validate optional runner capability evidence without inferring from prose."""
    values = {
        "capability_id": str(capability_id or "").strip().lower(),
        "effect_fingerprint": str(effect_fingerprint or "").strip().lower(),
        "evidence_artifact_ref": str(evidence_artifact_ref or "").strip(),
        "supervision_mode": str(supervision_mode or "").strip().lower(),
        "capability_evidence_status": str(capability_evidence_status or "").strip().lower(),
        "terminal_disposition": str(terminal_disposition or "").strip().lower(),
    }
    _validate_capability_effect_evidence_values(values)
    return CapabilityEffectEvidence(**values)


class RunnerDispatchStorage(Protocol):
    def read_record(self, pr_number: int, provider: str) -> dict[str, Any] | None: ...

    def write_record(self, pr_number: int, provider: str, record: dict[str, Any]) -> None: ...


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in PROVIDERS:
        raise ValueError(f"unsupported provider: {provider}")
    return normalized


def _resolve_child_path(root: Path, path: str | Path, *, description: str) -> Path:
    root_resolved = root.resolve()
    raw_path = Path(path)
    candidate = raw_path if raw_path.is_absolute() else root_resolved / raw_path
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"{description} must stay within {root_resolved}") from exc
    return candidate


def _resolve_reference_checkout_path(workspace_path: Path, checkout_path: str | Path) -> Path:
    reference_root = (workspace_path / ".reference").resolve()
    candidate = _resolve_child_path(
        workspace_path,
        checkout_path,
        description="reference checkout path",
    )
    try:
        candidate.relative_to(reference_root)
    except ValueError as exc:
        raise ValueError("reference checkout path must stay within .reference") from exc
    if candidate == reference_root:
        raise ValueError("reference checkout path must identify a child of .reference")
    return candidate


def _runner_key(pr_number: int, head_sha: str, provider: str) -> str:
    payload = f"{provider}:{pr_number}:{head_sha}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path} must be valid UTF-8") from exc


def _provider_instruction_path(workspace: Path, provider: str) -> Path:
    if provider == "codex":
        return workspace / ".github" / "codex" / "AGENT_INSTRUCTIONS.md"
    return workspace / ".github" / "claude" / "AGENT_INSTRUCTIONS.md"


def _repository_guidance_path(workspace: Path) -> Path:
    return workspace / "AGENTS.md"


def _prompt_output_name(provider: str, pr_number: str | int | None) -> str:
    suffix = f"-{pr_number}" if pr_number not in (None, "") else ""
    return f"{provider}-prompt{suffix}.md"


def _load_reference_packs_module() -> Any:
    try:
        return importlib.import_module("scripts.reference_packs")
    except ModuleNotFoundError as exc:
        if exc.name == "scripts.reference_packs":
            raise RuntimeError(
                "reference packs are not supported in this repository because "
                "scripts/reference_packs.py was not synced"
            ) from exc
        raise


def _load_orchestrator_skill_module() -> Any:
    try:
        return importlib.import_module("scripts.orchestrator_skill")
    except ModuleNotFoundError as exc:
        if exc.name == "scripts.orchestrator_skill":
            raise RuntimeError(
                "orchestrator skill context is not supported in this repository because "
                "scripts/orchestrator_skill.py was not synced"
            ) from exc
        raise


def _run_git(args: list[str], env: dict[str, str] | None = None) -> None:
    try:
        subprocess.check_call(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        redacted = ["<redacted>" if "x-access-token:" in part else part for part in args]
        raise RuntimeError(
            f"git command failed with exit code {exc.returncode}: {' '.join(redacted)}"
        ) from exc


def materialize_reference_packs(
    workspace: str | Path = ".",
    reference_pack_name: str | None = None,
    token: str | None = None,
) -> Path | None:
    """Validate and materialize configured reference packs into `.reference/`."""
    reference_packs = _load_reference_packs_module()
    workspace_path = Path(workspace).resolve()
    snapshot = reference_packs.load_reference_packs(workspace_path)
    if not snapshot.exists:
        return None

    plans = reference_packs.build_checkout_plan(snapshot.packs)
    if reference_pack_name:
        plans = [plan for plan in plans if plan.name == reference_pack_name]
        if not plans:
            raise ValueError(f"reference pack not found: {reference_pack_name}")

    reference_dir = workspace_path / ".reference"
    reference_dir.mkdir(exist_ok=True)

    for plan in plans:
        clone_parent = Path(tempfile.mkdtemp(prefix=f"ref-pack-{plan.name}-"))
        clone_dir = clone_parent / "repo"
        askpass_path = clone_parent / "git-askpass.sh"
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        if token:
            askpass_path.write_text(
                "#!/bin/sh\n"
                'case "$1" in\n'
                "  *Username*) printf '%s\\n' \"${GIT_ASKPASS_USERNAME:-x-access-token}\" ;;\n"
                "  *) printf '%s\\n' \"$GIT_ASKPASS_PASSWORD\" ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            askpass_path.chmod(0o700)
            git_env.update(
                {
                    "GIT_ASKPASS": str(askpass_path),
                    "GIT_ASKPASS_USERNAME": "x-access-token",
                    "GIT_ASKPASS_PASSWORD": token,
                }
            )

        clone_url = f"https://github.com/{plan.repo}.git"
        clone_cmd = ["git", "clone", "--depth=1", "--filter=blob:none", "--sparse"]
        is_sha = bool(re.fullmatch(r"[0-9a-fA-F]{40}", plan.ref))
        if not is_sha:
            clone_cmd.extend(["--branch", plan.ref])
        clone_cmd.extend([clone_url, str(clone_dir)])
        try:
            _run_git(clone_cmd, env=git_env)

            if is_sha:
                _run_git(
                    ["git", "-C", str(clone_dir), "fetch", "origin", plan.ref, "--depth=1"],
                    env=git_env,
                )
                _run_git(["git", "-C", str(clone_dir), "checkout", plan.ref], env=git_env)

            _run_git(
                [
                    "git",
                    "-C",
                    str(clone_dir),
                    "sparse-checkout",
                    "set",
                    "--no-cone",
                    *plan.paths,
                ],
                env=git_env,
            )
            _run_git(["git", "-C", str(clone_dir), "sparse-checkout", "reapply"], env=git_env)

            checkout_path = workspace_path / plan.checkout_path
            checkout_path.mkdir(parents=True, exist_ok=True)
            for rel_path in plan.paths:
                src = clone_dir / rel_path
                dst = checkout_path / rel_path
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                elif src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                else:
                    print(
                        f"warning: path '{rel_path}' not found in {plan.repo}@{plan.ref}",
                        file=sys.stderr,
                    )
        finally:
            shutil.rmtree(clone_parent, ignore_errors=True)

    summary_path = reference_dir / "REFERENCE_PACKS.md"
    with summary_path.open("w", encoding="utf-8") as handle:
        for plan in plans:
            checkout_path = workspace_path / plan.checkout_path
            handle.write(f"## {plan.name}\n")
            handle.write(f"- **Repo:** `{plan.repo}`\n")
            handle.write(f"- **Ref:** `{plan.ref}`\n")
            handle.write(f"- **Paths:** {', '.join(f'`{path}`' for path in plan.paths)}\n")
            handle.write(f"- **Location:** `{plan.checkout_path}/`\n\n")
            handle.write("### Contents\n")
            for path in sorted(item for item in checkout_path.rglob("*") if item.is_file()):
                handle.write(f"- `{path.relative_to(checkout_path)}`\n")
            handle.write("\n")
    return summary_path


def _materialize_single_checkout_plan(
    workspace_path: Path,
    *,
    repo: str,
    ref: str,
    paths: list[str],
    checkout_path: str,
    token: str | None,
) -> Path:
    clone_parent = Path(tempfile.mkdtemp(prefix="orchestrator-skill-"))
    clone_dir = clone_parent / "repo"
    askpass_path = clone_parent / "git-askpass.sh"
    git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token:
        askpass_path.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  *Username*) printf '%s\\n' \"${GIT_ASKPASS_USERNAME:-x-access-token}\" ;;\n"
            "  *) printf '%s\\n' \"$GIT_ASKPASS_PASSWORD\" ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        askpass_path.chmod(0o700)
        git_env.update(
            {
                "GIT_ASKPASS": str(askpass_path),
                "GIT_ASKPASS_USERNAME": "x-access-token",
                "GIT_ASKPASS_PASSWORD": token,
            }
        )

    clone_url = f"https://github.com/{repo}.git"
    clone_cmd = ["git", "clone", "--depth=1", "--filter=blob:none", "--sparse"]
    is_sha = bool(re.fullmatch(r"[0-9a-fA-F]{40}", ref))
    if not is_sha:
        clone_cmd.extend(["--branch", ref])
    clone_cmd.extend([clone_url, str(clone_dir)])
    try:
        _run_git(clone_cmd, env=git_env)

        if is_sha:
            _run_git(
                ["git", "-C", str(clone_dir), "fetch", "origin", ref, "--depth=1"],
                env=git_env,
            )
            _run_git(["git", "-C", str(clone_dir), "checkout", ref], env=git_env)

        _run_git(
            [
                "git",
                "-C",
                str(clone_dir),
                "sparse-checkout",
                "set",
                "--no-cone",
                *paths,
            ],
            env=git_env,
        )
        _run_git(["git", "-C", str(clone_dir), "sparse-checkout", "reapply"], env=git_env)

        destination_root = _resolve_reference_checkout_path(workspace_path, checkout_path)
        if destination_root.exists():
            shutil.rmtree(destination_root)
        destination_root.mkdir(parents=True, exist_ok=True)
        for rel_path in paths:
            src = clone_dir / rel_path
            dst = destination_root / rel_path
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            elif src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            else:
                print(
                    f"warning: path '{rel_path}' not found in {repo}@{ref}",
                    file=sys.stderr,
                )
    finally:
        shutil.rmtree(clone_parent, ignore_errors=True)

    return destination_root


def materialize_orchestrator_skill(
    workspace: str | Path = ".",
    *,
    pack_override: str | None = None,
    enabled_override: bool | None = None,
    token: str | None = None,
) -> Path | None:
    """Validate and materialize exported Orchestrator skill context into `.reference/`."""
    orchestrator_skill = _load_orchestrator_skill_module()
    workspace_path = Path(workspace).resolve()
    plan = orchestrator_skill.resolve_orchestrator_skill_plan(
        workspace_path,
        pack_override=pack_override,
        enabled_override=enabled_override,
    )
    if plan is None:
        return None

    if plan.pack:
        reference_packs = _load_reference_packs_module()
        snapshot = reference_packs.load_reference_packs(workspace_path)
        matching = [
            entry
            for entry in reference_packs.build_checkout_plan(snapshot.packs)
            if entry.name == plan.pack
        ]
        if not matching:
            raise ValueError(f"orchestrator skill reference pack not found: {plan.pack}")
        checkout_path = _resolve_reference_checkout_path(
            workspace_path,
            matching[0].checkout_path,
        )
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(checkout_path)
        materialize_reference_packs(
            workspace_path,
            reference_pack_name=plan.pack,
            token=token,
        )
    else:
        checkout_path = _materialize_single_checkout_plan(
            workspace_path,
            repo=plan.repo,
            ref=plan.ref,
            paths=plan.paths,
            checkout_path=plan.checkout_path,
            token=token,
        )

    return orchestrator_skill.write_orchestrator_skill_summary(
        workspace_path,
        checkout_path,
        pack_name=plan.pack,
    )


def assemble_prompt(
    reference_pack_name: str | None, context: dict[str, Any], provider: str
) -> RunnerPrompt:
    """Assemble a provider-specific prompt from template, context, and references."""
    provider = _validate_provider(provider)
    if provider not in PROMPT_PROVIDERS:
        raise ValueError(f"provider does not support prompt assembly: {provider}")
    workspace = Path(str(context.get("workspace", "."))).resolve()
    base_prompt_raw = context.get("base_prompt_file") or context.get("prompt_file")
    if not base_prompt_raw:
        raise ValueError("base_prompt_file is required")

    base_prompt = workspace / str(base_prompt_raw)
    if not base_prompt.is_file():
        raise FileNotFoundError(f"base prompt file not found: {base_prompt}")

    token = context.get("github_token") or context.get("token")
    if context.get("materialize_reference_packs"):
        materialize_reference_packs(
            workspace,
            reference_pack_name=reference_pack_name,
            token=token,
        )

    if context.get("materialize_orchestrator_skill"):
        orchestrator_summary_path = materialize_orchestrator_skill(
            workspace,
            pack_override=context.get("orchestrator_skill_pack") or None,
            enabled_override=context.get("orchestrator_skill_enabled"),
            token=token,
        )
    else:
        orchestrator_summary_raw = context.get("orchestrator_skill_summary_path")
        orchestrator_summary_path = (
            Path(str(orchestrator_summary_raw)) if orchestrator_summary_raw else None
        )
        if orchestrator_summary_path:
            orchestrator_summary_path = _resolve_child_path(
                workspace,
                orchestrator_summary_path,
                description="orchestrator_skill_summary_path",
            )

    output_file = str(
        context.get("output_file") or _prompt_output_name(provider, context.get("pr_number"))
    )
    output_path = workspace / output_file

    parts: list[str] = []
    instructions = _provider_instruction_path(workspace, provider)
    if instructions.is_file():
        parts.extend([_read_text(instructions).rstrip(), "\n---\n\n## Task Prompt\n"])
    parts.append(_read_text(base_prompt).rstrip())

    appendix = str(context.get("appendix") or "")
    mode = str(context.get("mode") or "")
    task_appendix_file = context.get("task_appendix_file")
    if mode == "keepalive" and task_appendix_file:
        task_path = Path(str(task_appendix_file))
        if not task_path.is_absolute():
            task_path = workspace / task_path
        if task_path.is_file() and task_path.stat().st_size > 0:
            appendix = _read_text(task_path)

    if appendix:
        parts.extend(["\n\n## Run context\n", appendix.rstrip()])

    repository_guidance = _repository_guidance_path(workspace)
    if repository_guidance.is_file():
        parts.extend(["\n\n## Repository Guidance\n", _read_text(repository_guidance).rstrip()])

    reference_summary = workspace / ".reference" / "REFERENCE_PACKS.md"
    if reference_summary.is_file():
        parts.extend(["\n\n## Reference Packs\n", _read_text(reference_summary).rstrip()])

    if orchestrator_summary_path and orchestrator_summary_path.is_file():
        parts.extend(
            [
                "\n\n## Orchestrator Skill Context\n",
                _read_text(orchestrator_summary_path).rstrip(),
            ]
        )

    text = "".join(parts).rstrip() + "\n"
    output_path.write_text(text, encoding="utf-8")
    return RunnerPrompt(
        provider=provider,
        file=output_file,
        text=text,
        reference_pack_name=reference_pack_name,
    )


def _extract_text_from_json_event(event: dict[str, Any]) -> str | None:
    for key in ("message", "text", "output", "final_message"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    content = event.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        chunks = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        text = "\n".join(chunk for chunk in chunks if chunk.strip())
        if text.strip():
            return text.strip()
    return None


def _parse_jsonl_output(raw_output: str) -> tuple[list[str], list[str]]:
    messages: list[str] = []
    errors: list[str] = []
    parsed_any = False
    for line in raw_output.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        parsed_any = True
        event_type = str(event.get("type") or event.get("status") or "").lower()
        text = _extract_text_from_json_event(event)
        if "error" in event_type or event.get("error"):
            error_value = event.get("error")
            nested_error = (
                _extract_text_from_json_event(error_value)
                if isinstance(error_value, dict)
                else None
            )
            direct_error = error_value.strip() if isinstance(error_value, str) else None
            errors.append(direct_error or nested_error or text or json.dumps(event, sort_keys=True))
        elif text:
            messages.append(text)
    if not parsed_any:
        return [], []
    return messages, errors


def parse_runner_output(provider: str, raw_output: str) -> RunnerResult:
    """Parse raw Codex/Claude output into a common result shape."""
    provider = _validate_provider(provider)
    if provider not in PROMPT_PROVIDERS:
        raise ValueError(f"provider does not support output parsing: {provider}")
    raw = raw_output or ""
    truncated = len(raw) > 64000 or bool(re.search(r"\btruncated\b", raw, re.IGNORECASE))
    clipped = raw[:64000] if len(raw) > 64000 else raw

    messages, errors = _parse_jsonl_output(clipped) if provider == "codex" else ([], [])
    final_message = errors[0] if errors else (messages[-1] if messages else clipped.strip())

    if not errors and re.search(
        r"(^::error::|\bTraceback\b|\bError:|\bException\b)",
        clipped,
        re.MULTILINE,
    ):
        first = next(
            (
                line.strip()
                for line in clipped.splitlines()
                if re.search(r"^::error::|\bTraceback\b|\bError:|\bException\b", line)
            ),
            "",
        )
        errors.append(first or "runner output indicates an error")

    if not final_message:
        final_message = "No output captured"

    summary = re.sub(r"\s+", " ", final_message).strip()[:500] or "No output captured"
    return RunnerResult(
        provider=provider,
        success=not errors,
        final_message=final_message,
        summary=summary,
        error=errors[0] if errors else None,
        truncated=truncated,
    )


def _marker_re(pr_number: int, provider: str) -> re.Pattern[str]:
    return re.compile(
        rf"<!--\s*{MARKER_PREFIX}:{provider}:{pr_number}:{MARKER_VERSION}\s+([\s\S]*?)\s*-->",
        re.DOTALL,
    )


def _build_marker(pr_number: int, provider: str, record: dict[str, Any]) -> str:
    payload = base64.b64encode(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return (
        f"Runner dispatch state for {provider} on PR #{pr_number}. Do not edit.\n\n"
        f"<!-- {MARKER_PREFIX}:{provider}:{pr_number}:{MARKER_VERSION} base64:{payload} -->"
    )


def _decode_record_candidate(candidate: str) -> str:
    value = candidate.strip()
    if value.startswith("base64:"):
        return base64.b64decode(value.removeprefix("base64:"), validate=True).decode("utf-8")
    return value


def _marker_safe_text(value: Any, limit: int = 1000) -> str:
    text = "" if value is None else str(value)
    if len(text) > limit:
        text = f"{text[:limit]}...[truncated {len(text) - limit} chars]"
    return text.replace("-->", "--\\u003e")


def _compact_runner_result_payload(result_payload: dict[str, Any]) -> dict[str, Any]:
    final_message_value = result_payload.get("final_message")
    final_message = "" if final_message_value is None else str(final_message_value)
    compact: dict[str, Any] = {
        "schema": "runner-result-summary/v1",
        "provider": str(result_payload.get("provider") or ""),
        "success": bool(result_payload.get("success")),
        "summary": _marker_safe_text(result_payload.get("summary")),
        "error": _marker_safe_text(result_payload.get("error")),
        "truncated": bool(result_payload.get("truncated")),
    }
    if final_message:
        compact["final_message_sha256"] = hashlib.sha256(final_message.encode("utf-8")).hexdigest()
        compact["final_message_chars"] = len(final_message)
    return compact


def _extract_record(value: str | None, pr_number: int, provider: str) -> dict[str, Any] | None:
    if not value:
        return None
    candidates: list[str] = []
    match = _marker_re(pr_number, provider).search(value)
    if match:
        candidates.append(match.group(1))
    stripped = value.strip()
    if stripped.startswith("{"):
        candidates.append(stripped)
    for candidate in candidates:
        try:
            payload = json.loads(_decode_record_candidate(candidate))
        except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("provider") == provider:
            return payload
    return None


def _variable_name(pr_number: int, provider: str) -> str:
    digest = hashlib.sha1(f"{provider}:{pr_number}".encode()).hexdigest()[:12]
    return f"RUNNER_DISPATCH_{provider.upper()}_{pr_number}_{digest}"[:100]


def _is_trusted_marker_comment(comment: dict[str, Any]) -> bool:
    user = comment.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    if isinstance(login, str) and login.strip().lower() in TRUSTED_MARKER_AUTHORS:
        return True

    association = str(comment.get("author_association") or "").upper()
    if association in TRUSTED_MARKER_ASSOCIATIONS:
        return True

    # Unit tests and older fixture data omit author metadata.
    return login is None and not association


class PrCommentRunnerStorage:
    def __init__(self, api: GitHubApi) -> None:
        self.api = api

    @classmethod
    def from_environment(cls) -> PrCommentRunnerStorage:
        repo, token = _github_context()
        return cls(GitHubApi(repo, token))

    def _iter_comments(self, pr_number: int, *, direction: str = "asc") -> Iterator[dict[str, Any]]:
        page = 1
        direction = "desc" if direction.strip().lower() == "desc" else "asc"
        while True:
            batch = self.api.request(
                "GET",
                f"/repos/{self.api.repo}/issues/{pr_number}/comments"
                f"?per_page=100&sort=created&direction={direction}&page={page}",
            )
            if not isinstance(batch, list):
                raise RuntimeError(
                    f"Expected list response from GitHub API comments page for PR {pr_number}"
                )
            yield from batch
            if len(batch) < 100:
                break
            page += 1

    def _find_comment(self, pr_number: int, provider: str) -> dict[str, Any] | None:
        pattern = _marker_re(pr_number, provider)
        for comment in self._iter_comments(pr_number, direction="desc"):
            if not _is_trusted_marker_comment(comment):
                continue
            body = comment.get("body")
            if isinstance(body, str) and pattern.search(body):
                return comment
        return None

    def read_record(self, pr_number: int, provider: str) -> dict[str, Any] | None:
        comment = self._find_comment(pr_number, provider)
        if not comment:
            return None
        body = comment.get("body")
        return _extract_record(body if isinstance(body, str) else None, pr_number, provider)

    def write_record(self, pr_number: int, provider: str, record: dict[str, Any]) -> None:
        body = _build_marker(pr_number, provider, record)
        existing = self._find_comment(pr_number, provider)
        if existing and existing.get("id"):
            self.api.request(
                "PATCH",
                f"/repos/{self.api.repo}/issues/comments/{existing['id']}",
                {"body": body},
            )
            return
        self.api.request(
            "POST",
            f"/repos/{self.api.repo}/issues/{pr_number}/comments",
            {"body": body},
        )


class RepoVariableRunnerStorage:
    def __init__(self, api: GitHubApi) -> None:
        self.api = api

    @classmethod
    def from_environment(cls) -> RepoVariableRunnerStorage:
        repo, token = _github_context()
        return cls(GitHubApi(repo, token))

    def read_record(
        self, pr_number: int, provider: str, *, require_access: bool = False
    ) -> dict[str, Any] | None:
        name = _variable_name(pr_number, provider)
        try:
            payload = self.api.request("GET", f"/repos/{self.api.repo}/actions/variables/{name}")
        except RuntimeError as exc:
            message = str(exc)
            # Explicit single-store callers retain their historical best-effort
            # read. Migration checks must distinguish denied access from absence.
            if " failed: 404 " in message or (
                not require_access and (" failed: 401 " in message or " failed: 403 " in message)
            ):
                return None
            raise
        value = payload.get("value") if isinstance(payload, dict) else None
        return _extract_record(value if isinstance(value, str) else None, pr_number, provider)

    def write_record(self, pr_number: int, provider: str, record: dict[str, Any]) -> None:
        name = _variable_name(pr_number, provider)
        value = json.dumps(record, sort_keys=True, separators=(",", ":"))
        try:
            self.api.request(
                "PATCH",
                f"/repos/{self.api.repo}/actions/variables/{name}",
                {"name": name, "value": value},
            )
        except RuntimeError as exc:
            message = str(exc)
            if " failed: 404 " in message:
                try:
                    self.api.request(
                        "POST",
                        f"/repos/{self.api.repo}/actions/variables",
                        {"name": name, "value": value},
                    )
                except RuntimeError as create_exc:
                    raise RuntimeError("Repository-variable creation failed.") from create_exc
                return
            # A denied write is not a persisted reservation or completion.
            # Propagate failure rather than reporting successful progress.
            raise RuntimeError("Repository-variable write failed.") from exc


class FallbackRunnerStorage:
    def __init__(self, primary: RunnerDispatchStorage, fallback: RunnerDispatchStorage) -> None:
        self.primary = primary
        self.fallback = fallback
        self._use_fallback = False

    def read_record(self, pr_number: int, provider: str) -> dict[str, Any] | None:
        try:
            record = self.primary.read_record(pr_number, provider)
        except Exception as exc:
            print(f"warning: runner dispatch primary storage unavailable: {exc}", file=sys.stderr)
            self._use_fallback = True
            return self.fallback.read_record(pr_number, provider)
        if record is not None:
            return record
        return self.fallback.read_record(pr_number, provider)

    def write_record(self, pr_number: int, provider: str, record: dict[str, Any]) -> None:
        if not self._use_fallback:
            try:
                self.primary.write_record(pr_number, provider, record)
                return
            except Exception as exc:
                print(f"warning: runner dispatch primary write failed: {exc}", file=sys.stderr)
                self._use_fallback = True
        self.fallback.write_record(pr_number, provider, record)


def _storage_from_name(name: str) -> RunnerDispatchStorage:
    if name == "pr-comment":
        return PrCommentRunnerStorage.from_environment()
    if name == "repo-variable":
        return RepoVariableRunnerStorage.from_environment()
    if name == "auto":
        return FallbackRunnerStorage(
            PrCommentRunnerStorage.from_environment(),
            RepoVariableRunnerStorage.from_environment(),
        )
    raise ValueError(f"unsupported storage backend: {name}")


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _pending_record_is_stale(prior: dict[str, Any], *, now: dt.datetime | None = None) -> bool:
    started_at = _parse_timestamp(prior.get("started_at"))
    if started_at is None:
        return True
    current = now or dt.datetime.now(dt.UTC)
    return (current - started_at).total_seconds() > PENDING_STALE_AFTER_SECONDS


def _utc_now_dt() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _unproductive_retry_available_at(prior: dict[str, Any] | None) -> dt.datetime | None:
    """When the cooldown after spent retries expires, or None if it cannot be determined.

    An unreadable or absent ``completed_at`` returns None, which the caller treats as "cooldown
    cannot be measured, so let the dispatch through". Failing toward motion is the whole point:
    a gate that cannot measure itself must not hold the loop shut on that basis.
    """
    if not prior:
        return None
    completed_at = _parse_timestamp(prior.get("completed_at"))
    if completed_at is None:
        return None
    return completed_at + dt.timedelta(seconds=UNPRODUCTIVE_COMPLETION_COOLDOWN_SECONDS)


def _completion_was_unproductive(prior: dict[str, Any] | None) -> bool:
    """True only when a completion explicitly reported that it produced no work.

    Absence of the field means the caller did not measure productivity, which must keep the
    pre-#3433 behavior (treat the completion as terminal) rather than silently loosening the
    debounce for every caller that has not been taught to report it.
    """
    return prior is not None and prior.get("productive") is False


def _unproductive_completion_count(prior: dict[str, Any] | None) -> int:
    if not prior:
        return 0
    try:
        return int(prior.get("unproductive_completions") or 0)
    except (TypeError, ValueError):
        return 0


def _workflow_attempt_id() -> str:
    """Identify the reserving workflow attempt across its jobs, not just the PR head."""
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if repository and run_id and attempt:
        return f"{repository}:{run_id}:{attempt}"
    return ""


def _unavailable_dispatch(key: str, prior: dict[str, Any] | None = None) -> DebounceDecision:
    return DebounceDecision(
        False,
        "authoritative-storage-unavailable",
        key,
        prior_status=str(prior.get("status")) if prior else None,
        prior_head_sha=str(prior.get("head_sha")) if prior else None,
        drainable="retry reservation after primary storage and legacy-state reads recover",
    )


def _reserve_dispatch(
    storage: RunnerDispatchStorage,
    pr_number: int,
    head_sha: str,
    provider: str,
    key: str,
    prior: dict[str, Any] | None,
    *,
    reason: str,
) -> DebounceDecision:
    """Write the pending reservation for a granted dispatch and describe the decision."""
    record = {
        "provider": provider,
        "pr_number": pr_number,
        "head_sha": head_sha,
        "key": key,
        "status": "pending",
        "started_at": _utc_now(),
    }
    attempt_id = _workflow_attempt_id()
    if attempt_id:
        record["workflow_attempt_id"] = attempt_id
    # Carry the unproductive tally across the retry so the allowance is bounded: it is the only
    # thing that makes "retry an unproductive completion" terminate instead of cycling forever.
    unproductive = _unproductive_completion_count(prior)
    if unproductive and prior and prior.get("head_sha") == head_sha:
        record["unproductive_completions"] = unproductive
        if _completion_was_unproductive(prior):
            record["productive"] = False
    # Auto completions only accept the primary reservation. Never start work
    # whose ownership would exist only in the fallback and could not complete.
    reservation_storage = storage.primary if isinstance(storage, FallbackRunnerStorage) else storage
    try:
        reservation_storage.write_record(pr_number, provider, record)
    except Exception as exc:
        if not isinstance(storage, FallbackRunnerStorage):
            raise
        _log_storage_failure("write", exc, phase="reservation")
        return _unavailable_dispatch(key, prior)
    return DebounceDecision(
        True,
        reason,
        key,
        prior_status=str(prior.get("status")) if prior else None,
        prior_head_sha=str(prior.get("head_sha")) if prior else None,
    )


def should_dispatch(
    pr_number: int,
    head_sha: str,
    provider: str,
    storage: RunnerDispatchStorage | None = None,
    *,
    authority_challenge: bool = False,
) -> DebounceDecision:
    """Reserve dispatch unless the same PR/head SHA completed or is actively pending.

    Error records are retried deliberately: they mean the prior runner attempt did not
    leave a successful completion marker, so a later Gate pass may try again.

    A completion that produced no work is retried too, up to
    ``UNPRODUCTIVE_COMPLETION_RETRY_LIMIT`` times on the same head, and after that on a
    ``UNPRODUCTIVE_COMPLETION_COOLDOWN_SECONDS`` timer. Without that, a runner that exits 0
    having done nothing latches the loop shut: the refusal could only be cleared by a new head
    commit, and only the refused agent could push one (#3433). The cooldown matters for the
    same reason — an allowance that expired into a permanent refusal would just move that latch
    two runs later.
    """
    provider = _validate_provider(provider)
    if authority_challenge and not _verified_authority_challenge(pr_number):
        raise ValueError("Authority challenge reservation requires a verified signed claim.")
    storage = storage or _storage_from_name("auto")
    if authority_challenge and not isinstance(storage, FallbackRunnerStorage):
        raise ValueError("Authority challenge reservation requires authoritative auto storage.")
    key = _runner_key(pr_number, head_sha, provider)
    try:
        if isinstance(storage, FallbackRunnerStorage):
            prior = storage.primary.read_record(pr_number, provider)
            if prior is None:
                # Respect legacy fallback reservations until they finish/age out,
                # but any newly granted reservation must be written to primary.
                if isinstance(storage.fallback, RepoVariableRunnerStorage):
                    prior = storage.fallback.read_record(pr_number, provider, require_access=True)
                else:
                    prior = storage.fallback.read_record(pr_number, provider)
        else:
            prior = storage.read_record(pr_number, provider)
    except Exception as exc:
        if not isinstance(storage, FallbackRunnerStorage):
            raise
        _log_storage_failure("read", exc, phase="reservation")
        return _unavailable_dispatch(key)
    unproductive_completions = _unproductive_completion_count(prior)

    if authority_challenge:
        return _reserve_dispatch(
            storage,
            pr_number,
            head_sha,
            provider,
            key,
            prior,
            reason="due-authority-challenge",
        )

    if prior and prior.get("head_sha") == head_sha:
        status = str(prior.get("status") or "")
        if status == "completed" and _completion_was_unproductive(prior):
            if unproductive_completions <= UNPRODUCTIVE_COMPLETION_RETRY_LIMIT:
                return _reserve_dispatch(
                    storage,
                    pr_number,
                    head_sha,
                    provider,
                    key,
                    prior,
                    reason="retry-unproductive-completion",
                )
            retry_at = _unproductive_retry_available_at(prior)
            if retry_at is not None and _utc_now_dt() < retry_at:
                return DebounceDecision(
                    False,
                    "unproductive-cooldown",
                    key,
                    prior_status=status,
                    prior_head_sha=head_sha,
                    drainable=(
                        f"time: retry at {retry_at.isoformat()} "
                        f"(after {unproductive_completions} zero-output runs)"
                    ),
                )
            return _reserve_dispatch(
                storage,
                pr_number,
                head_sha,
                provider,
                key,
                prior,
                reason="retry-after-unproductive-cooldown",
            )
        if status == "completed" or (status == "pending" and not _pending_record_is_stale(prior)):
            return DebounceDecision(
                False,
                f"duplicate-{status}",
                key,
                prior_status=status,
                prior_head_sha=head_sha,
                drainable=(
                    "a new head commit"
                    if status == "completed"
                    else (
                        "the in-flight run finishing, or this pending record ageing past "
                        f"{PENDING_STALE_AFTER_SECONDS}s"
                    )
                ),
            )

    if prior is None:
        reason = "first-dispatch"
    elif prior.get("head_sha") != head_sha:
        reason = "head-sha-changed"
    elif str(prior.get("status") or "") == "pending":
        reason = "stale-pending"
    else:
        reason = f"retry-{str(prior.get('status') or 'unknown')}"
    return _reserve_dispatch(storage, pr_number, head_sha, provider, key, prior, reason=reason)


def _verified_authority_challenge(pr_number: int) -> bool:
    """Use the existing HMAC verifier; never accept a caller's boolean assertion."""
    if (
        not _workflow_attempt_id()
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or os.environ.get("GITHUB_ACTOR") != "github-actions[bot]"
    ):
        return False
    script = """
const { verifyAuthorityChallengeEnvelope } =
  require('./.github/scripts/keepalive_challenge_due.js');
const verified = verifyAuthorityChallengeEnvelope({
  claimJson: process.env.AUTHORITY_CHALLENGE_CLAIM,
  signingKey: process.env.AUTHORITY_CHALLENGE_SIGNING_KEY,
  repository: process.env.GITHUB_REPOSITORY,
  prNumber: process.argv[1],
  boundaryFingerprint: process.env.AUTHORITY_CHALLENGE_FINGERPRINT,
});
process.exitCode = verified ? 0 : 1;
"""
    try:
        result = subprocess.run(
            ["node", "-e", script, str(pr_number)],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _log_storage_failure(operation: str, exc: Exception, *, phase: str = "completion") -> None:
    # GitHubApi preserves the HTTP/network exception as its cause. Log diagnostic
    # metadata, not raw exception text, which can contain URLs or response bodies.
    cause = exc.__cause__ or exc
    code = getattr(cause, "code", None)
    status = str(code) if isinstance(code, int) and 100 <= code <= 599 else "unknown"
    print(
        f"warning: authoritative {phase} {operation} failed: "
        f"error_type={type(exc).__name__} cause_type={type(cause).__name__} "
        f"http_status={status}",
        file=sys.stderr,
    )


def _unrecorded_completion(prior: dict[str, Any], key: str, reason: str) -> dict[str, Any]:
    return {
        **prior,
        "status": "unknown",
        "key": key,
        "completion_recorded": False,
        "completion_reason": reason,
    }


def record_completion(
    pr_number: int,
    head_sha: str,
    provider: str,
    result: RunnerResult | dict[str, Any],
    storage: RunnerDispatchStorage | None = None,
    produced_work: bool | None = None,
) -> dict[str, Any]:
    """Persist terminal runner state after a dispatch finishes.

    ``produced_work`` is the caller's verdict on whether the run actually moved the branch.
    ``None`` means unmeasured and preserves an existing same-head unproductive retry streak;
    otherwise it preserves the pre-#3433 behavior. ``False`` marks the
    completion unproductive so ``should_dispatch`` will grant a bounded retry on the same head
    instead of refusing forever (#3433).
    """
    provider = _validate_provider(provider)
    storage = storage or _storage_from_name("auto")
    key = _runner_key(pr_number, head_sha, provider)
    result_payload = (
        dataclasses.asdict(result) if dataclasses.is_dataclass(result) else dict(result)
    )
    status = "completed" if result_payload.get("success") else "error"
    compact_result = _compact_runner_result_payload(result_payload)
    # Dispatch and completion both require the authoritative reservation.
    # An empty/stale fallback cannot prove that a newer attempt does not own the
    # primary, even if caller identity is absent.
    uses_fallback = isinstance(storage, FallbackRunnerStorage)
    completion_storage = storage.primary if isinstance(storage, FallbackRunnerStorage) else storage
    try:
        prior_record = completion_storage.read_record(pr_number, provider)
    except Exception as exc:
        if not uses_fallback:
            raise
        _log_storage_failure("read", exc)
        return _unrecorded_completion({}, key, "authoritative-storage-unavailable")
    if uses_fallback and prior_record is None:
        return _unrecorded_completion({}, key, "authoritative-reservation-missing")
    prior = prior_record or {}
    if prior.get("workflow_attempt_id") and (
        prior.get("workflow_attempt_id") != _workflow_attempt_id()
        or (prior.get("key") != key and produced_work is not True)
    ):
        # A completion rerun from an earlier attempt must not overwrite a newer reservation,
        # including when both attempts target the same head. The owning attempt may report
        # a new head only when it explicitly measured productive work. Return an observation only.
        return _unrecorded_completion(prior, key, "stale-attempt")
    if produced_work is None and prior.get("key") == key and _completion_was_unproductive(prior):
        produced_work = False
    completed_at = (
        prior.get("completed_at")
        if prior.get("key") == key and prior.get("status") in TERMINAL_STATUSES
        else _utc_now()
    )
    record = {
        **prior,
        "provider": provider,
        "pr_number": pr_number,
        "head_sha": head_sha,
        "key": key,
        "status": status,
        "completed_at": completed_at,
        "result": compact_result,
    }
    if status == "completed" and produced_work is not None:
        record["productive"] = bool(produced_work)
        if produced_work:
            record["unproductive_completions"] = 0
        elif prior.get("key") == key and prior.get("status") in TERMINAL_STATUSES:
            # This completion is already recorded; re-running the completion job for the same
            # dispatch key must not spend another retry. record_completion is idempotent for a
            # key by contract (see completed_at above, which is preserved the same way), and a
            # counter that advanced on a rerun would quietly exhaust the allowance without any
            # additional agent run having happened.
            record["unproductive_completions"] = _unproductive_completion_count(prior) or 1
        else:
            previous = _unproductive_completion_count(prior)
            # Past the allowance the streak stops climbing: the cooldown is re-armed from this
            # completion's timestamp instead, so each new zero-output run buys one fresh window
            # rather than an ever-growing count that means nothing.
            record["unproductive_completions"] = min(
                previous + 1, UNPRODUCTIVE_COMPLETION_RETRY_LIMIT + 1
            )
    try:
        completion_storage.write_record(pr_number, provider, record)
    except Exception as exc:
        if not uses_fallback:
            raise
        _log_storage_failure("write", exc)
        # Never redirect a checked primary reservation into an unchecked fallback.
        # A failed response may be ambiguous; a retry re-reads primary state first.
        return _unrecorded_completion(prior, key, "authoritative-storage-unavailable")
    return record


def _github_output_value(value: str) -> str:
    return value.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")


def _write_github_output(outputs: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={_github_output_value(value)}\n")


def _parse_optional_bool(raw: str) -> bool | None:
    normalized = (raw or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("orchestrator skill enabled override must be true or false")


def _cmd_assemble(args: argparse.Namespace) -> int:
    context = {
        "workspace": args.workspace,
        "base_prompt_file": args.base_prompt,
        "appendix": args.appendix or "",
        "mode": args.mode,
        "pr_number": args.pr_number,
        "output_file": args.output,
        "task_appendix_file": args.task_appendix_file,
        "materialize_reference_packs": args.materialize_reference_packs,
        "materialize_orchestrator_skill": args.materialize_orchestrator_skill,
        "orchestrator_skill_pack": args.orchestrator_skill_pack or None,
        "orchestrator_skill_enabled": _parse_optional_bool(args.orchestrator_skill_enabled),
        "orchestrator_skill_summary_path": os.environ.get("ORCHESTRATOR_SKILL_SUMMARY_PATH"),
        "github_token": os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"),
    }
    prompt = assemble_prompt(args.reference_pack_name, context, args.provider)
    outputs = {"file": prompt.file, "provider": prompt.provider}
    _write_github_output(outputs)
    print(json.dumps({**outputs, "chars": len(prompt.text)}, sort_keys=True))
    return 0


def _cmd_parse(args: argparse.Namespace) -> int:
    raw = (
        Path(args.raw_output_file).read_text(encoding="utf-8")
        if args.raw_output_file
        else sys.stdin.read()
    )
    result = parse_runner_output(args.provider, raw)
    outputs = {
        "success": "true" if result.success else "false",
        "summary": result.summary,
        "final-message-summary": result.summary,
        "error": result.error or "",
        "error-summary": result.error or result.summary,
        "truncated": "true" if result.truncated else "false",
        "final-message": base64.b64encode(result.final_message.encode("utf-8")).decode("ascii"),
    }
    _write_github_output(outputs)
    print(json.dumps(dataclasses.asdict(result), sort_keys=True))
    return 0


def _cmd_should_dispatch(args: argparse.Namespace) -> int:
    decision = should_dispatch(
        int(args.pr_number),
        args.head_sha,
        args.provider,
        storage=_storage_from_name(args.storage),
        authority_challenge=args.authority_challenge,
    )
    outputs = {
        "should_dispatch": "true" if decision.should_dispatch else "false",
        "reason": decision.reason,
        "key": decision.key,
        "prior_status": decision.prior_status or "",
        "prior_head_sha": decision.prior_head_sha or "",
        # Always emitted, including as "" for a granted dispatch, so "no drainable path stated"
        # can never be confused with "nothing is blocking" — one sentinel, one meaning.
        "drainable": decision.drainable,
    }
    _write_github_output(outputs)
    print(json.dumps(outputs, sort_keys=True))
    return 0


def _parse_produced_work(raw: str) -> bool | None:
    """Parse the caller's productivity verdict, treating anything unrecognized as unmeasured.

    Deliberately does NOT reuse ``_parse_optional_bool``: that helper raises on an unknown
    value, and a workflow that could not read the branch head (API hiccup, token scope) would
    then fail to record the completion at all — a worse outcome than the debounce defect this
    field exists to fix. Unmeasured must degrade to the pre-#3433 behavior, not to an error.
    """
    normalized = (raw or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _cmd_record_completion(args: argparse.Namespace) -> int:
    raw = ""
    if args.raw_output_file:
        path = Path(args.raw_output_file)
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
    provider = _validate_provider(args.provider)
    if provider in PROMPT_PROVIDERS:
        result = parse_runner_output(provider, raw or args.summary or "")
    else:
        summary = args.summary or raw or "No output captured"
        result = RunnerResult(
            provider=provider,
            success=args.exit_code is None or int(args.exit_code) == 0,
            final_message=summary,
            summary=re.sub(r"\s+", " ", summary).strip()[:500] or "No output captured",
        )
    if args.exit_code is not None and int(args.exit_code) != 0 and result.success:
        result = dataclasses.replace(result, success=False, error=result.summary)
    record = record_completion(
        int(args.pr_number),
        args.head_sha,
        args.provider,
        result,
        storage=_storage_from_name(args.storage),
        produced_work=_parse_produced_work(args.produced_work),
    )
    outputs = {
        "recorded": "false" if record.get("completion_recorded") is False else "true",
        "reason": str(record.get("completion_reason", "")),
        "status": str(record["status"]),
        "key": str(record["key"]),
        "productive": "" if "productive" not in record else str(record["productive"]).lower(),
    }
    _write_github_output(outputs)
    print(json.dumps(outputs, sort_keys=True))
    return 0


def _cmd_normalize_evidence(args: argparse.Namespace) -> int:
    evidence = normalize_capability_effect_evidence(
        capability_id=args.capability_id,
        effect_fingerprint=args.effect_fingerprint,
        evidence_artifact_ref=args.evidence_artifact_ref,
        supervision_mode=args.supervision_mode,
        capability_evidence_status=args.capability_evidence_status,
        terminal_disposition=args.terminal_disposition,
    )
    outputs = evidence.github_outputs()
    _write_github_output(outputs)
    print(json.dumps(outputs, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    assemble = subparsers.add_parser("assemble-prompt", help="assemble provider prompt")
    assemble.add_argument("--provider", choices=sorted(PROMPT_PROVIDERS), required=True)
    assemble.add_argument("--base-prompt", required=True)
    assemble.add_argument("--workspace", default=".")
    assemble.add_argument("--appendix", default="")
    assemble.add_argument("--mode", default="")
    assemble.add_argument("--pr-number", default="")
    assemble.add_argument("--output", default="")
    assemble.add_argument("--task-appendix-file", default="")
    assemble.add_argument("--reference-pack-name", default="")
    assemble.add_argument("--materialize-reference-packs", action="store_true")
    assemble.add_argument("--orchestrator-skill-pack", default="")
    assemble.add_argument("--orchestrator-skill-enabled", default="")
    assemble.add_argument("--materialize-orchestrator-skill", action="store_true")
    assemble.set_defaults(func=_cmd_assemble)

    parse = subparsers.add_parser("parse-output", help="parse provider output")
    parse.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    parse.add_argument("--raw-output-file", default="")
    parse.set_defaults(func=_cmd_parse)

    dispatch = subparsers.add_parser("should-dispatch", help="reserve a runner dispatch")
    dispatch.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    dispatch.add_argument("--pr-number", required=True)
    dispatch.add_argument("--head-sha", required=True)
    dispatch.add_argument(
        "--storage", choices=["auto", "pr-comment", "repo-variable"], default="auto"
    )
    dispatch.set_defaults(func=_cmd_should_dispatch)
    dispatch.add_argument(
        "--authority-challenge",
        action="store_true",
        help="reserve a signed authority challenge before bypassing ordinary debounce",
    )

    complete = subparsers.add_parser("record-completion", help="persist runner completion")
    complete.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    complete.add_argument("--pr-number", required=True)
    complete.add_argument("--head-sha", required=True)
    complete.add_argument(
        "--storage", choices=["auto", "pr-comment", "repo-variable"], default="auto"
    )
    complete.add_argument("--raw-output-file", default="")
    complete.add_argument("--summary", default="")
    complete.add_argument("--exit-code", default=None)
    complete.add_argument(
        "--produced-work",
        default="",
        help=(
            "whether the run actually moved the branch (true/false). Anything else, including "
            "the default, means unmeasured and preserves an existing unproductive retry streak."
        ),
    )
    complete.set_defaults(func=_cmd_record_completion)

    evidence = subparsers.add_parser(
        "normalize-evidence", help="validate optional capability/effect evidence"
    )
    evidence.add_argument("--capability-id", default="")
    evidence.add_argument("--effect-fingerprint", default="")
    evidence.add_argument("--evidence-artifact-ref", default="")
    evidence.add_argument("--supervision-mode", default="")
    evidence.add_argument("--capability-evidence-status", default="")
    evidence.add_argument("--terminal-disposition", default="")
    evidence.set_defaults(func=_cmd_normalize_evidence)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
