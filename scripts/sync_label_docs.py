#!/usr/bin/env python3
"""Sync docs/LABELS.md to registered consumer repositories."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

DEFAULT_SOURCE = Path("docs/LABELS.md")
TARGET_PATH = Path("docs/LABELS.md")
COMMIT_MESSAGE = "docs: sync LABELS.md from Workflows repository"


class SyncLabelDocsError(RuntimeError):
    """Raised when a label docs sync cannot be completed safely."""


@dataclass(frozen=True)
class SyncResult:
    repo: str
    status: str
    message: str


CommandRunner = Callable[[Sequence[str], Path | None], None]


def parse_repos(value: str) -> list[str]:
    return [repo.strip() for repo in value.split(",") if repo.strip()]


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_command(command: Sequence[str], redactions: Sequence[str] = ()) -> str:
    parts: list[str] = []
    for part in command:
        safe_part = part
        for secret in redactions:
            if secret:
                safe_part = safe_part.replace(secret, "***")
        parts.append(safe_part)
    return " ".join(parts)


def run_command(
    command: Sequence[str],
    cwd: Path | None = None,
    *,
    redactions: Sequence[str] = (),
) -> None:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode == 0:
        return

    details = (completed.stderr or completed.stdout).strip()
    safe_command = redact_command(command, redactions)
    if details:
        raise SyncLabelDocsError(
            f"{safe_command} failed with exit {completed.returncode}: {details}"
        )
    raise SyncLabelDocsError(f"{safe_command} failed with exit {completed.returncode}")


def build_clone_url(repo: str, token: str) -> str:
    return f"https://x-access-token:{quote(token, safe='')}@github.com/{repo}.git"


def sync_checkout(
    *,
    repo: str,
    source_file: Path,
    checkout_dir: Path,
    dry_run: bool = False,
    run: CommandRunner = run_command,
) -> SyncResult:
    source_file = source_file.resolve()
    checkout_dir = checkout_dir.resolve()
    docs_dir = checkout_dir / TARGET_PATH.parent
    target_file = checkout_dir / TARGET_PATH

    if not source_file.is_file():
        raise SyncLabelDocsError(f"Source file not found: {source_file}")
    if not docs_dir.is_dir():
        raise SyncLabelDocsError(f"{repo}: target docs directory not found: {TARGET_PATH.parent}")

    source_hash = file_sha256(source_file)
    target_hash = file_sha256(target_file)
    if source_hash == target_hash:
        return SyncResult(repo=repo, status="skipped", message=f"No changes needed for {repo}")

    if dry_run:
        return SyncResult(
            repo=repo,
            status="changed",
            message=f"DRY RUN: Would update {TARGET_PATH} in {repo}",
        )

    shutil.copyfile(source_file, target_file)
    run(["git", "config", "user.name", "github-actions[bot]"], checkout_dir)
    run(
        ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
        checkout_dir,
    )
    run(["git", "add", str(TARGET_PATH)], checkout_dir)
    run(["git", "commit", "-m", COMMIT_MESSAGE], checkout_dir)
    run(["git", "push"], checkout_dir)
    return SyncResult(repo=repo, status="updated", message=f"Successfully synced to {repo}")


def sync_repo(
    *,
    repo: str,
    token: str,
    source_file: Path,
    dry_run: bool = False,
    run: CommandRunner = run_command,
) -> SyncResult:
    with tempfile.TemporaryDirectory(prefix="sync-label-docs-") as tmp:
        checkout_dir = Path(tmp) / "repo"
        clone_url = build_clone_url(repo, token)
        try:
            run(["git", "clone", "--depth", "1", clone_url, str(checkout_dir)], None)
        except SyncLabelDocsError as exc:
            raise SyncLabelDocsError(f"{repo}: clone failed") from exc

        return sync_checkout(
            repo=repo,
            source_file=source_file,
            checkout_dir=checkout_dir,
            dry_run=dry_run,
            run=run,
        )


def sync_repos(
    *,
    repos: Sequence[str],
    token: str,
    source_file: Path = DEFAULT_SOURCE,
    dry_run: bool = False,
) -> list[SyncResult]:
    results: list[SyncResult] = []
    failures: list[str] = []

    for repo in repos:
        print(f"## Syncing to {repo}", flush=True)
        try:
            result = sync_repo(repo=repo, token=token, source_file=source_file, dry_run=dry_run)
        except SyncLabelDocsError as exc:
            message = str(exc)
            if not message.startswith(f"{repo}:"):
                message = f"{repo}: {message}"
            print(f"::error::{message}", flush=True)
            failures.append(message)
            continue

        print(result.message, flush=True)
        results.append(result)

    if failures:
        raise SyncLabelDocsError("; ".join(failures))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos", required=True, help="Comma-separated owner/repo names")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Source LABELS.md path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.environ.get("DRY_RUN", "false").lower() == "true",
        help="Preview changes without committing or pushing",
    )
    parser.add_argument(
        "--token-env",
        default="SYNC_TOKEN",
        help="Environment variable containing a push-capable GitHub token",
    )
    args = parser.parse_args()

    repos = parse_repos(args.repos)
    if not repos:
        raise SystemExit("No repositories supplied")

    token = os.environ.get(args.token_env, "")
    if not token:
        raise SystemExit(f"Missing sync token in ${args.token_env}")

    try:
        sync_repos(repos=repos, token=token, source_file=Path(args.source), dry_run=args.dry_run)
    except SyncLabelDocsError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
