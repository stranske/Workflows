#!/usr/bin/env python3
"""Stage agent work without runtime artifacts; preserve existing staged source blobs."""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path

# Root-level runner outputs only: docs/evidence and other intentional proof remain eligible.
ARTIFACT_PATTERNS = tuple(
    f"{agent}-{kind}{suffix}"
    for agent in ("codex", "claude", "cursor", "gemini", "muse")
    for kind, suffix in (
        ("output", "*.md"),
        ("prompt", "*.md"),
        ("session", "*.log"),
        ("session", "*.jsonl"),
        ("analysis", "*.json"),
    )
) + (
    ".coverage",
    ".coverage.*",
    "coverage.xml",
    "pr_body.md",
    "autofix_report_enriched.json",
    "poetry.lock",
)
ARTIFACT_DIRECTORIES = {
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
}
ROOT_CHECKOUTS = {".workflows-lib", ".workflows-actions", ".reference", "coverage", "htmlcov"}
# These paths require a separately authorized repair, not automatic conflict staging.
# Match the existing worker boundaries in .github/codex/AGENT_INSTRUCTIONS.md.
PROTECTED_RESOLUTIONS = {
    ".github/CODEOWNERS",
    ".github/scripts/prompt_injection_guard.js",
    ".github/scripts/agents-guard.js",
    ".github/dependabot.yml",
    ".github/renovate.json",
    "SECURITY.md",
}


def is_artifact(path: str) -> bool:
    parts = path.split("/")
    return (
        parts[0] in ROOT_CHECKOUTS
        or any(part in ARTIFACT_DIRECTORIES for part in parts)
        or (len(parts) == 1 and any(fnmatch.fnmatchcase(path, p) for p in ARTIFACT_PATTERNS))
    )


def git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args],
        input=data,
        stdout=subprocess.PIPE,
        check=True,
        env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"},
    ).stdout


def paths(*args: str) -> set[str]:
    return {os.fsdecode(p) for p in git(*args).split(b"\0") if p}


def update_index(command: tuple[str, ...], names: set[str]) -> None:
    if names:
        git(
            *command,
            "--pathspec-from-file=-",
            "--pathspec-file-nul",
            data=b"".join(os.fsencode(p) + b"\0" for p in sorted(names)),
        )


def unmerged_paths() -> set[str]:
    return {
        os.fsdecode(record.split(b"\t", 1)[1])
        for record in git("ls-files", "--unmerged", "-z").split(b"\0")
        if record
    }


def require_text(content: bytes, name: str) -> None:
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        raise SystemExit(f"Refusing non-text conflict resolution: {name!r}") from None
    if b"\0" in content:
        raise SystemExit(f"Refusing non-text conflict resolution: {name!r}")


def validate_resolutions(names: set[str]) -> None:
    for name in sorted(names):
        if (
            is_artifact(name)
            or name in PROTECTED_RESOLUTIONS
            or name.startswith(".github/workflows/")
            or any(word in name.lower() for word in ("secret", "token", "credential"))
        ):
            raise SystemExit(f"Refusing excluded conflict resolution: {name!r}")
        path = Path(name)
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise SystemExit(f"Refusing symlink conflict resolution: {name!r}")
        attributes = git(
            "check-attr", "-z", "diff", "merge", "conflict-marker-size", "--", name
        ).split(b"\0")
        if attributes[2] == b"unset" or attributes[5] not in (b"unspecified", b"set", b"text"):
            raise SystemExit(f"Refusing non-text conflict resolution: {name!r}")
        if attributes[2] not in (b"unspecified", b"set"):
            key = f"diff.{os.fsdecode(attributes[2])}.binary"
            if git("config", "--type=bool", "--default", "false", "--get", key).strip() == b"true":
                raise SystemExit(f"Refusing non-text conflict resolution: {name!r}")
        if attributes[5] == b"unspecified":
            driver = git("config", "--default", "text", "--get", "merge.default").strip()
            if driver != b"text":
                raise SystemExit(f"Refusing non-text conflict resolution: {name!r}")
        # Git can leave an untouched text 'ours' file for a binary conflict in
        # the base or incoming blob. Validate all original stages, not just the
        # marker-free working file, before allowing automatic host staging.
        for record in git("ls-files", "--unmerged", "-z", "--", name).split(b"\0"):
            if record:
                mode, oid, _ = record.split(b"\t", 1)[0].split()
                if mode not in (b"100644", b"100755"):
                    raise SystemExit(f"Refusing non-file conflict resolution: {name!r}")
                require_text(git("cat-file", "blob", oid.decode("ascii")), name)
        if path.exists():
            if not path.is_file():
                raise SystemExit(f"Refusing non-file conflict resolution: {name!r}")
            content = path.read_bytes()
            require_text(content, name)
            try:
                marker_size = int(attributes[8])
            except ValueError:
                marker_size = 7
            minimum = min(7, marker_size) if marker_size > 0 else 7
            marker = re.compile(rb"(?:<{%d,}|={%d,}|>{%d,}|\|{%d,})(?:[ \t].*)?" % ((minimum,) * 4))
            if any(marker.fullmatch(line) for line in content.splitlines()):
                raise SystemExit(f"Unresolved conflict markers: {name!r}")
        # Missing working files are explicit deletion resolutions, staged by add -A.
    if names:
        # Git also honors conflict-marker-size attributes and detects whitespace errors.
        git("diff", "--check", "--", *sorted(names))


def main() -> None:
    os.chdir(os.fsdecode(git("rev-parse", "--show-toplevel")).strip())
    unmerged = unmerged_paths()
    # Validate every resolution before changing any index entry. Unmerged paths
    # appear in --cached output but have no staged source blob to preserve.
    validate_resolutions(unmerged)
    staged = paths("diff", "--cached", "--no-renames", "--name-only", "-z")
    # Remove even previously staged junk, without changing or deleting working files.
    update_index(("restore", "--staged"), {p for p in staged if is_artifact(p)})
    candidates = paths("diff", "--no-renames", "--name-only", "-z") | paths(
        "ls-files", "--others", "--exclude-standard", "-z"
    )
    update_index(("add", "-A"), {p for p in (candidates - staged) | unmerged if not is_artifact(p)})
    remaining = unmerged_paths()
    if remaining:
        raise SystemExit(f"Unmerged index entries remain: {sorted(remaining)!r}")
    if unmerged:
        git("diff", "--cached", "--check", "--", *sorted(unmerged))


if __name__ == "__main__":
    main()
