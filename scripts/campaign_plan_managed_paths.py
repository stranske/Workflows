#!/usr/bin/env python3
"""Write the managed path set of the exact campaign sync plan, for Maint 71's no-change carry-over.

Maint 71 may carry Maint 68's "no change" verdict for a consumer from the evidence head to a newer default-branch
head only when no commit in between touches a path the plan manages. Maint 68's sync step reads the consumer only at
those paths: each entry's target (a file, or a directory tree), each removal target, and the managed `.gitignore`
block of a full plan. `requires` paths are added too, as a conservative margin.

The plan is compiled from a checkout of the plan's own source commit and must hash to the expected plan id;
otherwise no file is written and Maint 71 keeps its exact-head rule. This script never fails the job: every
refusal is printed and exits 0, because a missing file already means "no carry-over".
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCHEMA = "workflows.consumer-sync-plan-managed-paths/v1"


def managed_paths(plan: dict) -> dict:
    paths: set[str] = {".gitignore"}
    directories: set[str] = set()
    for entry in plan.get("entries") or []:
        target = str(entry.get("target") or "").strip().rstrip("/")
        if not target:
            raise ValueError("plan entry without a target")
        (directories if entry.get("is_directory") else paths).add(target)
        paths.update(str(dep).strip() for dep in entry.get("requires") or [] if str(dep).strip())
    for removal in plan.get("removals") or []:
        target = str(removal.get("target") or "").strip().rstrip("/")
        if not target:
            raise ValueError("plan removal without a target")
        # A removal may name a file or a tree; treat it as both.
        paths.add(target)
        directories.add(target)
    return {"paths": sorted(paths), "directories": sorted(directories)}


def build(source_root: Path, expected_plan_id: str, source_commit: str) -> tuple[dict | None, str]:
    if not expected_plan_id or not source_commit:
        return None, "expected plan id or source commit missing"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plan.json"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/sync_manifest_compiler.py",
                "--manifest",
                ".github/sync-manifest.yml",
                "--output-json",
                str(out),
            ],
            cwd=source_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not out.is_file():
            return None, f"plan compile failed: {(result.stderr or result.stdout).strip()[-300:]}"
        plan = json.loads(out.read_text(encoding="utf-8"))
    if plan.get("schema") != "workflows.consumer-sync-plan/v1":
        return None, f"unexpected plan schema {plan.get('schema')!r}"
    if plan.get("plan_id") != expected_plan_id:
        return None, f"compiled plan {plan.get('plan_id')} is not the expected {expected_plan_id}"
    return {
        "schema": SCHEMA,
        "plan_id": plan["plan_id"],
        "source_commit": source_commit.lower(),
        **managed_paths(plan),
    }, "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--expected-plan-id", default="")
    parser.add_argument("--source-commit", default="")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        document, reason = build(
            args.source_root, args.expected_plan_id.strip(), args.source_commit.strip()
        )
    except (OSError, ValueError) as exc:
        document, reason = None, f"{exc.__class__.__name__}: {exc}"
    if document is None:
        print(
            f"::notice::campaign plan managed paths not written ({reason}); no-change carry-over disabled"
        )
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    print(
        f"campaign plan managed paths: {len(document['paths'])} paths, "
        f"{len(document['directories'])} directories for {document['plan_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
