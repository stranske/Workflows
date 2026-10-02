#!/usr/bin/env python3
"""Read-only audit for historical belt tasks completed without evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

try:
    from scripts.belt_ledger_completion import completion_issues
except ModuleNotFoundError:  # direct script execution
    from belt_ledger_completion import completion_issues


def audit_ledger_evidence(root: Path) -> tuple[list[str], list[str]]:
    """Return actionable findings separately from locally unverifiable history."""
    findings: list[str] = []
    unverifiable: list[str] = []
    for ledger_path in sorted((root / ".agents").glob("issue-*-ledger.yml")):
        original = ledger_path.read_bytes()
        data = yaml.safe_load(original) or {}
        tasks = data.get("tasks") if isinstance(data, dict) else []
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict) or task.get("status") != "done":
                continue
            commit = str(task.get("commit") or "")
            for issue in completion_issues(task, commit, repo_root=root):
                rendered = f"{ledger_path.relative_to(root)} {issue.message}"
                if issue.kind == "unverifiable":
                    unverifiable.append(rendered)
                else:
                    findings.append(rendered)
        if ledger_path.read_bytes() != original:  # pragma: no cover - safety invariant
            raise RuntimeError(f"audit modified {ledger_path}")
    return findings, unverifiable


def audit_ledgers(root: Path) -> list[str]:
    """Return only actionable historical false-completion findings."""
    findings, _ = audit_ledger_evidence(root)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    findings, unverifiable = audit_ledger_evidence(args.root.resolve())
    for finding in findings:
        print(finding)
    if not findings:
        print("No invalid belt completion evidence found.")
    if unverifiable:
        print(f"{len(unverifiable)} completion commit(s) unverifiable (skipped, not findings).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
