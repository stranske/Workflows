#!/bin/bash
# Sync source scripts to template directory
set -e

SOURCE_DIR=".github/scripts"
TEMPLATE_DIR="templates/consumer-repo/.github/scripts"

echo "🔄 Syncing scripts to template directory..."

# Get list of files to sync (exclude tests)
FILES=$(find "$SOURCE_DIR" -name "*.js" -type f \
    | grep -v "__tests__" \
    | grep -v ".test.js" \
    | sed "s|^$SOURCE_DIR/||")

synced=0
for file in $FILES; do
    source_file="$SOURCE_DIR/$file"
    template_file="$TEMPLATE_DIR/$file"
    
    if [ -f "$template_file" ]; then
        if ! cmp -s "$source_file" "$template_file"; then
            echo "  ✓ Syncing $file"
            cp "$source_file" "$template_file"
            ((synced++))
        fi
    fi
done

if [ $synced -eq 0 ]; then
    echo "✅ All files already in sync"
else
    echo "✅ Synced $synced file(s)"
fi
