#!/usr/bin/env python3
"""Derive a deterministic full or exact-source-delta consumer sync plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from scripts.sync_manifest_compiler import PLAN_SCHEMA
except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
    from sync_manifest_compiler import PLAN_SCHEMA

SCOPE_SCHEMA = "workflows.consumer-sync-plan-scope/v1"
SCOPES = {"full", "source-delta"}
MANIFEST_PATH = ".github/sync-manifest.yml"


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


def select_plan(
    plan: Any,
    *,
    mode: str,
    changed_paths: list[str] | None = None,
    base_sha: str = "",
    source_commit: str = "",
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
    if mode == "source-delta" and MANIFEST_PATH in normalized_paths:
        raise PlanScopeError("manifest_change_requires_full_scope")

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
        # change must use full scope, so an exact source delta never replays old
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
