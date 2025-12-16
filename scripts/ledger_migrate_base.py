from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import yaml  # type: ignore


class LedgerDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:  # type: ignore[override]
        super().increase_indent(flow, False)


class MigrationError(Exception):
    """Raised when the migration cannot determine the default branch."""


@dataclass
class LedgerResult:
    path: Path
    previous: Optional[str]
    updated: Optional[str]
    changed: bool


def _run_git(args: Iterable[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
    ) as exc:  # pragma: no cover - git failures surfaced to caller
        raise MigrationError(str(exc)) from exc
    return completed.stdout


def detect_default_branch(explicit: Optional[str] = None) -> str:
    if explicit:
        candidate = explicit.strip()
        if not candidate:
            raise MigrationError("default branch override cannot be empty")
        return candidate

    # Attempt to parse `git remote show origin` which exposes the HEAD branch even when the
    # repository default is renamed away from `main`.
    try:
        output = _run_git(["remote", "show", "origin"])
    except MigrationError:
        output = ""
    else:
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("head branch:"):
                branch = stripped.split(":", 1)[1].strip()
                if branch:
                    return branch

    # Fallback to symbolic-ref which resolves origin/HEAD -> refs/remotes/origin/<branch>
    try:
        ref = _run_git(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"]).strip()
    except MigrationError:
        ref = ""
    if ref:
        prefix = "refs/remotes/origin/"
        if ref.startswith(prefix):
            return ref[len(prefix) :]
        if ref.startswith("refs/heads/"):
            return ref[len("refs/heads/") :]
        if ref:
            return ref

    # `git rev-parse --abbrev-ref origin/HEAD` is another option when the symbolic-ref exists
    # but the repository is shallow.
    try:
        rev = _run_git(["rev-parse", "--abbrev-ref", "origin/HEAD"]).strip()
    except MigrationError:
        rev = ""
    if rev and rev != "origin/HEAD":
        return rev.split("/", 1)[-1]

    # Fall back to the current branch as a last resort; callers can override via --default.
    try:
        current = _run_git(["symbolic-ref", "--quiet", "HEAD"]).strip()
    except MigrationError as exc:
        raise MigrationError(
            "unable to determine default branch; pass --default explicitly"
        ) from exc
    if current.startswith("refs/heads/"):
        return current[len("refs/heads/") :]
    if current:
        return current
    raise MigrationError("unable to determine default branch; pass --default explicitly")


def load_ledger(path: Path) -> tuple[dict, Optional[str]]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise MigrationError(f"{path}: ledger must be a mapping")
    base = data.get("base")
    return data, base if isinstance(base, str) else None


def migrate_ledger(path: Path, default_branch: str, *, check: bool) -> LedgerResult:
    data, base = load_ledger(path)
    if base == default_branch:
        return LedgerResult(path=path, previous=base, updated=base, changed=False)

    if check:
        return LedgerResult(path=path, previous=base, updated=None, changed=False)

    data["base"] = default_branch
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(
            data,
            handle,
            Dumper=LedgerDumper,
            sort_keys=False,
            indent=2,
            default_flow_style=False,
        )
    return LedgerResult(path=path, previous=base, updated=default_branch, changed=True)


def find_repo_root() -> Path:
    try:
        path = _run_git(["rev-parse", "--show-toplevel"]).strip()
    except MigrationError as exc:
        raise MigrationError("not inside a git repository") from exc
    return Path(path)


def discover_ledgers(root: Path) -> List[Path]:
    agents_dir = root / ".agents"
    if not agents_dir.exists():
        return []
    return sorted(agents_dir.glob("issue-*-ledger.yml"))


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Update ledger base branch to repository default")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify ledgers already match the default branch",
    )
    parser.add_argument(
        "--default",
        dest="default_branch",
        help="Explicit default branch name to use",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        root = find_repo_root()
        default_branch = detect_default_branch(args.default_branch)
    except MigrationError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2

    ledgers = discover_ledgers(root)
    if not ledgers:
        print("No ledgers found; nothing to do.")
        return 0

    mismatches: List[LedgerResult] = []
    updated: List[LedgerResult] = []
    for ledger_path in ledgers:
        result = migrate_ledger(ledger_path, default_branch, check=args.check)
        if args.check:
            if result.previous != default_branch:
                mismatches.append(result)
        elif result.changed:
            updated.append(result)

    if args.check:
        if mismatches:
            print("Found ledgers with stale base values:")
            for result in mismatches:
                prev = result.previous or "<unset>"
                print(f"  - {result.path}: base={prev!r}, expected {default_branch!r}")
            print("Run scripts/ledger_migrate_base.py to update them.")
            return 1
        print("All ledgers already track the default branch.")
        return 0

    if updated:
        print("Updated ledgers:")
        for result in updated:
            prev = result.previous or "<unset>"
            print(f"  - {result.path}: {prev!r} -> {default_branch!r}")
    else:
        print("Ledgers already matched the default branch; no updates written.")
    return 0


if __name__ == "__main__":
    from trend_analysis.script_logging import setup_script_logging

    setup_script_logging(module_file=__file__)
    sys.exit(main())
