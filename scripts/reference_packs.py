#!/usr/bin/env python3
"""Utilities for loading and validating reference pack configuration."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_RELPATH = ".github/reference_packs.json"
PACK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class ReferencePackConfigError(ValueError):
    """Raised when reference pack configuration is invalid."""


@dataclass(frozen=True)
class ReferencePack:
    """A single reference pack configuration entry."""

    name: str
    repo: str
    ref: str
    paths: list[str]


@dataclass(frozen=True)
class ReferencePackSnapshot:
    """Loaded reference pack state for a workspace."""

    exists: bool
    config_path: Path
    config_text: str | None
    packs: list[ReferencePack]


@dataclass(frozen=True)
class ReferencePackCheckoutPlan:
    """Workflow-ready checkout plan derived from validated pack config."""

    name: str
    repo: str
    ref: str
    paths: list[str]
    checkout_path: str


def reference_pack_config_path(workspace: Path | str = ".") -> Path:
    """Return the absolute path to the reference pack config file."""
    return Path(workspace).resolve() / DEFAULT_CONFIG_RELPATH


def reference_pack_config_exists(workspace: Path | str = ".") -> bool:
    """Return whether `.github/reference_packs.json` exists in the workspace."""
    return reference_pack_config_path(workspace).is_file()


def read_reference_pack_config_text(workspace: Path | str = ".") -> tuple[Path, str | None]:
    """Read `.github/reference_packs.json` from a workspace when it exists."""
    config_path = reference_pack_config_path(workspace)
    if not config_path.is_file():
        return config_path, None

    try:
        return config_path, config_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ReferencePackConfigError(
            f"Malformed text in {config_path}: file must be valid UTF-8"
        ) from exc


def _require_nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReferencePackConfigError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_repo(repo: str) -> str:
    if "/" not in repo or repo.startswith("/") or repo.endswith("/"):
        raise ReferencePackConfigError("repo must use owner/name format")
    return repo


def _validate_paths(raw_paths: Any) -> list[str]:
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ReferencePackConfigError("paths must be a non-empty array of strings")

    validated: list[str] = []
    for entry in raw_paths:
        path = _require_nonempty_string(entry, "paths[]")
        if path.startswith("/"):
            raise ReferencePackConfigError("paths[] must be relative, not absolute")
        if ".." in path.split("/"):
            raise ReferencePackConfigError("paths[] must not traverse parent directories")
        validated.append(path)

    return validated


def _build_pack(name: str, payload: Any) -> ReferencePack:
    normalized_name = _require_nonempty_string(name, "pack name")
    if not PACK_NAME_PATTERN.fullmatch(normalized_name):
        raise ReferencePackConfigError(
            "pack name may only contain letters, numbers, '.', '_', and '-'"
        )
    if not isinstance(payload, dict):
        raise ReferencePackConfigError(f"pack '{normalized_name}' must be a JSON object")

    repo = _validate_repo(_require_nonempty_string(payload.get("repo"), "repo"))
    ref = _require_nonempty_string(payload.get("ref"), "ref")
    paths = _validate_paths(payload.get("paths"))
    return ReferencePack(name=normalized_name, repo=repo, ref=ref, paths=paths)


def parse_reference_packs(payload: Any) -> list[ReferencePack]:
    """Parse reference packs from decoded JSON payload.

    Accepted formats:
    - Mapping format: {"pack_name": {"repo": ..., "ref": ..., "paths": [...]}}
    - List format: {"packs": [{"name": ..., "repo": ..., "ref": ..., "paths": [...]}]}
    """
    if not isinstance(payload, dict):
        raise ReferencePackConfigError("reference_packs.json must contain a JSON object")

    if "packs" in payload:
        extra_keys = sorted(str(key) for key in payload if key != "packs")
        if extra_keys:
            extras = ", ".join(extra_keys)
            raise ReferencePackConfigError(
                f"when using 'packs' format, no additional top-level keys are allowed: {extras}"
            )
        packs_node = payload["packs"]
        if not isinstance(packs_node, list):
            raise ReferencePackConfigError("packs must be an array")
        packs: list[ReferencePack] = []
        for index, entry in enumerate(packs_node):
            if not isinstance(entry, dict):
                raise ReferencePackConfigError(f"packs[{index}] must be an object")
            name = _require_nonempty_string(entry.get("name"), f"packs[{index}].name")
            packs.append(_build_pack(name, entry))
    else:
        packs = [_build_pack(name, item) for name, item in payload.items()]

    seen_names: set[str] = set()
    for pack in packs:
        if pack.name in seen_names:
            raise ReferencePackConfigError(f"duplicate pack name: {pack.name}")
        seen_names.add(pack.name)

    return packs


def parse_reference_pack_config_text(config_text: str, config_path: Path) -> list[ReferencePack]:
    """Parse and validate reference packs from raw JSON text."""
    try:
        payload = json.loads(config_text)
    except json.JSONDecodeError as exc:
        raise ReferencePackConfigError(
            f"Malformed JSON in {config_path}: line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc

    try:
        return parse_reference_packs(payload)
    except ReferencePackConfigError as exc:
        raise ReferencePackConfigError(f"Invalid config in {config_path}: {exc}") from exc


def load_reference_packs(workspace: Path | str = ".") -> ReferencePackSnapshot:
    """Load and validate reference pack configuration from a workspace."""
    config_path, config_text = read_reference_pack_config_text(workspace)
    if config_text is None:
        return ReferencePackSnapshot(
            exists=False, config_path=config_path, config_text=None, packs=[]
        )

    packs = parse_reference_pack_config_text(config_text, config_path)

    return ReferencePackSnapshot(
        exists=True, config_path=config_path, config_text=config_text, packs=packs
    )


def build_checkout_plan(packs: list[ReferencePack]) -> list[ReferencePackCheckoutPlan]:
    """Build a stable, workflow-ready checkout plan for reference packs."""
    return [
        ReferencePackCheckoutPlan(
            name=pack.name,
            repo=pack.repo,
            ref=pack.ref,
            paths=pack.paths,
            checkout_path=f".reference/{pack.name}",
        )
        for pack in packs
    ]


def _snapshot_to_dict(snapshot: ReferencePackSnapshot) -> dict[str, Any]:
    checkout_plan = build_checkout_plan(snapshot.packs)
    return {
        "exists": snapshot.exists,
        "config_path": str(snapshot.config_path),
        "config_text": snapshot.config_text,
        "packs": [asdict(pack) for pack in snapshot.packs],
        "checkout_plan": [asdict(plan_entry) for plan_entry in checkout_plan],
    }


def _github_output_value(value: str) -> str:
    """Escape output values to avoid multi-line output parsing issues."""
    return value.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read and validate .github/reference_packs.json")
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root that may contain .github/reference_packs.json",
    )
    parser.add_argument(
        "--format",
        choices=["json", "github-output", "self-check"],
        default="json",
        help="Output format",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        snapshot = load_reference_packs(args.workspace)
    except ReferencePackConfigError as exc:
        print(f"Reference packs config error: {exc}", file=sys.stderr)
        return 2

    payload = _snapshot_to_dict(snapshot)
    if args.format == "json":
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    if args.format == "self-check":
        if not snapshot.exists:
            print(
                f"Reference packs self-check: skipped ({snapshot.config_path} not found).",
                file=sys.stderr,
            )
            return 0
        print(
            "Reference packs self-check: OK "
            f"({len(snapshot.packs)} pack(s) validated from {snapshot.config_path}).",
            file=sys.stderr,
        )
        return 0

    github_output_raw = os.environ.get("GITHUB_OUTPUT")
    if not github_output_raw:
        print("Reference packs config error: GITHUB_OUTPUT is not set", file=sys.stderr)
        return 2
    github_output = Path(github_output_raw)

    canonical_payload_json = json.dumps(payload, separators=(",", ":"))
    checkout_plan_json = json.dumps(
        [asdict(plan_entry) for plan_entry in build_checkout_plan(snapshot.packs)],
        separators=(",", ":"),
    )
    config_text_b64 = (
        base64.b64encode((snapshot.config_text or "").encode("utf-8")).decode("ascii")
        if snapshot.exists
        else ""
    )
    lines = [
        f"reference_packs_exists={'true' if snapshot.exists else 'false'}",
        f"reference_packs_path={snapshot.config_path}",
        f"reference_packs_count={len(snapshot.packs)}",
        f"reference_packs_json={json.dumps([asdict(pack) for pack in snapshot.packs], separators=(',', ':'))}",
        f"reference_packs_payload_json={_github_output_value(canonical_payload_json)}",
        f"reference_packs_checkout_plan_json={_github_output_value(checkout_plan_json)}",
        f"reference_packs_config_text={_github_output_value(snapshot.config_text or '')}",
        f"reference_packs_config_text_b64={config_text_b64}",
    ]
    github_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
