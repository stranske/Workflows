#!/usr/bin/env python3
"""Merge integration-template coverage omit patterns into a consumer pyproject.

``maint-69-sync-integration-repo`` pin-syncs ``pyproject.toml`` but does not
replace the file. Integration-Tests therefore keeps a consumer-owned
``[tool.coverage.run]`` table. Full-coverage jobs measure imported synced
``scripts/`` / ``tools/`` boilerplate and fail the reusable 70% floor unless
those paths stay omitted.

This helper merges omit entries from the integration template (source of truth)
into the consumer pyproject while preserving other keys such as ``branch``.

Stdlib-only (no tomlkit) so maint-69 can run it without installing extras.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python <3.11
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parent.parent / "templates" / "integration-repo" / "pyproject.toml"
)

_OMIT_BLOCK_RE = re.compile(
    r"(?P<prefix>^omit\s*=\s*)(?P<body>\[[^\]]*\])",
    re.MULTILINE | re.DOTALL,
)
_COVERAGE_RUN_HEADER_RE = re.compile(r"^\[tool\.coverage\.run\]\s*$", re.MULTILINE)


def _coverage_omit(document: dict[str, Any]) -> list[str]:
    tool = document.get("tool")
    if not isinstance(tool, dict):
        return []
    coverage = tool.get("coverage")
    if not isinstance(coverage, dict):
        return []
    run = coverage.get("run")
    if not isinstance(run, dict):
        return []
    omit = run.get("omit")
    if not isinstance(omit, list):
        return []
    return [str(item) for item in omit]


def required_omit_patterns(template_path: Path) -> list[str]:
    """Return omit patterns declared by the integration template."""
    data = tomllib.loads(template_path.read_text(encoding="utf-8"))
    patterns = _coverage_omit(data)
    if not patterns:
        raise SystemExit(f"template {template_path} has no [tool.coverage.run] omit entries")
    return patterns


def merge_omit_patterns(existing: list[str], required: list[str]) -> list[str]:
    """Union required patterns into existing, preserving order and uniqueness."""
    seen: set[str] = set()
    merged: list[str] = []
    for item in [*existing, *required]:
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _format_omit_array(patterns: list[str]) -> str:
    inner = ",\n".join(f'    "{item}"' for item in patterns)
    return f"[\n{inner},\n]"


def _replace_or_insert_omit(content: str, patterns: list[str]) -> str:
    formatted = _format_omit_array(patterns)
    match = _OMIT_BLOCK_RE.search(content)
    if match:
        return content[: match.start()] + match.group("prefix") + formatted + content[match.end() :]

    header = _COVERAGE_RUN_HEADER_RE.search(content)
    if header:
        insert_at = header.end()
        return content[:insert_at] + f"\nomit = {formatted}" + content[insert_at:]

    block = f"\n[tool.coverage.run]\nomit = {formatted}\n"
    return content.rstrip() + "\n" + block


def apply_coverage_omit(target_path: Path, required: list[str], *, apply: bool) -> list[str]:
    """Ensure ``required`` omit patterns exist in ``target_path``.

    Returns the list of patterns that were missing before the merge.
    """
    text = target_path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    existing = _coverage_omit(data)
    merged = merge_omit_patterns(existing, required)
    missing = [item for item in required if item not in existing]
    if not missing:
        return []

    if not apply:
        return missing

    updated = _replace_or_insert_omit(text, merged)
    # Validate round-trip before writing.
    parsed = tomllib.loads(updated)
    if _coverage_omit(parsed) != merged:
        raise SystemExit(f"failed to merge coverage omit into {target_path}")
    target_path.write_text(updated, encoding="utf-8")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge integration-template coverage omit patterns into a pyproject.toml"
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Path to templates/integration-repo/pyproject.toml",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        required=True,
        help="Consumer pyproject.toml to update",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write merged omit patterns (default: report only)",
    )
    args = parser.parse_args(argv)

    if not args.template.is_file():
        print(f"template not found: {args.template}", file=sys.stderr)
        return 2
    if not args.pyproject.is_file():
        print(f"pyproject not found: {args.pyproject}", file=sys.stderr)
        return 2

    required = required_omit_patterns(args.template)
    missing = apply_coverage_omit(args.pyproject, required, apply=args.apply)
    if not missing:
        print(f"✅ Coverage omit already includes template patterns in {args.pyproject}")
        return 0

    action = "Applied" if args.apply else "Would apply"
    print(f"{action} coverage omit patterns to {args.pyproject}: {', '.join(missing)}")
    return 0 if args.apply else 1


if __name__ == "__main__":
    raise SystemExit(main())
