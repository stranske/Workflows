#!/bin/bash
# Sync source scripts to template directory
set -e

SOURCE_DIR=".github/scripts"
TEMPLATE_DIR="templates/consumer-repo/.github/scripts"

echo "🔄 Syncing scripts to template directory..."

# Get list of files to sync from sync-manifest.yml
FILES=$(python - <<'PY'
from pathlib import Path
import sys

try:
    import yaml
except Exception as exc:  # pragma: no cover - runtime environment only
    print("❌ PyYAML is required to sync templates. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

manifest_path = Path(".github/sync-manifest.yml")
if not manifest_path.exists():
    print("❌ sync-manifest.yml not found", file=sys.stderr)
    sys.exit(1)

manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
scripts = []
for entry in manifest.get("scripts", []) or []:
    source = entry.get("source", "")
    if source.startswith(".github/scripts/"):
        scripts.append(source.replace(".github/scripts/", "", 1))

print("\n".join(sorted(set(scripts))))
PY
)

synced=0
for file in $FILES; do
    source_file="$SOURCE_DIR/$file"
    template_file="$TEMPLATE_DIR/$file"

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
done

if [ $synced -eq 0 ]; then
    echo "✅ All files already in sync"
else
    echo "✅ Synced $synced file(s)"
fi
