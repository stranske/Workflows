#!/usr/bin/env python3
"""Require a receiving disposition when an entire sync target stops being managed."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from scripts.sync_manifest_compiler import COPY_SYNCED_SECTIONS, _safe_relative_path


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = yaml.safe_load(path.read_bytes())
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError(f"{path}: expected a version 1 sync manifest")
    return manifest


def declared_targets(manifest: dict[str, Any], section: str, field: str) -> set[str]:
    entries = manifest.get(section, [])
    if not isinstance(entries, list):
        raise ValueError(f"{section} must be a list")
    targets = set()
    for index, entry in enumerate(entries):
        context = f"{section}[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{context} must be a mapping")
        value = entry.get(field, entry.get("source") if section in COPY_SYNCED_SECTIONS else None)
        target, error = _safe_relative_path(value, field, context)
        if error:
            raise ValueError(error)
        if section == "excluded":
            reason = entry.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"{context}: exclusion for {target!r} needs a reason")
        targets.add(target)
    return targets


def copy_targets(manifest: dict[str, Any]) -> set[str]:
    return {
        target
        for section in COPY_SYNCED_SECTIONS
        for target in declared_targets(manifest, section, "target")
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        base = load_manifest(args.base_manifest)
        current = load_manifest(args.manifest)
        departed = copy_targets(base) - copy_targets(current)
        dispositions = declared_targets(current, "removals", "target") | declared_targets(
            current, "excluded", "path"
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Cannot validate managed sync target dispositions: {exc}")
        return 1
    unaccounted = departed - dispositions
    for target in sorted(unaccounted):
        print(
            f"Managed sync target {target!r} disappeared without a disposition. "
            "Add its exact path to removals or to excluded with a reason."
        )
    if unaccounted:
        return 1
    print(f"Validated dispositions for {len(departed)} departed managed sync target(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
