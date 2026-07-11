#!/usr/bin/env python3
"""Typed, deterministic compiler for .github/sync-manifest.yml.

Parses the raw YAML manifest into fully-validated, normalized dataclass objects.
Invalid entries (missing source, unknown sync_mode, malformed skip_repos, etc.)
raise ManifestCompileError before any consumer mutation can happen.

Usage as a library::

    from pathlib import Path
    from sync_manifest_compiler import compile_manifest

    compiled = compile_manifest(Path(".github/sync-manifest.yml"))
    for entry in compiled.section("workflows"):
        print(entry.source, entry.target, entry.sync_mode)

Usage as a CLI validator (exits 0 for valid, 1 for invalid)::

    python scripts/sync_manifest_compiler.py --validate .github/sync-manifest.yml
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ALLOWED_SYNC_MODES: frozenset[str] = frozenset({"create_only"})
ALLOWED_TEMPLATE_SYNC: frozenset[str] = frozenset({"exact"})

COPY_SYNCED_SECTIONS: tuple[str, ...] = (
    "workflows",
    "prompts",
    "scripts",
    "codex_config",
    "copilot_config",
    "templates",
    "actions",
    "docs",
    "llm_config",
    "git_config",
    "issue_templates",
    "user_docs",
)


class ManifestCompileError(ValueError):
    """Raised when the manifest contains one or more validation errors."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        lines = "\n".join(f"  - {p}" for p in self.problems)
        super().__init__(f"{len(self.problems)} manifest validation error(s):\n{lines}")


@dataclass(frozen=True)
class SkipRepo:
    """A repo-specific skip rule from skip_repos."""

    repo: str
    reason: str


@dataclass(frozen=True)
class ManifestEntry:
    """Normalized, validated representation of one sync-manifest entry."""

    source: str
    target: str
    description: str
    sync_mode: str | None
    skip_repos: tuple[SkipRepo, ...]
    overwrite_repos: tuple[str, ...]
    is_directory: bool
    template_sync: str | None
    section: str


@dataclass(frozen=True)
class RemovalEntry:
    """Normalized, validated representation of one removals entry."""

    target: str
    description: str


class CompiledManifest:
    """Result of compiling a sync-manifest YAML file."""

    def __init__(
        self,
        version: int,
        sections: dict[str, list[ManifestEntry]],
        removals: list[RemovalEntry],
    ) -> None:
        self.version = version
        self._sections: dict[str, tuple[ManifestEntry, ...]] = {
            k: tuple(v) for k, v in sections.items()
        }
        self.removals: tuple[RemovalEntry, ...] = tuple(removals)

    def section(self, name: str) -> tuple[ManifestEntry, ...]:
        """Return compiled entries for a manifest section, or () if absent."""
        return self._sections.get(name, ())

    def all_entries(self) -> list[ManifestEntry]:
        """Return all entries across all sections."""
        result: list[ManifestEntry] = []
        for entries in self._sections.values():
            result.extend(entries)
        return result


def _parse_skip_repos(raw: object, context: str) -> tuple[SkipRepo, ...] | str:
    """Return a tuple of SkipRepo or an error string."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return f"{context}: skip_repos must be a list, got {type(raw).__name__}"
    result: list[SkipRepo] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            result.append(SkipRepo(repo=item.strip(), reason=""))
            continue
        if isinstance(item, dict):
            repo = item.get("repo")
            if not repo or not isinstance(repo, str) or not repo.strip():
                return (
                    f"{context}: skip_repos[{index}] dict must have a non-empty 'repo' field"
                )
            reason = str(item.get("reason", "")).strip()
            result.append(SkipRepo(repo=repo.strip(), reason=reason))
            continue
        return (
            f"{context}: skip_repos[{index}] must be a string or dict,"
            f" got {type(item).__name__}"
        )
    return tuple(result)


def _parse_overwrite_repos(raw: object, context: str) -> tuple[str, ...] | str:
    """Return a tuple of repo strings or an error string."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return (
            f"{context}: overwrite_repos must be a list, got {type(raw).__name__}"
        )
    result: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str):
            return (
                f"{context}: overwrite_repos[{index}] must be a string,"
                f" got {type(item).__name__}"
            )
        result.append(item)
    return tuple(result)


def _compile_entry(
    raw: object,
    section: str,
    index: int,
    problems: list[str],
) -> ManifestEntry | None:
    """Try to compile one raw manifest entry; append to problems on failure."""
    context = f"section '{section}', entry {index}"

    if not isinstance(raw, dict):
        problems.append(f"{context}: entry must be a mapping, got {type(raw).__name__}")
        return None

    source = raw.get("source")
    if not source or not isinstance(source, str) or not source.strip():
        problems.append(f"{context}: 'source' must be a non-empty string")
        return None
    source = source.strip()
    target = str(raw.get("target", source)).strip() or source

    description = str(raw.get("description", "")).strip()

    sync_mode_raw = raw.get("sync_mode")
    if sync_mode_raw is None:
        sync_mode: str | None = None
    elif isinstance(sync_mode_raw, str) and sync_mode_raw in ALLOWED_SYNC_MODES:
        sync_mode = sync_mode_raw
    else:
        problems.append(
            f"{context} (source={source!r}): sync_mode {sync_mode_raw!r}"
            f" is not allowed; expected one of {sorted(ALLOWED_SYNC_MODES)}"
        )
        return None

    skip_repos_result = _parse_skip_repos(raw.get("skip_repos"), context)
    if isinstance(skip_repos_result, str):
        problems.append(skip_repos_result)
        return None
    skip_repos = skip_repos_result

    overwrite_repos_result = _parse_overwrite_repos(raw.get("overwrite_repos"), context)
    if isinstance(overwrite_repos_result, str):
        problems.append(overwrite_repos_result)
        return None
    overwrite_repos = overwrite_repos_result

    is_directory_raw = raw.get("is_directory")
    if is_directory_raw is None:
        is_directory = False
    elif isinstance(is_directory_raw, bool):
        is_directory = is_directory_raw
    else:
        problems.append(
            f"{context} (source={source!r}): is_directory must be a boolean,"
            f" got {type(is_directory_raw).__name__}"
        )
        return None

    template_sync_raw = raw.get("template_sync")
    if template_sync_raw is None:
        template_sync: str | None = None
    elif isinstance(template_sync_raw, str) and template_sync_raw in ALLOWED_TEMPLATE_SYNC:
        template_sync = template_sync_raw
    else:
        problems.append(
            f"{context} (source={source!r}): template_sync {template_sync_raw!r}"
            f" is not allowed; expected one of {sorted(ALLOWED_TEMPLATE_SYNC)}"
        )
        return None

    return ManifestEntry(
        source=source,
        target=target,
        description=description,
        sync_mode=sync_mode,
        skip_repos=skip_repos,
        overwrite_repos=overwrite_repos,
        is_directory=is_directory,
        template_sync=template_sync,
        section=section,
    )


def _compile_removal(raw: object, index: int, problems: list[str]) -> RemovalEntry | None:
    """Try to compile one raw removals entry; append to problems on failure."""
    context = f"removals entry {index}"
    if not isinstance(raw, dict):
        problems.append(f"{context}: entry must be a mapping, got {type(raw).__name__}")
        return None
    target = raw.get("target")
    if not target or not isinstance(target, str) or not target.strip():
        problems.append(f"{context}: 'target' must be a non-empty string")
        return None
    description = str(raw.get("description", "")).strip()
    return RemovalEntry(target=target.strip(), description=description)


def compile_manifest(path: Path) -> CompiledManifest:
    """Parse and validate a sync-manifest YAML file.

    Raises ManifestCompileError if any entry is invalid.
    Raises FileNotFoundError if the file does not exist.
    """
    raw_yaml = path.read_text(encoding="utf-8")
    data: object = yaml.safe_load(raw_yaml)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ManifestCompileError([f"Manifest root must be a mapping, got {type(data).__name__}"])

    version_raw = data.get("version", 1)
    try:
        version = int(version_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        version = 1

    problems: list[str] = []
    sections: dict[str, list[ManifestEntry]] = {}

    for key, value in data.items():
        if key in ("version", "removals", "excluded", "runtime_fetched"):
            continue
        if not isinstance(value, list):
            continue
        entries: list[ManifestEntry] = []
        for index, raw_entry in enumerate(value):
            entry = _compile_entry(raw_entry, key, index, problems)
            if entry is not None:
                entries.append(entry)
        sections[key] = entries

    removals: list[RemovalEntry] = []
    raw_removals = data.get("removals")
    if isinstance(raw_removals, list):
        for index, raw_entry in enumerate(raw_removals):
            removal = _compile_removal(raw_entry, index, problems)
            if removal is not None:
                removals.append(removal)

    if problems:
        raise ManifestCompileError(problems)

    return CompiledManifest(version=version, sections=sections, removals=removals)


def _cli_validate(path: Path) -> int:
    """Validate a manifest file; return 0 for valid, 1 for invalid."""
    if not path.exists():
        print(f"::error::Manifest file not found: {path}", file=sys.stderr)
        return 1
    try:
        compiled = compile_manifest(path)
        total = sum(len(compiled.section(s)) for s in COPY_SYNCED_SECTIONS)
        total += len(compiled.removals)
        print(
            f"✅ Manifest valid: {total} entries across"
            f" {len([s for s in COPY_SYNCED_SECTIONS if compiled.section(s)])} sections,"
            f" {len(compiled.removals)} removals"
        )
        return 0
    except ManifestCompileError as exc:
        print(f"❌ Manifest invalid:\n{exc}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a sync-manifest YAML file against the typed schema."
    )
    parser.add_argument("--validate", metavar="PATH", help="Manifest file to validate")
    args = parser.parse_args()

    if args.validate:
        return _cli_validate(Path(args.validate))

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
