#!/usr/bin/env python3
"""Derive a deterministic full or exact-source-delta consumer sync plan."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

try:
    from scripts.sync_manifest_compiler import (
        COPY_SYNCED_SECTIONS,
        PLAN_SCHEMA,
        ManifestCompileError,
        compile_manifest,
    )
except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
    from sync_manifest_compiler import (
        COPY_SYNCED_SECTIONS,
        PLAN_SCHEMA,
        ManifestCompileError,
        compile_manifest,
    )

SCOPE_SCHEMA = "workflows.consumer-sync-plan-scope/v1"
SCOPES = {"full", "source-delta"}
MANIFEST_PATH = ".github/sync-manifest.yml"
FULL_SCOPE_ONLY_PATHS = frozenset(
    {
        "scripts/sync_status_file_ignores.py",
        "templates/consumer-repo/.gitignore",
        "templates/consumer-repo/scripts/sync_status_file_ignores.py",
    }
)


class PlanScopeError(ValueError):
    """The requested scope cannot produce a safe consumer sync plan."""


def _stable_hash(namespace: str, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(namespace.encode() + b"\0" + encoded).hexdigest()


def _validate_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
        raise PlanScopeError("unsupported_consumer_sync_plan")
    if not isinstance(plan.get("plan_id"), str) or not plan["plan_id"].startswith("sha256:"):
        raise PlanScopeError("invalid_consumer_sync_plan_id")
    if not isinstance(plan.get("entries"), list) or not isinstance(plan.get("removals"), list):
        raise PlanScopeError("invalid_consumer_sync_plan_collections")
    return plan


def _entry_matches_path(entry: dict[str, Any], changed_path: str) -> bool:
    source = str(entry.get("resolved_source") or "").strip()
    if not source:
        return False
    if changed_path == source:
        return True
    return (
        bool(entry.get("is_directory"))
        and PurePosixPath(source) in PurePosixPath(changed_path).parents
    )


def _source_delta_dependencies(
    plan_entries: list[dict[str, Any]], selected_entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Expand selected entries with mandatory runtime/bootstrap dependencies."""
    entries_by_target = {str(entry.get("target") or ""): entry for entry in plan_entries}
    selected_targets = {str(entry.get("target") or "") for entry in selected_entries}
    required_targets: set[str] = set()
    pending = list(selected_targets)
    while pending:
        target = pending.pop()
        for dependency in entries_by_target.get(target, {}).get("requires") or []:
            dependency = str(dependency or "")
            if (
                dependency
                and dependency not in selected_targets
                and dependency not in required_targets
            ):
                required_targets.add(dependency)
                pending.append(dependency)
    return [
        entry
        for entry in plan_entries
        if str(entry.get("target") or "") in required_targets
        and str(entry.get("target") or "") not in selected_targets
    ]


class _UniqueManifestLoader(yaml.SafeLoader):
    """Refuse ambiguous YAML while comparing the two immutable selectors."""

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[str, Any]:
        self.flatten_mapping(node)
        result: dict[str, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise PlanScopeError("ambiguous_manifest_selector")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _without_descriptions(document: dict[str, Any], *, compiled: bool) -> dict[str, Any]:
    result = copy.deepcopy(document)
    collections = ("entries", "removals") if compiled else (*COPY_SYNCED_SECTIONS, "removals")
    for section in collections:
        for entry in result.get(section, []):
            if not isinstance(entry.get("description"), str) or not entry["description"].strip():
                raise PlanScopeError("invalid_manifest_description")
            del entry["description"]
    if compiled:
        del result["plan_id"]
        del result["manifest_sha256"]
    return result


def _verify_source_payload(root: Path, commit: str, plan: dict[str, Any]) -> None:
    """Match compiled inputs to native Git blobs/modes, including directory inventory."""
    sources = sorted({entry["resolved_source"] for entry in plan["entries"]})
    if not sources:
        return
    native = subprocess.run(
        ["git", "ls-tree", "-r", "-z", commit, "--", *sources],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    tracked = {}
    for row in native.split(b"\0"):
        if not row:
            continue
        header, name = row.split(b"\t", 1)
        mode, kind, blob = header.decode().split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise PlanScopeError("unsupported_source_payload_mode")
        tracked[name.decode()] = (mode, blob)
    checked = set()
    for entry in plan["entries"]:
        source = entry["resolved_source"]
        path = root / source
        if entry["is_directory"]:
            expected = {name for name in tracked if name.startswith(source + "/")}
            children = list(path.rglob("*"))
            if any(child.is_symlink() for child in children):
                raise PlanScopeError("source_payload_symlink")
            observed = {child.relative_to(root).as_posix() for child in children if child.is_file()}
            if not expected or observed != expected:
                raise PlanScopeError("source_payload_inventory_differs")
        else:
            expected = {source}
        for name in expected - checked:
            target = root / name
            if (
                name not in tracked
                or not target.is_file()
                or target.is_symlink()
                or target.resolve(strict=True) != target
            ):
                raise PlanScopeError("source_payload_identity_differs")
            raw = target.read_bytes()
            mode = "100755" if target.stat().st_mode & 0o111 else "100644"
            # Match native Git object IDs, not a cryptographic security assertion.
            blob = hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
            ).hexdigest()
            if (mode, blob) != tracked[name]:
                raise PlanScopeError("source_payload_blob_or_mode_differs")
            checked.add(name)


def _manifest_metadata_equivalence(
    repo_root: Path, base_sha: str, source_commit: str, plan: dict[str, Any]
) -> dict[str, Any]:
    """Prove only known descriptions/comments differ using the actual compiler.

    Both manifests are compiled against the same immutable source payload: an
    intended source-content edit must still be selected by the ordinary range.
    Unknown fields, non-description metadata, removals and policy changes refuse.
    No caller-provided flag or comparison digest can substitute for this read.
    """
    try:
        base_sha, source_commit, _ = changed_paths_for_range(repo_root, base_sha, source_commit)
        if _commit(repo_root, "HEAD") != source_commit:
            raise PlanScopeError("source_checkout_commit_differs")
        clean = subprocess.run(
            ["git", "diff", "--quiet", "--exit-code", source_commit, "--"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        )
        if clean.returncode != 0:
            raise PlanScopeError("source_checkout_is_dirty")
        source_tree = subprocess.run(
            ["git", "rev-parse", "--verify", f"{source_commit}^{{tree}}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        documents, compiled, hashes, manifest_modes = [], [], [], []
        with tempfile.TemporaryDirectory(prefix="sync-selector-equivalence-") as directory:
            for index, commit in enumerate((base_sha, source_commit)):
                native_entry = subprocess.run(
                    ["git", "ls-tree", "-z", commit, "--", MANIFEST_PATH],
                    cwd=repo_root,
                    check=True,
                    capture_output=True,
                ).stdout
                mode = native_entry.split(b" ", 1)[0]
                if mode not in {b"100644", b"100755"}:
                    raise PlanScopeError("manifest_source_mode_unknown")
                manifest_modes.append(mode)
                raw = subprocess.run(
                    ["git", "show", f"{commit}:{MANIFEST_PATH}"],
                    cwd=repo_root,
                    check=True,
                    capture_output=True,
                ).stdout
                if any(
                    isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
                    for token in yaml.scan(raw)
                ):
                    raise PlanScopeError("ambiguous_manifest_alias")
                document = yaml.load(raw, Loader=_UniqueManifestLoader)
                if not isinstance(document, dict):
                    raise PlanScopeError("invalid_manifest_selector")
                path = Path(directory) / f"manifest-{index}.yml"
                path.write_bytes(raw)
                compiled.append(compile_manifest(path, repo_root=repo_root).to_plan())
                documents.append(_without_descriptions(document, compiled=False))
                hashes.append("sha256:" + hashlib.sha256(raw).hexdigest())
            if (repo_root / MANIFEST_PATH).read_bytes() != raw:
                raise PlanScopeError("source_manifest_checkout_differs")
        if manifest_modes[0] != manifest_modes[1]:
            raise PlanScopeError("manifest_source_mode_changed")
        if _stable_hash("selector", documents[0]) != _stable_hash("selector", documents[1]):
            raise PlanScopeError("operational_manifest_changed")
        operational = [_without_descriptions(value, compiled=True) for value in compiled]
        if _stable_hash("operations", operational[0]) != _stable_hash("operations", operational[1]):
            raise PlanScopeError("compiled_manifest_effect_changed")
        if _stable_hash("plan", compiled[1]) != _stable_hash("plan", plan):
            raise PlanScopeError("source_compiled_plan_differs")
        _verify_source_payload(repo_root, source_commit, compiled[1])
        return {
            "schema": "workflows.consumer-sync-manifest-equivalence/v1",
            "base_sha": base_sha,
            "source_commit": source_commit,
            "source_tree_sha": source_tree,
            "manifest_mode": manifest_modes[1].decode(),
            "base_manifest_sha256": hashes[0],
            "source_manifest_sha256": hashes[1],
            "selector_sha256": _stable_hash("selector", documents[1]),
            "operational_plan_sha256": _stable_hash("operations", operational[1]),
            "allowed_difference": "known_descriptions_and_comments_only",
        }
    except (
        OSError,
        ValueError,
        TypeError,
        RecursionError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
        ManifestCompileError,
    ) as exc:
        reason = str(exc) if isinstance(exc, PlanScopeError) else type(exc).__name__
        raise PlanScopeError(f"manifest_change_requires_full_scope:{reason}") from exc


def select_plan(
    plan: Any,
    *,
    mode: str,
    changed_paths: list[str] | None = None,
    base_sha: str = "",
    source_commit: str = "",
    repo_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the scoped v1 plan and an auditable scope envelope."""
    plan = _validate_plan(plan)
    if mode not in SCOPES:
        raise PlanScopeError("unsupported_plan_scope")
    normalized_paths = sorted(
        {
            PurePosixPath(str(path).strip()).as_posix()
            for path in changed_paths or []
            if str(path).strip()
        }
    )
    if mode == "source-delta" and not base_sha:
        raise PlanScopeError("source_delta_requires_base_sha")
    if mode == "source-delta" and not source_commit:
        raise PlanScopeError("source_delta_requires_source_commit")
    manifest_equivalence = None
    if mode == "source-delta" and MANIFEST_PATH in normalized_paths:
        if repo_root is None:
            raise PlanScopeError("manifest_change_requires_full_scope")
        manifest_equivalence = _manifest_metadata_equivalence(
            repo_root.resolve(), base_sha, source_commit, plan
        )
    if mode == "source-delta" and FULL_SCOPE_ONLY_PATHS.intersection(normalized_paths):
        raise PlanScopeError("status_ignore_change_requires_full_scope")

    if mode == "full":
        scoped = dict(plan)
        selected_entries = list(plan["entries"])
        selected_removals = list(plan["removals"])
    else:
        selected_entries = [
            entry
            for entry in plan["entries"]
            if any(_entry_matches_path(entry, path) for path in normalized_paths)
        ]
        direct_selected_targets = {str(entry.get("target") or "") for entry in selected_entries}
        dependency_entries = _source_delta_dependencies(plan["entries"], selected_entries)
        selected_entries.extend(dependency_entries)
        # Removals are manifest declarations without a live source path. A manifest
        # operational change must use full scope, so a delta never replays old
        # removals merely because unrelated consumer drift exists.
        selected_removals = []
        core = {
            "schema": plan["schema"],
            "version": plan["version"],
            "manifest_sha256": plan["manifest_sha256"],
            "entries": selected_entries,
            "removals": selected_removals,
        }
        scoped = {**core, "plan_id": _stable_hash("consumer-sync-plan", core)}

    matched_paths = {
        path
        for path in normalized_paths
        if any(_entry_matches_path(entry, path) for entry in selected_entries)
    }
    evidence = {
        "schema": SCOPE_SCHEMA,
        "mode": mode,
        "base_sha": base_sha,
        "source_commit": source_commit,
        "full_plan_id": plan["plan_id"],
        "plan_id": scoped["plan_id"],
        "changed_paths": normalized_paths,
        "matched_changed_paths": sorted(matched_paths),
        "ignored_changed_paths": sorted(set(normalized_paths) - matched_paths),
        "selected_targets": sorted(
            {
                str(item.get("target"))
                for item in [*selected_entries, *selected_removals]
                if item.get("target")
            }
        ),
        "selected_entry_count": len(selected_entries),
        "selected_removal_count": len(selected_removals),
        "dependency_targets": (
            sorted(
                str(entry.get("target"))
                for entry in selected_entries
                if str(entry.get("target") or "") not in direct_selected_targets
            )
            if mode == "source-delta"
            else []
        ),
    }
    if manifest_equivalence is not None:
        evidence["manifest_selector_equivalence"] = manifest_equivalence
    return scoped, evidence


def _commit(repo_root: Path, ref: str) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise PlanScopeError(f"invalid_git_commit:{ref}") from exc


def changed_paths_for_range(
    repo_root: Path, base_ref: str, head_ref: str
) -> tuple[str, str, list[str]]:
    base_sha = _commit(repo_root, base_ref)
    head_sha = _commit(repo_root, head_ref)
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, head_sha],
        cwd=repo_root,
        check=False,
    )
    if ancestor.returncode != 0:
        raise PlanScopeError("scope_base_is_not_ancestor_of_source_commit")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMRTUXB",
            "-z",
            base_sha,
            head_sha,
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    paths = [part.decode("utf-8") for part in result.stdout.split(b"\0") if part]
    return base_sha, head_sha, paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--mode", choices=sorted(SCOPES), required=True)
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--scope-evidence-json", type=Path, required=True)
    parser.add_argument(
        "--github-output",
        type=Path,
        default=Path(os.environ["GITHUB_OUTPUT"]) if os.environ.get("GITHUB_OUTPUT") else None,
    )
    args = parser.parse_args(argv)
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        if args.mode == "source-delta":
            base_sha, source_commit, changed_paths = changed_paths_for_range(
                args.repo_root.resolve(), args.base_ref, args.head_ref
            )
        else:
            base_sha = ""
            source_commit = _commit(args.repo_root.resolve(), args.head_ref)
            changed_paths = []
        scoped, evidence = select_plan(
            plan,
            mode=args.mode,
            changed_paths=changed_paths,
            base_sha=base_sha,
            source_commit=source_commit,
            repo_root=args.repo_root.resolve(),
        )
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError, PlanScopeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    args.output_json.write_text(
        json.dumps(scoped, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    args.scope_evidence_json.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"plan_id={scoped['plan_id']}\n")
            handle.write(f"template_hash={scoped['plan_id'].split(':', 1)[1][:12]}\n")
            handle.write(f"entry_count={len(scoped['entries'])}\n")
            handle.write(f"removal_count={len(scoped['removals'])}\n")
            handle.write(
                "has_plan_items="
                f"{'true' if scoped['entries'] or scoped['removals'] else 'false'}\n"
            )
            handle.write(f"plan_scope={args.mode}\n")
            handle.write(f"scope_base_sha={base_sha}\n")
            handle.write(f"source_commit={source_commit}\n")
    print(
        f"Scoped {len(scoped['entries'])} entries and {len(scoped['removals'])} removals "
        f"as {scoped['plan_id']} ({args.mode})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
