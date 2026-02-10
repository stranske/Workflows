#!/usr/bin/env python3
"""Check consumer repos for drift against manifest-defined templates."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path

import requests
import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check consumer repos for drift against Workflows templates and manifest entries."
    )
    parser.add_argument(
        "--repos",
        help="Comma-separated list of repos to check (owner/name).",
    )
    parser.add_argument(
        "--manifest",
        default=".github/sync-manifest.yml",
        help="Path to sync manifest.",
    )
    parser.add_argument(
        "--summary",
        default=os.environ.get("GITHUB_STEP_SUMMARY", ""),
        help="Optional path to write a summary markdown.",
    )
    return parser.parse_args()


def resolve_repos(raw: str | None) -> list[str]:
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    env_repos = os.environ.get("REGISTERED_CONSUMER_REPOS", "")
    repos = [item.strip() for item in env_repos.splitlines() if item.strip()]
    return repos


def local_path_for(source: str) -> Path | None:
    template_candidate = Path("templates/consumer-repo") / source
    if template_candidate.exists():
        return template_candidate
    root_candidate = Path(source)
    if root_candidate.exists():
        return root_candidate
    return None


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def main() -> int:
    args = parse_args()
    repos = resolve_repos(args.repos)
    if not repos:
        print("::error::No repos provided or found in REGISTERED_CONSUMER_REPOS")
        return 1

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print("::error::sync-manifest.yml not found")
        return 1

    token = os.environ.get("DRIFT_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("::error::No GitHub token available for cross-repo reads")
        return 1

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    sections = [
        "workflows",
        "prompts",
        "scripts",
        "codex_config",
        "docs",
        "copilot_config",
        "templates",
        "actions",
        "llm_config",
        "git_config",
        "issue_templates",
        "user_docs",
    ]

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
    )

    drift: set[str] = set()
    missing: set[str] = set()
    errors: set[str] = set()
    obsolete: set[str] = set()

    def _check_file(local_file: Path, remote_target: str, repo: str) -> None:
        """Compare a single local file against its remote counterpart."""
        local_digest = file_hash(local_file.read_bytes())
        url = f"https://api.github.com/repos/{repo}/contents/{remote_target}"
        response = session.get(url)
        if response.status_code == 404:
            missing.add(f"{repo}: {remote_target}")
            return
        if response.status_code >= 400:
            errors.add(f"{repo}: {remote_target} (HTTP {response.status_code})")
            return
        data = response.json()
        if data.get("encoding") != "base64" or "content" not in data:
            errors.add(f"{repo}: {remote_target} (unexpected content encoding)")
            return
        remote_content = base64.b64decode(data["content"])
        if file_hash(remote_content) != local_digest:
            drift.add(f"{repo}: {remote_target}")

    for section in sections:
        for entry in manifest.get(section, []) or []:
            source = entry.get("source")
            if not source:
                continue
            if entry.get("sync_mode") == "create_only":
                continue
            target = entry.get("target", source)
            is_directory = entry.get("is_directory", False)
            local_path = local_path_for(source)
            if not local_path:
                errors.add(f"{section}: missing local file for {source}")
                continue

            for repo in repos:
                if is_directory or local_path.is_dir():
                    # Recursively compare all files within the directory
                    for child in sorted(local_path.rglob("*")):
                        if child.is_file():
                            rel = child.relative_to(local_path)
                            remote_target = f"{target}/{rel}"
                            _check_file(child, remote_target, repo)
                else:
                    _check_file(local_path, target, repo)

    for entry in manifest.get("removals", []) or []:
        target = entry.get("target")
        if not target:
            continue
        for repo in repos:
            url = f"https://api.github.com/repos/{repo}/contents/{target}"
            response = session.get(url)
            if response.status_code == 404:
                continue
            if response.status_code >= 400:
                errors.add(f"{repo}: {target} (HTTP {response.status_code})")
                continue
            obsolete.add(f"{repo}: {target}")

    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("a", encoding="utf-8") as handle:
            handle.write("## Consumer Sync Drift Check\n")
            handle.write(f"Checked repos: {', '.join(repos)}\n\n")
            if drift:
                handle.write("❌ Drift detected for:\n")
                handle.write("\n".join(f"- {item}" for item in sorted(drift)))
                handle.write("\n\n")
            else:
                handle.write("✅ No drift detected.\n\n")
            if missing:
                handle.write("⚠️ Missing files:\n")
                handle.write("\n".join(f"- {item}" for item in sorted(missing)))
                handle.write("\n\n")
            if errors:
                handle.write("⚠️ Errors:\n")
                handle.write("\n".join(f"- {item}" for item in sorted(errors)))
                handle.write("\n\n")
            if obsolete:
                handle.write("⚠️ Obsolete files present (should be removed):\n")
                handle.write("\n".join(f"- {item}" for item in sorted(obsolete)))
                handle.write("\n\n")

    if drift or missing or errors or obsolete:
        print("::warning::Consumer repo drift detected")
        return 1

    print("Consumer repos are in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
