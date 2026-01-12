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


def hash_file(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    # Files that should be synced (exclude test files and some specific scripts)
    exclude_patterns = ["__tests__", ".test.js", "deploy", "release"]

    mismatches = []
    source_files = [
        f
        for f in source_dir.rglob("*.js")
        if not any(pattern in str(f) for pattern in exclude_patterns)
    ]

    for source_file in source_files:
        relative_path = source_file.relative_to(source_dir)
        template_file = template_dir / relative_path

        if not template_file.exists():
            mismatches.append(relative_path)
            continue

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
