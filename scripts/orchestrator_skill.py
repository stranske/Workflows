#!/usr/bin/env python3
"""Load, validate, and materialize exported Orchestrator skill context for remote Codex runs."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_RELPATH = ".github/orchestrator_skill.json"
SUMMARY_RELPATH = ".reference/ORCHESTRATOR_SKILL.md"
DEFAULT_CHECKOUT_PATH = ".reference/orchestrator-skill"
FORBIDDEN_PATH_MARKERS = (
    "/users/",
    "~/.codex",
    "/.codex/",
    "library/cloudstorage/dropbox/learning/code/orchestrator",
    "orchestrator/feedback",
    "orchestrator/brain",
)
FORBIDDEN_VALUE_MARKERS = (
    "/users/teacher/.codex",
    "library/cloudstorage/dropbox/learning/code/orchestrator",
)


class OrchestratorSkillConfigError(ValueError):
    """Raised when orchestrator skill configuration is invalid."""


@dataclass(frozen=True)
class OrchestratorSkillCheckoutPlan:
    """Workflow-ready checkout plan for exported Orchestrator skill material."""

    repo: str
    ref: str
    paths: list[str]
    checkout_path: str
    pack: str | None = None


@dataclass(frozen=True)
class OrchestratorSkillSnapshot:
    exists: bool
    enabled: bool
    config_path: Path
    config_text: str | None
    plan: OrchestratorSkillCheckoutPlan | None


def orchestrator_skill_config_path(workspace: Path | str = ".") -> Path:
    return Path(workspace).resolve() / DEFAULT_CONFIG_RELPATH


def orchestrator_skill_config_exists(workspace: Path | str = ".") -> bool:
    return orchestrator_skill_config_path(workspace).is_file()


def read_orchestrator_skill_config_text(
    workspace: Path | str = ".",
) -> tuple[Path, str | None]:
    config_path = orchestrator_skill_config_path(workspace)
    if not config_path.is_file():
        return config_path, None
    try:
        return config_path, config_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise OrchestratorSkillConfigError(
            f"Malformed text in {config_path}: file must be valid UTF-8"
        ) from exc


def _require_nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OrchestratorSkillConfigError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_repo(repo: str) -> str:
    if "/" not in repo or repo.startswith("/") or repo.endswith("/"):
        raise OrchestratorSkillConfigError("repo must use owner/name format")
    return repo


def _validate_paths(raw_paths: Any) -> list[str]:
    if not isinstance(raw_paths, list) or not raw_paths:
        raise OrchestratorSkillConfigError("paths must be a non-empty array of strings")

    validated: list[str] = []
    for entry in raw_paths:
        path = _require_nonempty_string(entry, "paths[]")
        lowered = path.lower()
        if any(marker in lowered for marker in FORBIDDEN_PATH_MARKERS):
            raise OrchestratorSkillConfigError(
                f"paths[] must not reference local Orchestrator runtime paths: {path}"
            )
        if path.startswith("/"):
            raise OrchestratorSkillConfigError("paths[] must be relative, not absolute")
        if ".." in path.split("/"):
            raise OrchestratorSkillConfigError("paths[] must not traverse parent directories")
        validated.append(path)
    return validated


def _reject_local_runtime_values(value: str, field_name: str) -> None:
    lowered = value.lower()
    if any(marker in lowered for marker in FORBIDDEN_VALUE_MARKERS):
        raise OrchestratorSkillConfigError(
            f"{field_name} must not reference local Orchestrator runtime paths"
        )


def _coerce_enabled(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise OrchestratorSkillConfigError("enabled must be a boolean")


def parse_orchestrator_skill_config(
    payload: Any,
) -> tuple[bool, OrchestratorSkillCheckoutPlan | None]:
    if not isinstance(payload, dict):
        raise OrchestratorSkillConfigError("orchestrator_skill.json must contain a JSON object")

    enabled = _coerce_enabled(payload.get("enabled"), default=True)
    if not enabled:
        return False, None

    pack = payload.get("pack")
    repo = payload.get("repo")
    ref = payload.get("ref")
    paths = payload.get("paths")

    has_pack = pack is not None
    has_inline = any(item is not None for item in (repo, ref, paths))
    if has_pack and has_inline:
        raise OrchestratorSkillConfigError("use either 'pack' or inline repo/ref/paths, not both")
    if not has_pack and not has_inline:
        raise OrchestratorSkillConfigError(
            "enabled orchestrator skill config requires 'pack' or inline repo/ref/paths"
        )

    if has_pack:
        pack_name = _require_nonempty_string(pack, "pack")
        _reject_local_runtime_values(pack_name, "pack")
        return True, OrchestratorSkillCheckoutPlan(
            repo="",
            ref="",
            paths=[],
            checkout_path=DEFAULT_CHECKOUT_PATH,
            pack=pack_name,
        )

    validated_repo = _validate_repo(_require_nonempty_string(repo, "repo"))
    validated_ref = _require_nonempty_string(ref, "ref")
    validated_paths = _validate_paths(paths)
    _reject_local_runtime_values(validated_repo, "repo")
    _reject_local_runtime_values(validated_ref, "ref")

    return True, OrchestratorSkillCheckoutPlan(
        repo=validated_repo,
        ref=validated_ref,
        paths=validated_paths,
        checkout_path=DEFAULT_CHECKOUT_PATH,
        pack=None,
    )


def parse_orchestrator_skill_config_text(
    config_text: str,
    config_path: Path,
) -> tuple[bool, OrchestratorSkillCheckoutPlan | None]:
    try:
        payload = json.loads(config_text)
    except json.JSONDecodeError as exc:
        raise OrchestratorSkillConfigError(
            f"Malformed JSON in {config_path}: line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc
    try:
        return parse_orchestrator_skill_config(payload)
    except OrchestratorSkillConfigError as exc:
        raise OrchestratorSkillConfigError(f"Invalid config in {config_path}: {exc}") from exc


def resolve_orchestrator_skill_plan(
    workspace: Path | str = ".",
    *,
    pack_override: str | None = None,
    enabled_override: bool | None = None,
) -> OrchestratorSkillCheckoutPlan | None:
    config_path, config_text = read_orchestrator_skill_config_text(workspace)
    enabled = False
    plan: OrchestratorSkillCheckoutPlan | None = None

    if config_text is not None:
        enabled, plan = parse_orchestrator_skill_config_text(config_text, config_path)
    elif pack_override:
        enabled = enabled_override is not False
        plan = OrchestratorSkillCheckoutPlan(
            repo="",
            ref="",
            paths=[],
            checkout_path=DEFAULT_CHECKOUT_PATH,
            pack=pack_override,
        )

    if enabled_override is not None:
        enabled = enabled_override

    if not enabled:
        return None

    if pack_override:
        if plan is None:
            plan = OrchestratorSkillCheckoutPlan(
                repo="",
                ref="",
                paths=[],
                checkout_path=DEFAULT_CHECKOUT_PATH,
                pack=pack_override,
            )
        else:
            plan = OrchestratorSkillCheckoutPlan(
                repo=plan.repo,
                ref=plan.ref,
                paths=list(plan.paths),
                checkout_path=plan.checkout_path,
                pack=pack_override,
            )

    return plan


def load_orchestrator_skill(
    workspace: Path | str = ".",
    *,
    pack_override: str | None = None,
    enabled_override: bool | None = None,
) -> OrchestratorSkillSnapshot:
    config_path, config_text = read_orchestrator_skill_config_text(workspace)
    plan = resolve_orchestrator_skill_plan(
        workspace,
        pack_override=pack_override,
        enabled_override=enabled_override,
    )
    enabled = plan is not None
    if config_text is None and enabled_override is False:
        enabled = False
    return OrchestratorSkillSnapshot(
        exists=config_text is not None,
        enabled=enabled,
        config_path=config_path,
        config_text=config_text,
        plan=plan,
    )


def build_orchestrator_skill_summary(
    checkout_path: Path,
    *,
    pack_name: str | None = None,
) -> str:
    files = sorted(
        path.relative_to(checkout_path).as_posix()
        for path in checkout_path.rglob("*")
        if path.is_file()
    )
    primary = files[0] if files else "(no files materialized)"
    pack_line = f"- **Reference pack:** `{pack_name}`\n" if pack_name else ""
    file_lines = "\n".join(f"- `{rel}`" for rel in files) or "- `(empty)`"
    return (
        "\n".join(
            [
                "This section provides **exported Orchestrator instructions** for remote Codex runs.",
                "It is **not** a live mount of the local Orchestrator Brain, feedback database, worktrees, or credentials.",
                "",
                "**Read and apply the materialized Orchestrator skill files before coordinating work.**",
                "Use the exported policy for decomposition and judgment only; do not attempt to access local Orchestrator runtime tools or state.",
                "",
                f"- **Location:** `{checkout_path.as_posix()}/`",
                pack_line.rstrip(),
                f"- **Primary entry point:** `{primary}`",
                "",
                "### Materialized files",
                file_lines,
            ]
        ).strip()
        + "\n"
    )


def write_orchestrator_skill_summary(
    workspace: Path | str,
    checkout_path: Path | str,
    *,
    pack_name: str | None = None,
) -> Path:
    workspace_path = Path(workspace).resolve()
    summary_path = workspace_path / SUMMARY_RELPATH
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        build_orchestrator_skill_summary(Path(checkout_path), pack_name=pack_name),
        encoding="utf-8",
    )
    return summary_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read and validate .github/orchestrator_skill.json"
    )
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument(
        "--format",
        choices=["json", "self-check"],
        default="json",
        help="Output format",
    )
    parser.add_argument(
        "--pack-override",
        default="",
        help="Optional reference-pack name override",
    )
    parser.add_argument(
        "--enabled-override",
        default="",
        help="Optional enabled override (true/false); empty means use repo config",
    )
    return parser


def _parse_enabled_override(raw: str) -> bool | None:
    normalized = raw.strip().lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise OrchestratorSkillConfigError("enabled override must be true or false")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    pack_override = args.pack_override.strip() or None
    enabled_override = _parse_enabled_override(args.enabled_override)

    try:
        snapshot = load_orchestrator_skill(
            args.workspace,
            pack_override=pack_override,
            enabled_override=enabled_override,
        )
    except OrchestratorSkillConfigError as exc:
        print(f"Orchestrator skill config error: {exc}", file=sys.stderr)
        return 2

    if args.format == "self-check":
        if not snapshot.exists:
            print(
                "Orchestrator skill self-check: skipped " f"({snapshot.config_path} not found).",
                file=sys.stderr,
            )
            return 0
        if not snapshot.enabled:
            print(
                "Orchestrator skill self-check: disabled " f"({snapshot.config_path}).",
                file=sys.stderr,
            )
            return 0
        print(
            "Orchestrator skill self-check: OK " f"(enabled from {snapshot.config_path}).",
            file=sys.stderr,
        )
        return 0

    payload = {
        "exists": snapshot.exists,
        "enabled": snapshot.enabled,
        "config_path": str(snapshot.config_path),
        "config_text": snapshot.config_text,
        "plan": asdict(snapshot.plan) if snapshot.plan else None,
    }
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
