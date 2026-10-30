#!/usr/bin/env python3
"""Deliver the manifest-declared hub scripts and removals to the integration repo.

``maint-69-sync-integration-repo`` copies a hand-picked set of workflows into
``stranske/Workflows-Integration-Tests`` (WIT). WIT is not in the maint-68
consumer matrix, so nothing else delivers the ``.github/scripts/*`` files those
workflows ``require()`` at runtime, and nothing removes workflows the manifest
retired. The result, measured 2026-10-30 against WIT main: ``Agents Gate
Followups`` failed with ``Cannot find module .github/scripts/runtime_ac_merge_guard.js``
and ``createTokenAwareRetry is not a function`` (a January copy of
``github-api-with-retry.js``), the retired ``agents-autofix-loop.yml`` ended in
``startup_failure``, and a January copy of ``maint-coverage-guard.yml`` failed
with a shell syntax error.

This helper applies the SAME manifest entries to WIT that maint-68 applies to a
consumer, restricted to the surfaces WIT can take without a template of its own:

* ``source`` entries under ``.github/scripts/`` (scripts and JSON dependencies), and
* the ``maint-coverage-guard.yml`` workflow (an intentional full-workflow sync), and
* ``removals`` that name a file under ``.github/workflows/`` or ``.github/scripts/``.

Stdlib + PyYAML only, so maint-69 can run it without installing extras.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

DEFAULT_REPO = "stranske/Workflows-Integration-Tests"
SCRIPT_PREFIX = ".github/scripts/"
SCRIPT_SUFFIXES = frozenset({".js", ".cjs", ".mjs", ".py", ".json"})
EXTRA_WORKFLOW_SOURCES = frozenset({".github/workflows/maint-coverage-guard.yml"})
ACTION_DIRECTORIES = frozenset({".github/actions/setup-api-client"})
REMOVAL_PREFIXES = (".github/workflows/", ".github/scripts/")


@dataclass
class SyncResult:
    """Outcome of one apply run, split so a drained run is distinguishable from a failed one."""

    copied: list[str] = field(default_factory=list)  # content changed or file created
    unchanged: list[str] = field(default_factory=list)  # already identical
    removed: list[str] = field(default_factory=list)  # existed and was deleted
    absent: list[str] = field(default_factory=list)  # removal target already gone
    missing_sources: list[str] = field(default_factory=list)  # manifest names a file that is absent

    @property
    def ok(self) -> bool:
        return not self.missing_sources


def _is_safe_relative(path: str) -> bool:
    posix = PurePosixPath(path)
    return bool(path) and not posix.is_absolute() and ".." not in posix.parts


def _select_copy_entries(manifest: dict[str, Any], repo: str) -> list[tuple[str, str]]:
    """Select paths together with their declared source tree, without fallback."""
    selected: list[tuple[str, str]] = []
    seen: set[str] = set()
    for section in ("scripts", "workflows"):
        for entry in manifest.get(section) or []:
            source = str(entry.get("source") or "")
            if not source or source in seen or not _is_safe_relative(source):
                continue
            if entry.get("is_directory") or entry.get("delivery", "copy") != "copy":
                continue
            skipped = {
                item.get("repo") if isinstance(item, dict) else item
                for item in entry.get("skip_repos") or []
            }
            if repo in skipped:
                continue
            include = entry.get("include_repos") or []
            if include and repo not in include:
                continue
            posix = PurePosixPath(source)
            is_script = (
                source.startswith(SCRIPT_PREFIX)
                and posix.suffix in SCRIPT_SUFFIXES
                and "node_modules" not in posix.parts
            )
            if is_script or source in EXTRA_WORKFLOW_SOURCES:
                source_tree = entry.get(
                    "source_tree", "root" if section == "scripts" else "template"
                )
                if source_tree not in {"root", "template"}:
                    raise ValueError(f"unsupported source_tree {source_tree!r} for {source}")
                seen.add(source)
                selected.append((source, source_tree))
    return selected


def select_copy_sources(manifest: dict[str, Any], repo: str = DEFAULT_REPO) -> list[str]:
    """Manifest ``source`` paths this helper delivers to ``repo``, in manifest order."""
    return [source for source, _tree in _select_copy_entries(manifest, repo)]


def select_action_directories(manifest: dict[str, Any], repo: str = DEFAULT_REPO) -> list[str]:
    """Manifest ``actions`` directories delivered to ``repo``.

    The delivered ``maint-coverage-guard.yml`` runs ``uses: ./.github/actions/setup-api-client``,
    and a local composite action must exist in the consuming repo.
    """
    selected: list[str] = []
    for entry in manifest.get("actions") or []:
        source = str(entry.get("source") or "").rstrip("/")
        if source not in ACTION_DIRECTORIES or not entry.get("is_directory"):
            continue
        skipped = {
            item.get("repo") if isinstance(item, dict) else item
            for item in entry.get("skip_repos") or []
        }
        include = entry.get("include_repos") or []
        if repo in skipped or (include and repo not in include):
            continue
        if source not in selected:
            selected.append(source)
    return selected


def select_removals(manifest: dict[str, Any]) -> list[str]:
    """Manifest ``removals`` targets that are single files this helper may delete."""
    targets: list[str] = []
    for entry in manifest.get("removals") or []:
        target = str(entry.get("target") or "")
        if _is_safe_relative(target) and target.startswith(REMOVAL_PREFIXES):
            targets.append(target)
    return targets


def apply_subset(
    manifest: dict[str, Any],
    source_root: Path,
    target_root: Path,
    *,
    repo: str = DEFAULT_REPO,
    dry_run: bool = False,
) -> SyncResult:
    """Copy selected sources into ``target_root`` and delete retired targets."""
    result = SyncResult()
    for source, source_tree in _select_copy_entries(manifest, repo):
        root = source_root if source_tree == "root" else source_root / "templates/consumer-repo"
        src = root / source
        if not src.is_file():
            result.missing_sources.append(source)
            continue
        dest = target_root / source
        if dest.is_file() and dest.read_bytes() == src.read_bytes():
            result.unchanged.append(source)
            continue
        result.copied.append(source)
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            shutil.copymode(src, dest)
    for directory in select_action_directories(manifest, repo):
        src_dir = source_root / directory
        if not src_dir.is_dir():
            result.missing_sources.append(directory)
            continue
        for src in sorted(p for p in src_dir.rglob("*") if p.is_file()):
            if "node_modules" in src.relative_to(src_dir).parts:
                continue
            rel = src.relative_to(source_root).as_posix()
            dest = target_root / rel
            if dest.is_file() and dest.read_bytes() == src.read_bytes():
                result.unchanged.append(rel)
                continue
            result.copied.append(rel)
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                shutil.copymode(src, dest)
    for target in select_removals(manifest):
        dest = target_root / target
        if dest.is_file():
            result.removed.append(target)
            if not dry_run:
                dest.unlink()
        else:
            result.absent.append(target)
    return result


def render_summary(result: SyncResult) -> str:
    """Report every count, including zeros, so a drained run reads as drained."""
    lines = [
        f"copied={len(result.copied)} unchanged={len(result.unchanged)} "
        f"removed={len(result.removed)} already_absent={len(result.absent)} "
        f"missing_sources={len(result.missing_sources)}"
    ]
    lines.extend(f"  copied   {path}" for path in result.copied)
    lines.extend(f"  removed  {path}" for path in result.removed)
    lines.extend(f"  MISSING  {path}" for path in result.missing_sources)
    if result.ok and not result.copied and not result.removed:
        lines.append("fully drained: integration repo already matches the manifest subset")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True, help="Workflows checkout")
    parser.add_argument("--target-root", type=Path, required=True, help="integration repo checkout")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8")) or {}
    result = apply_subset(
        manifest, args.source_root, args.target_root, repo=args.repo, dry_run=args.dry_run
    )
    print(render_summary(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
