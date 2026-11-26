#!/usr/bin/env python3
"""Require a receiving disposition when an entire sync target stops being managed."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml
from scripts.sync_manifest_compiler import COPY_SYNCED_SECTIONS, _safe_relative_path


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = yaml.safe_load(path.read_bytes())
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError(f"{path}: expected a version 1 sync manifest")
    return manifest


def manifest_entries(
    manifest: dict[str, Any], section: str
) -> Iterator[tuple[str, dict[str, Any]]]:
    entries = manifest.get(section, [])
    if not isinstance(entries, list):
        raise ValueError(f"{section} must be a list")
    for index, entry in enumerate(entries):
        context = f"{section}[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{context} must be a mapping")
        yield context, entry


def destination(value: Any, field: str, context: str) -> str:
    target, error = _safe_relative_path(value, field, context)
    if error:
        raise ValueError(error)
    return target


def declared_dispositions(manifest: dict[str, Any], section: str, field: str) -> set[str]:
    targets = set()
    for context, entry in manifest_entries(manifest, section):
        target = destination(entry.get(field), field, context)
        if section == "excluded":
            reason = entry.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"{context}: exclusion for {target!r} needs a reason")
        targets.add(target)
    return targets


def copy_targets(manifest: dict[str, Any]) -> dict[str, bool]:
    return {
        destination(entry.get("target", entry.get("source")), "target", context): (
            entry.get("is_directory") is True
        )
        for section in COPY_SYNCED_SECTIONS
        for context, entry in manifest_entries(manifest, section)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        base = load_manifest(args.base_manifest)
        current = load_manifest(args.manifest)
        old_targets = copy_targets(base)
        new_targets = copy_targets(current)
        removals = declared_dispositions(current, "removals", "target")
        exclusions = declared_dispositions(current, "excluded", "path")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Cannot validate managed sync target dispositions: {exc}")
        return 1
    departed = old_targets.keys() - new_targets.keys()
    unaccounted = departed - removals - exclusions
    replacements = {
        target
        for target in old_targets.keys() & new_targets.keys()
        if old_targets[target] and not new_targets[target]
    }
    removed_children = [
        (target, child)
        for target in removals
        for child in new_targets
        if child.startswith(target + "/")
    ]
    for target in sorted(unaccounted):
        print(
            f"Managed sync target {target!r} disappeared without a disposition. "
            "Add its exact path to removals or to excluded with a reason."
        )
    for target in sorted(replacements):
        print(
            f"Managed sync directory {target!r} would be replaced by a file. "
            "Retire the directory and verify receiver removal before adding that file."
        )
    for target, child in sorted(removed_children):
        print(f"Removal {target!r} would also delete managed sync target {child!r}.")
    if unaccounted or replacements or removed_children:
        return 1
    print(f"Validated dispositions for {len(departed)} departed managed sync target(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
