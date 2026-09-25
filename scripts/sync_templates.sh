#!/bin/bash
# Sync source scripts to template directory
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
TEMPLATE_ROOT="$REPO_ROOT/templates/consumer-repo"

cd "$REPO_ROOT"

echo "🔄 Syncing scripts to template directory..."

# Compile the complete manifest before touching the filesystem. Do not use
# process substitution here: Bash does not propagate the producer's failure.
if ! FILES=$(python scripts/validate_template_sync.py --print-sources); then
    echo "❌ Refusing to sync templates from an invalid manifest" >&2
    exit 1
fi

validate_sync_path() {
    python - "$REPO_ROOT" "$TEMPLATE_ROOT" "$1" <<'PY'
from pathlib import Path
import sys

repo_root = Path(sys.argv[1]).resolve(strict=True)
template_root = Path(sys.argv[2])
relative = Path(sys.argv[3])


def fail(message: str) -> None:
    print(f"❌ Unsafe template-sync path {relative}: {message}", file=sys.stderr)
    raise SystemExit(1)


def reject_symlink_components(path: Path, anchor: Path) -> None:
    try:
        relative_parts = path.relative_to(anchor).parts
    except ValueError:
        fail(f"{path} is outside {anchor}")
    current = anchor
    for part in relative_parts:
        current /= part
        if current.is_symlink():
            fail(f"symlink component is not allowed: {current}")


if not template_root.exists() or not template_root.is_dir() or template_root.is_symlink():
    fail(f"template root is not a real directory: {template_root}")
reject_symlink_components(template_root, repo_root)

source = repo_root / relative
destination = template_root / relative
reject_symlink_components(source, repo_root)
reject_symlink_components(destination, repo_root)

try:
    source_resolved = source.resolve(strict=True)
except OSError as exc:
    fail(f"source cannot be resolved: {exc}")
template_resolved = template_root.resolve(strict=True)
destination_resolved = destination.resolve(strict=False)

try:
    source_resolved.relative_to(repo_root)
except ValueError:
    fail("source resolves outside the repository")
try:
    destination_relative = destination_resolved.relative_to(template_resolved)
except ValueError:
    fail("destination resolves outside the template root")
if not destination_relative.parts:
    fail("destination equals the template root")
if source_resolved == destination_resolved:
    fail("source and destination are identical")
if source_resolved in destination_resolved.parents or destination_resolved in source_resolved.parents:
    fail("source and destination overlap")

if source_resolved.is_dir():
    for child in source_resolved.rglob("*"):
        if child.is_symlink():
            fail(f"source directory contains a symlink: {child}")
PY
}

# Validate every entry before the first mkdir, copy, or removal. Revalidate each
# entry immediately before mutation to catch ordinary local path changes.
while IFS= read -r file; do
    [ -n "$file" ] || continue
    validate_sync_path "$file"
done <<< "$FILES"

synced=0
while IFS= read -r file; do
    [ -n "$file" ] || continue
    validate_sync_path "$file"
    source_file="$REPO_ROOT/$file"
    template_file="$TEMPLATE_ROOT/$file"

    # Create parent directory if it doesn't exist
    mkdir -p "$(dirname "$template_file")"

    if [ -d "$source_file" ]; then
        # Handle directory entries (e.g. vendored node_modules)
        if [ ! -d "$template_file" ] || ! diff -qr "$source_file" "$template_file" > /dev/null 2>&1; then
            if [ -d "$template_file" ]; then
                echo "  ✓ Syncing $file (directory)"
            else
                echo "  ✓ Creating $file (new directory)"
            fi
            rm -rf "$template_file"
            cp -r "$source_file" "$template_file"
            synced=$((synced + 1)) || true
        fi
    elif [ ! -f "$template_file" ]; then
        echo "  ✓ Creating $file (new file)"
        cp "$source_file" "$template_file"
        synced=$((synced + 1)) || true
    elif ! cmp -s "$source_file" "$template_file"; then
        echo "  ✓ Syncing $file"
        cp "$source_file" "$template_file"
        synced=$((synced + 1)) || true
    fi
done <<< "$FILES"

if [ $synced -eq 0 ]; then
    echo "✅ All files already in sync"
else
    echo "✅ Synced $synced file(s)"
fi
