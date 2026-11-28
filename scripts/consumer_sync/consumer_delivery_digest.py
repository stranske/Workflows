#!/usr/bin/env python3
"""Hash rendered manifest delivery intent, independently of source commit identity."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

# The manifest compiler and the status-file block stay at the root of scripts/
# (the compiler runs from Maint 68's immutable source checkout).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sync_manifest_compiler import DirectorySourceInventory, compile_manifest  # noqa: E402
from sync_status_file_ignores import load_template_block  # noqa: E402


def delivery_digest(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(b"consumer-delivery/v1\0" + encoded).hexdigest()


def render_payload(root: Path, repositories: list[str]) -> dict:
    """Render copies, removals, scopes/create-only policy and the managed block.

    Consumer-local content is deliberately absent: this is delivery intent, not
    an authorization to overwrite local files or to carry a seal to a new head.
    """
    directories = DirectorySourceInventory(root)
    plan = compile_manifest(
        root / ".github/sync-manifest.yml", repo_root=root, directories=directories
    ).to_plan()
    files = {repository: {} for repository in sorted(set(repositories))}
    for entry in plan["entries"]:
        recipients = [
            repository
            for repository in files
            if (not entry["include_repos"] or repository in entry["include_repos"])
            and repository not in entry["skip_repos"]
        ]
        if not recipients:
            continue
        source = root / entry["resolved_source"]
        children = directories.files(source) if entry["is_directory"] else [source]
        for child in children:
            if not child.is_file():
                continue
            target = entry["target"]
            if entry["is_directory"]:
                target += "/" + child.relative_to(source).as_posix()
            content = (
                hashlib.sha256(child.read_bytes()).hexdigest()
                if entry["is_directory"]
                else entry["content_sha256"].removeprefix("sha256:")
            )
            executable = bool(child.stat().st_mode & 0o111)
            for repository in recipients:
                files[repository][target] = {
                    "content": content,
                    "executable": executable,
                    "create_only": entry["sync_mode"] == "create_only"
                    and repository not in entry["overwrite_repos"],
                }
    for repository, rows in files.items():
        for removal in plan["removals"]:
            if repository not in removal.get("skip_repos", []):
                rows[removal["target"]] = {"remove": True}
        # Full plans also reconcile this generated block outside the manifest.
        # Track it on .gitignore so overlap detection sees its real target.
        lines = (root / "templates/consumer-repo/.gitignore").read_text().splitlines()
        with patch("sync_status_file_ignores._read_template_lines", return_value=lines):
            blocks = [
                load_template_block(preserve_vendored_node_modules=value) for value in (False, True)
            ]
        rows.setdefault(".gitignore", {})["managed_blocks"] = blocks
    return {"digest": delivery_digest(files), "files": files}


def payload_at_ref(root: Path, ref: str, repositories: list[str]) -> dict:
    if not re.fullmatch(r"[a-f0-9]{40}", ref):
        raise ValueError("delivery digest requires an immutable source SHA")
    exists = subprocess.run(
        ["git", "cat-file", "-e", ref + "^{commit}"], cwd=root, capture_output=True, check=False
    )
    if exists.returncode:
        subprocess.run(
            ["git", "fetch", "--no-tags", "--no-write-fetch-head", "origin", ref],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    archive = subprocess.check_output(["git", "archive", "--format=tar", ref], cwd=root)
    with tempfile.TemporaryDirectory(prefix="consumer-delivery-") as directory:
        snapshot = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            for member in stream:
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("unsafe source archive path")
                if member.isfile():
                    destination = snapshot / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(stream.extractfile(member).read())
                    destination.chmod(member.mode)
                elif not member.isdir():
                    raise ValueError("unsupported source archive entry: " + member.name)
        return render_payload(snapshot, repositories)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--repos", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(
        json.dumps(payload_at_ref(args.repo_root, args.ref, args.repos.split(",")), sort_keys=True)
    )


if __name__ == "__main__":
    main()
