#!/usr/bin/env python3
"""
Validate that exact template-sync files match their source files.

This prevents the common mistake of updating source files that are copied
into templates/consumer-repo/ without updating the matching template files,
which causes sync PRs to consumer repos to miss the source change.
"""

import sys
from pathlib import Path

# Ensure the scripts package is importable when run as a subprocess from any cwd.
sys.path.insert(0, str(Path(__file__).parent))

import hashlib  # noqa: E402

from sync_manifest_compiler import (  # noqa: E402
    CompiledManifest,
    ManifestCompileError,
    compile_manifest,
)


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


def _manifest_template_sync_sources(compiled: CompiledManifest) -> list[str]:
    sources: list[str] = []
    for entry in compiled.section("scripts"):
        if entry.source.startswith(".github/scripts/"):
            sources.append(entry.source)
            continue
        if entry.template_sync == "exact":
            sources.append(entry.source)
    return sorted(set(sources))


def _format_stage_paths(template_root: Path, mismatches: list[Path]) -> list[str]:
    return [str(template_root / path) for path in mismatches]


def main() -> int:
    repo_root = Path(__file__).parent.parent
    template_root = repo_root / "templates" / "consumer-repo"
    source_dir = repo_root / ".github" / "scripts"
    template_dir = template_root / ".github" / "scripts"

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

    try:
        compiled = compile_manifest(manifest_path)
    except ManifestCompileError as exc:
        print(f"❌ Manifest is invalid:\n{exc}")
        return 1

    manifest_sources = _manifest_template_sync_sources(compiled)

    mismatches = []
    for source in manifest_sources:
        source_file = repo_root / source
        template_file = template_root / source
        relative_path = Path(source)

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
            template_file = template_root / path
            if not template_file.exists():
                print(f"  • {path} (MISSING - needs to be created)")
            else:
                print(f"  • {path} (out of sync)")
        print("\n💡 To fix: ./scripts/sync_templates.sh")
        print("   Then stage the affected template path(s):")
        for path in _format_stage_paths(Path("templates") / "consumer-repo", mismatches):
            print(f"     git add {path}")
        return 1

    print("✅ All template files in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
