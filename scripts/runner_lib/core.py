"""Shared runner prompt, output parsing, and dispatch debounce utilities."""

from __future__ import annotations

import argparse
import base64
import dataclasses
import datetime as dt
import hashlib
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

from scripts import reference_packs
from scripts.state_fingerprint import GitHubApi, _github_context

MARKER_VERSION = "v1"
MARKER_PREFIX = "runner-dispatch"
PROVIDERS = {"autofix", "claude", "codex"}
PROMPT_PROVIDERS = {"claude", "codex"}
TERMINAL_STATUSES = {"completed", "error"}


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


def _prompt_output_name(provider: str, pr_number: str | int | None) -> str:
    suffix = f"-{pr_number}" if pr_number not in (None, "") else ""
    return f"{provider}-prompt{suffix}.md"


def materialize_reference_packs(
    workspace: str | Path = ".",
    reference_pack_name: str | None = None,
    token: str | None = None,
) -> Path | None:
    """Validate and materialize configured reference packs into `.reference/`."""
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
            subprocess.check_call(
                clone_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=git_env,
            )

            if is_sha:
                subprocess.check_call(
                    ["git", "-C", str(clone_dir), "fetch", "origin", plan.ref, "--depth=1"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=git_env,
                )
                subprocess.check_call(
                    ["git", "-C", str(clone_dir), "checkout", plan.ref],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=git_env,
                )

            subprocess.check_call(
                [
                    "git",
                    "-C",
                    str(clone_dir),
                    "sparse-checkout",
                    "set",
                    "--no-cone",
                    *plan.paths,
                ],
                stdout=subprocess.DEVNULL,
                env=git_env,
            )
            subprocess.check_call(
                ["git", "-C", str(clone_dir), "sparse-checkout", "reapply"],
                stdout=subprocess.DEVNULL,
                env=git_env,
            )

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

    if context.get("materialize_reference_packs"):
        materialize_reference_packs(
            workspace,
            reference_pack_name=reference_pack_name,
            token=context.get("github_token") or context.get("token"),
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

    reference_summary = workspace / ".reference" / "REFERENCE_PACKS.md"
    if reference_summary.is_file():
        parts.extend(["\n\n## Reference Packs\n", _read_text(reference_summary).rstrip()])

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
            errors.append(text or json.dumps(event, sort_keys=True))
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
    final_message = messages[-1] if messages else clipped.strip()

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
        rf"<!--\s*{MARKER_PREFIX}:{provider}:{pr_number}:{MARKER_VERSION}\s+(\{{.*?\}})\s*-->",
        re.DOTALL,
    )


def _build_marker(pr_number: int, provider: str, record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return (
        f"Runner dispatch state for {provider} on PR #{pr_number}. Do not edit.\n\n"
        f"<!-- {MARKER_PREFIX}:{provider}:{pr_number}:{MARKER_VERSION} {payload} -->"
    )


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
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("provider") == provider:
            return payload
    return None


def _variable_name(pr_number: int, provider: str) -> str:
    digest = hashlib.sha1(f"{provider}:{pr_number}".encode()).hexdigest()[:12]
    return f"RUNNER_DISPATCH_{provider.upper()}_{pr_number}_{digest}"[:100]


class PrCommentRunnerStorage:
    def __init__(self, api: GitHubApi) -> None:
        self.api = api

    @classmethod
    def from_environment(cls) -> PrCommentRunnerStorage:
        repo, token = _github_context()
        return cls(GitHubApi(repo, token))

    def _iter_comments(self, pr_number: int) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            batch = self.api.request(
                "GET",
                f"/repos/{self.api.repo}/issues/{pr_number}/comments?per_page=100&page={page}",
            )
            if not isinstance(batch, list):
                raise RuntimeError(
                    f"Expected list response from GitHub API comments page for PR {pr_number}"
                )
            yield from reversed(batch)
            if len(batch) < 100:
                return
            page += 1

    def _find_comment(self, pr_number: int, provider: str) -> dict[str, Any] | None:
        pattern = _marker_re(pr_number, provider)
        for comment in self._iter_comments(pr_number):
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

    def read_record(self, pr_number: int, provider: str) -> dict[str, Any] | None:
        name = _variable_name(pr_number, provider)
        try:
            payload = self.api.request("GET", f"/repos/{self.api.repo}/actions/variables/{name}")
        except RuntimeError as exc:
            message = str(exc)
            if (
                " failed: 404 " in message
                or " failed: 401 " in message
                or " failed: 403 " in message
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
                self.api.request(
                    "POST",
                    f"/repos/{self.api.repo}/actions/variables",
                    {"name": name, "value": value},
                )
                return
            if " failed: 401 " in message or " failed: 403 " in message:
                print(
                    f"warning: runner dispatch write skipped for {name}: {message}",
                    file=sys.stderr,
                )
                return
            raise


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


def should_dispatch(
    pr_number: int,
    head_sha: str,
    provider: str,
    storage: RunnerDispatchStorage | None = None,
) -> DebounceDecision:
    """Reserve a provider dispatch unless the same PR/head SHA was already seen."""
    provider = _validate_provider(provider)
    storage = storage or _storage_from_name("auto")
    key = _runner_key(pr_number, head_sha, provider)
    prior = storage.read_record(pr_number, provider)

    if prior and prior.get("head_sha") == head_sha:
        status = str(prior.get("status") or "")
        if status in {"pending", "completed"}:
            return DebounceDecision(
                False,
                f"duplicate-{status}",
                key,
                prior_status=status,
                prior_head_sha=head_sha,
            )

    reason = "first-dispatch" if prior is None else "head-sha-changed"
    record = {
        "provider": provider,
        "pr_number": pr_number,
        "head_sha": head_sha,
        "key": key,
        "status": "pending",
        "started_at": _utc_now(),
    }
    storage.write_record(pr_number, provider, record)
    return DebounceDecision(
        True,
        reason,
        key,
        prior_status=str(prior.get("status")) if prior else None,
        prior_head_sha=str(prior.get("head_sha")) if prior else None,
    )


def record_completion(
    pr_number: int,
    head_sha: str,
    provider: str,
    result: RunnerResult | dict[str, Any],
    storage: RunnerDispatchStorage | None = None,
) -> dict[str, Any]:
    """Persist terminal runner state after a dispatch finishes."""
    provider = _validate_provider(provider)
    storage = storage or _storage_from_name("auto")
    key = _runner_key(pr_number, head_sha, provider)
    result_payload = (
        dataclasses.asdict(result) if dataclasses.is_dataclass(result) else dict(result)
    )
    status = "completed" if result_payload.get("success") else "error"
    prior = storage.read_record(pr_number, provider) or {}
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
        "result": result_payload,
    }
    storage.write_record(pr_number, provider, record)
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
    )
    outputs = {
        "should_dispatch": "true" if decision.should_dispatch else "false",
        "reason": decision.reason,
        "key": decision.key,
        "prior_status": decision.prior_status or "",
        "prior_head_sha": decision.prior_head_sha or "",
    }
    _write_github_output(outputs)
    print(json.dumps(outputs, sort_keys=True))
    return 0


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
    )
    outputs = {"recorded": "true", "status": str(record["status"]), "key": str(record["key"])}
    _write_github_output(outputs)
    print(json.dumps(outputs, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    assemble = subparsers.add_parser("assemble-prompt", help="assemble provider prompt")
    assemble.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    assemble.add_argument("--base-prompt", required=True)
    assemble.add_argument("--workspace", default=".")
    assemble.add_argument("--appendix", default="")
    assemble.add_argument("--mode", default="")
    assemble.add_argument("--pr-number", default="")
    assemble.add_argument("--output", default="")
    assemble.add_argument("--task-appendix-file", default="")
    assemble.add_argument("--reference-pack-name", default="")
    assemble.add_argument("--materialize-reference-packs", action="store_true")
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
    complete.set_defaults(func=_cmd_record_completion)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
