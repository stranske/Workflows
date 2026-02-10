#!/usr/bin/env python3
"""
Validate that template files are in sync with source files.

This prevents the common mistake of updating .github/scripts/ without
updating templates/consumer-repo/.github/scripts/, which causes sync
PRs to consumer repos to not be triggered.
"""

import hashlib
import sys
from pathlib import Path

import yaml


def hash_file(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hash_directory(path: Path) -> str:
    """Compute a combined SHA256 hash of all files in a directory."""
    h = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        if child.is_file():
            rel = child.relative_to(path)
            h.update(str(rel).encode())
            h.update(child.read_bytes())
    return h.hexdigest()


def main() -> int:
    repo_root = Path(__file__).parent.parent
    source_dir = repo_root / ".github" / "scripts"
    template_dir = repo_root / "templates" / "consumer-repo" / ".github" / "scripts"

    if not source_dir.exists():
        print(f"❌ Source directory not found: {source_dir}")
        return 1

    if not template_dir.exists():
        print(f"❌ Template directory not found: {template_dir}")
        return 1

    manifest_path = repo_root / ".github" / "sync-manifest.yml"
    if not manifest_path.exists():
        print(f"❌ sync-manifest.yml not found: {manifest_path}")
        return 1

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    manifest_scripts = []
    for entry in manifest.get("scripts", []) or []:
        source = entry.get("source", "")
        if source.startswith(".github/scripts/"):
            manifest_scripts.append(source.replace(".github/scripts/", "", 1))

    mismatches = []
    source_files = [source_dir / rel_path for rel_path in manifest_scripts]

    for source_file in source_files:
        relative_path = source_file.relative_to(source_dir)
        template_file = template_dir / relative_path

        if not source_file.exists():
            mismatches.append(relative_path)
            continue

        if not template_file.exists():
            mismatches.append(relative_path)
            continue

        if source_file.is_dir():
            source_hash = hash_directory(source_file)
            template_hash = hash_directory(template_file)
        else:
            source_hash = hash_file(source_file)
            template_hash = hash_file(template_file)

        if source_hash != template_hash:
            mismatches.append(relative_path)

    if mismatches:
        print("❌ Template files out of sync with source files:\n")
        for path in mismatches:
            template_file = template_dir / path
            if not template_file.exists():
                print(f"  • {path} (MISSING - needs to be created)")
            else:
                print(f"  • {path} (out of sync)")
        print("\n💡 To fix: ./scripts/sync_templates.sh")
        print("   Then: git add templates/consumer-repo/.github/scripts/")
        return 1

    print("✅ All template files in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
