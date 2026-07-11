#!/usr/bin/env python3
"""Compile the consumer sync manifest into one typed, deterministic plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

PLAN_SCHEMA = "workflows.consumer-sync-plan/v1"
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
ROOT_SOURCE_SECTIONS = {"scripts", "templates"}
TEMPLATE_SOURCE_SECTIONS = set(COPY_SYNCED_SECTIONS) - ROOT_SOURCE_SECTIONS
IGNORED_METADATA_SECTIONS = {"excluded", "runtime_fetched"}
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ManifestCompileError(ValueError):
    """The manifest cannot produce a safe, unambiguous sync plan."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(dict.fromkeys(problems))
        lines = "\n".join(f"  - {problem}" for problem in self.problems)
        super().__init__(f"{len(self.problems)} manifest validation error(s):\n{lines}")


@dataclass(frozen=True)
class SkipRepo:
    repo: str
    reason: str


@dataclass(frozen=True)
class ManifestEntry:
    source: str
    resolved_source: str
    target: str
    description: str
    sync_mode: str | None
    skip_repos: tuple[SkipRepo, ...]
    overwrite_repos: tuple[str, ...]
    is_directory: bool
    template_sync: str | None
    delivery: str
    section: str
    content_sha256: str
    effect_fingerprint: str

    def plan_record(self) -> dict[str, Any]:
        skip_reasons = {rule.repo: rule.reason for rule in self.skip_repos}
        return {
            "section": self.section,
            "source": self.source,
            "resolved_source": self.resolved_source,
            "target": self.target,
            "description": self.description,
            "sync_mode": self.sync_mode,
            "is_directory": self.is_directory,
            "skip_repos": [rule.repo for rule in self.skip_repos],
            "skip_reasons": skip_reasons,
            "overwrite_repos": list(self.overwrite_repos),
            "template_sync": self.template_sync,
            "delivery": self.delivery,
            "content_sha256": self.content_sha256,
            "effect_fingerprint": self.effect_fingerprint,
        }


@dataclass(frozen=True)
class RemovalEntry:
    target: str
    description: str
    effect_fingerprint: str

    def plan_record(self) -> dict[str, str]:
        return {
            "target": self.target,
            "description": self.description,
            "effect_fingerprint": self.effect_fingerprint,
        }


class CompiledManifest:
    def __init__(
        self,
        *,
        version: int,
        manifest_sha256: str,
        sections: dict[str, list[ManifestEntry]],
        removals: list[RemovalEntry],
    ) -> None:
        self.version = version
        self.manifest_sha256 = manifest_sha256
        self._sections = {section: tuple(entries) for section, entries in sections.items()}
        self.removals = tuple(removals)

    def section(self, name: str) -> tuple[ManifestEntry, ...]:
        return self._sections.get(name, ())

    def all_entries(self) -> list[ManifestEntry]:
        return [entry for section in COPY_SYNCED_SECTIONS for entry in self.section(section)]

    def to_plan(self) -> dict[str, Any]:
        core = {
            "schema": PLAN_SCHEMA,
            "version": 1,
            "manifest_sha256": self.manifest_sha256,
            "entries": [entry.plan_record() for entry in self.all_entries()],
            "removals": [removal.plan_record() for removal in self.removals],
        }
        return {
            **core,
            "plan_id": _stable_hash("consumer-sync-plan", core),
        }


def _stable_hash(namespace: str, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(namespace.encode() + b"\0" + encoded).hexdigest()


def _content_hash(path: Path) -> str:
    if path.is_file():
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    rows: list[dict[str, str]] = []
    for child in sorted(path.rglob("*")):
        if child.is_file():
            rows.append(
                {
                    "path": child.relative_to(path).as_posix(),
                    "sha256": hashlib.sha256(child.read_bytes()).hexdigest(),
                }
            )
    return _stable_hash("consumer-sync-directory", rows)


def _safe_relative_path(raw: Any, field: str, context: str) -> tuple[str, str | None]:
    if not isinstance(raw, str):
        return "", f"{context}: {field} must be a safe repository-relative path"
    value = raw.strip()
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or any(part in {".", ".."} for part in value.split("/"))
        or value.startswith("./")
        or "//" in value
    ):
        return value, f"{context}: {field} must be a safe repository-relative path"
    return path.as_posix(), None


def _parse_repo_list(raw: Any, *, field: str, context: str) -> tuple[tuple[str, ...], list[str]]:
    if raw is None:
        return (), []
    if not isinstance(raw, list):
        return (), [f"{context}: {field} must be a list"]
    values: list[str] = []
    errors: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not REPO_RE.fullmatch(item.strip()):
            errors.append(f"{context}: {field}[{index}] must be owner/repo")
            continue
        values.append(item.strip())
    if len(values) != len(set(values)):
        errors.append(f"{context}: {field} contains duplicate repositories")
    return tuple(values), errors


def _parse_skip_repos(raw: Any, *, context: str) -> tuple[tuple[SkipRepo, ...], list[str]]:
    if raw is None:
        return (), []
    if not isinstance(raw, list):
        return (), [f"{context}: skip_repos must be a list"]
    rules: list[SkipRepo] = []
    errors: list[str] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            repo, reason = item.strip(), ""
        elif isinstance(item, dict) and set(item) <= {"repo", "reason"}:
            repo = str(item.get("repo") or "").strip()
            reason = str(item.get("reason") or "").strip()
        else:
            errors.append(
                f"{context}: skip_repos[{index}] must be owner/repo or a repo/reason mapping"
            )
            continue
        if not REPO_RE.fullmatch(repo):
            errors.append(f"{context}: skip_repos[{index}].repo must be owner/repo")
            continue
        rules.append(SkipRepo(repo=repo, reason=reason))
    repos = [rule.repo for rule in rules]
    if len(repos) != len(set(repos)):
        errors.append(f"{context}: skip_repos contains duplicate repositories")
    return tuple(rules), errors


def _source_candidates(repo_root: Path, source: str, section: str) -> tuple[list[Path], str | None]:
    root = repo_root / source
    template = repo_root / "templates" / "consumer-repo" / source
    if section in ROOT_SOURCE_SECTIONS:
        return [root, template], None
    if section in TEMPLATE_SOURCE_SECTIONS:
        return [template, root], None
    return [template, root], f"unknown source ownership policy for section {section}"


def _resolve_source(
    *, repo_root: Path, source: str, section: str, context: str
) -> tuple[str, Path | None, list[str]]:
    candidates, policy_error = _source_candidates(repo_root, source, section)
    errors = [f"{context}: {policy_error}"] if policy_error else []
    existing = [candidate for candidate in candidates if candidate.exists()]
    if not existing:
        searched = ", ".join(
            candidate.relative_to(repo_root).as_posix() for candidate in candidates
        )
        return (
            "",
            None,
            [
                *errors,
                f"{context}: source {source!r} is not deliverable; searched {searched}",
            ],
        )
    root = repo_root.resolve()
    chosen = next(candidate for candidate in candidates if candidate.exists())
    try:
        chosen.resolve().relative_to(root)
    except ValueError:
        return "", None, [*errors, f"{context}: source {source!r} escapes repository root"]
    if chosen.is_dir():
        for child in chosen.rglob("*"):
            if not child.is_symlink():
                continue
            try:
                Path(os.path.realpath(child, strict=True)).relative_to(root)
            except (RuntimeError, ValueError):
                return (
                    "",
                    None,
                    [
                        *errors,
                        f"{context}: source {source!r} contains an invalid symlink",
                    ],
                )
            except OSError:
                return (
                    "",
                    None,
                    [
                        *errors,
                        f"{context}: source {source!r} contains an invalid symlink",
                    ],
                )
    return chosen.relative_to(repo_root).as_posix(), chosen, errors


def resolve_source_path(
    source: str, section: str | None, *, repo_root: Path = Path(".")
) -> Path | None:
    """Resolve one source using the compiler's canonical ownership policy.

    ``section=None`` preserves the drift checker's legacy compatibility lookup:
    prefer the consumer template and then fall back to the repository root.
    Manifest compilation always supplies a section and therefore remains bound
    to the explicit ownership policy.
    """
    source, error = _safe_relative_path(source, "source", "source resolution")
    if error:
        return None
    root = repo_root.resolve()
    if section is None:
        for candidate in (root / "templates" / "consumer-repo" / source, root / source):
            if candidate.exists() and candidate.resolve().is_relative_to(root):
                return candidate
        return None
    _resolved, path, errors = _resolve_source(
        repo_root=root,
        source=source,
        section=section,
        context=f"section '{section}'",
    )
    return None if errors else path


def _compile_entry(
    raw: Any,
    *,
    section: str,
    index: int,
    repo_root: Path,
) -> tuple[ManifestEntry | None, list[str]]:
    context = f"section '{section}', entry {index}"
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, [f"{context}: entry must be a mapping"]
    allowed = {
        "source",
        "target",
        "description",
        "sync_mode",
        "skip_repos",
        "overwrite_repos",
        "is_directory",
        "template_sync",
        "delivery",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        errors.append(f"{context}: unsupported fields {unknown}")
    source, source_error = _safe_relative_path(raw.get("source"), "source", context)
    if source_error:
        errors.append(source_error)
    target, error = _safe_relative_path(raw.get("target", source), "target", context)
    if error:
        errors.append(error)
    description = str(raw.get("description") or "").strip()
    if not description:
        errors.append(f"{context}: description must be non-empty")
    sync_mode = raw.get("sync_mode")
    if sync_mode is not None and sync_mode not in ALLOWED_SYNC_MODES:
        errors.append(f"{context}: sync_mode {sync_mode!r} is unsupported")
    template_sync = raw.get("template_sync")
    if template_sync is not None and template_sync not in ALLOWED_TEMPLATE_SYNC:
        errors.append(f"{context}: template_sync {template_sync!r} is unsupported")
    delivery = raw.get("delivery", "copy")
    if delivery != "copy":
        errors.append(f"{context}: copy-synced entry delivery must be 'copy'")
    is_directory = raw.get("is_directory", False)
    if not isinstance(is_directory, bool):
        errors.append(f"{context}: is_directory must be a boolean")
        is_directory = False
    skip_repos, skip_errors = _parse_skip_repos(raw.get("skip_repos"), context=context)
    overwrite_repos, overwrite_errors = _parse_repo_list(
        raw.get("overwrite_repos"),
        field="overwrite_repos",
        context=context,
    )
    errors.extend(skip_errors)
    errors.extend(overwrite_errors)
    if source_error:
        resolved_source, resolved_path = "", None
    else:
        resolved_source, resolved_path, source_errors = _resolve_source(
            repo_root=repo_root,
            source=source,
            section=section,
            context=context,
        )
        errors.extend(source_errors)
    if resolved_path is not None:
        if is_directory != resolved_path.is_dir():
            expected = "directory" if is_directory else "file"
            errors.append(f"{context}: resolved source must be a {expected}")
        content_sha256 = _content_hash(resolved_path)
    else:
        content_sha256 = ""
    if errors:
        return None, errors
    effect_core = {
        "section": section,
        "source": source,
        "resolved_source": resolved_source,
        "target": target,
        "sync_mode": sync_mode,
        "is_directory": is_directory,
        "skip_repos": [rule.repo for rule in skip_repos],
        "skip_reasons": {rule.repo: rule.reason for rule in skip_repos},
        "overwrite_repos": list(overwrite_repos),
        "template_sync": template_sync,
        "delivery": delivery,
        "content_sha256": content_sha256,
    }
    return (
        ManifestEntry(
            source=source,
            resolved_source=resolved_source,
            target=target,
            description=description,
            sync_mode=sync_mode,
            skip_repos=skip_repos,
            overwrite_repos=overwrite_repos,
            is_directory=is_directory,
            template_sync=template_sync,
            delivery=delivery,
            section=section,
            content_sha256=content_sha256,
            effect_fingerprint=_stable_hash("consumer-sync-source-effect", effect_core),
        ),
        [],
    )


def _compile_removal(raw: Any, *, index: int) -> tuple[RemovalEntry | None, list[str]]:
    context = f"removals entry {index}"
    if not isinstance(raw, dict) or set(raw) - {"target", "description"}:
        return None, [f"{context}: entry must contain only target and description"]
    target, error = _safe_relative_path(raw.get("target"), "target", context)
    description = str(raw.get("description") or "").strip()
    errors = [error] if error else []
    if not description:
        errors.append(f"{context}: description must be non-empty")
    if errors:
        return None, errors
    core = {"target": target}
    return (
        RemovalEntry(
            target=target,
            description=description,
            effect_fingerprint=_stable_hash("consumer-sync-removal-effect", core),
        ),
        [],
    )


def compile_manifest(path: Path, *, repo_root: Path | None = None) -> CompiledManifest:
    path = path.resolve()
    root = repo_root.resolve() if repo_root is not None else path.parent.parent.resolve()
    raw_bytes = path.read_bytes()
    data = yaml.safe_load(raw_bytes) or {}
    if not isinstance(data, dict):
        raise ManifestCompileError(["manifest root must be a mapping"])
    problems: list[str] = []
    if data.get("version") != 1:
        problems.append("manifest version must be 1")
    known = {"version", "removals"} | set(COPY_SYNCED_SECTIONS) | IGNORED_METADATA_SECTIONS
    unknown = sorted(set(data) - known)
    if unknown:
        problems.append(f"manifest has unsupported top-level sections {unknown}")
    sections: dict[str, list[ManifestEntry]] = {}
    target_owners: dict[str, str] = {}
    for section in COPY_SYNCED_SECTIONS:
        raw_entries = data.get(section, [])
        if not isinstance(raw_entries, list):
            problems.append(f"section '{section}' must be a list")
            continue
        entries: list[ManifestEntry] = []
        for index, raw in enumerate(raw_entries):
            entry, errors = _compile_entry(
                raw,
                section=section,
                index=index,
                repo_root=root,
            )
            problems.extend(errors)
            if entry is None:
                continue
            owner = target_owners.get(entry.target)
            if owner:
                problems.append(
                    f"duplicate effective target {entry.target!r}: {owner} and {section}[{index}]"
                )
            else:
                target_owners[entry.target] = f"{section}[{index}]"
            entries.append(entry)
        sections[section] = entries
    raw_removals = data.get("removals", [])
    if not isinstance(raw_removals, list):
        problems.append("removals must be a list")
        raw_removals = []
    removals: list[RemovalEntry] = []
    for index, raw in enumerate(raw_removals):
        removal, errors = _compile_removal(raw, index=index)
        problems.extend(errors)
        if removal is None:
            continue
        owner = target_owners.get(removal.target)
        if owner:
            problems.append(
                f"duplicate effective target {removal.target!r}: {owner} and removals[{index}]"
            )
        else:
            target_owners[removal.target] = f"removals[{index}]"
        removals.append(removal)
    if problems:
        raise ManifestCompileError(problems)
    return CompiledManifest(
        version=1,
        manifest_sha256="sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
        sections=sections,
        removals=removals,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        "--validate",
        dest="manifest",
        required=True,
        help="Path to .github/sync-manifest.yml",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Write the deterministic workflows.consumer-sync-plan/v1 JSON",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        default=Path(os.environ["GITHUB_OUTPUT"]) if os.environ.get("GITHUB_OUTPUT") else None,
        help="Optional GitHub Actions output file",
    )
    args = parser.parse_args(argv)
    try:
        compiled = compile_manifest(Path(args.manifest))
    except (OSError, yaml.YAMLError, ManifestCompileError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    plan = compiled.to_plan()
    serialized = json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if args.output_json:
        args.output_json.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"plan_id={plan['plan_id']}\n")
            handle.write(f"template_hash={plan['plan_id'].split(':', 1)[1][:12]}\n")
            handle.write(f"entry_count={len(plan['entries'])}\n")
            handle.write(f"removal_count={len(plan['removals'])}\n")
    print(
        f"Compiled {len(plan['entries'])} copy entries and "
        f"{len(plan['removals'])} removals as {plan['plan_id']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
