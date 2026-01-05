#!/bin/bash
# Sync test helper utilities to consumer repos
# 
# This script copies shared test utilities from the Workflows repo
# to consumer repos, ensuring consistent testing patterns across all projects.
#
# Usage:
#   ./scripts/sync_test_helpers.sh [--check] [--repo path/to/repo]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOWS_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATES_DIR="$WORKFLOWS_ROOT/templates/test_helpers"

# Default to checking current repo
CHECK_MODE=false
TARGET_REPO="."

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --check)
            CHECK_MODE=true
            shift
            ;;
        --repo)
            TARGET_REPO="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--check] [--repo path/to/repo]"
            exit 1
            ;;
    esac
done

# Resolve target repo path
TARGET_REPO="$(cd "$TARGET_REPO" && pwd)"
TARGET_HELPERS_DIR="$TARGET_REPO/tests/helpers"

echo "Syncing test helpers..."
echo "  Source: $TEMPLATES_DIR"
echo "  Target: $TARGET_HELPERS_DIR"
echo ""

# Create target directory if it doesn't exist
if [[ ! -d "$TARGET_HELPERS_DIR" ]]; then
    if [[ "$CHECK_MODE" == "true" ]]; then
        echo "❌ Target directory missing: $TARGET_HELPERS_DIR"
        exit 1
    fi
    mkdir -p "$TARGET_HELPERS_DIR"
    echo "📁 Created $TARGET_HELPERS_DIR"
fi

# Ensure __init__.py exists
INIT_FILE="$TARGET_HELPERS_DIR/__init__.py"
if [[ ! -f "$INIT_FILE" ]]; then
    if [[ "$CHECK_MODE" == "true" ]]; then
        echo "⚠️  Missing __init__.py"
    else
        touch "$INIT_FILE"
        echo "📝 Created __init__.py"
    fi
fi

# Sync each helper file
changes=0
for helper_file in "$TEMPLATES_DIR"/*.py; do
    if [[ ! -f "$helper_file" ]]; then
        continue
    fi
    
    filename="$(basename "$helper_file")"
    target_file="$TARGET_HELPERS_DIR/$filename"
    
    if [[ ! -f "$target_file" ]]; then
        if [[ "$CHECK_MODE" == "true" ]]; then
            echo "⚠️  Missing: $filename"
            changes=$((changes + 1))
        else
            cp "$helper_file" "$target_file"
            echo "✅ Added: $filename"
            changes=$((changes + 1))
        fi
    elif ! diff -q "$helper_file" "$target_file" > /dev/null 2>&1; then
        if [[ "$CHECK_MODE" == "true" ]]; then
            echo "⚠️  Out of sync: $filename"
            changes=$((changes + 1))
        else
            cp "$helper_file" "$target_file"
            echo "✅ Updated: $filename"
            changes=$((changes + 1))
        fi
    else
        echo "✓ Up to date: $filename"
    fi
done

echo ""
if [[ "$CHECK_MODE" == "true" ]]; then
    if [[ $changes -gt 0 ]]; then
        echo "❌ Found $changes file(s) that need syncing"
        echo "Run without --check to apply changes"
        exit 1
    else
        echo "✅ All test helpers are in sync"
        exit 0
    fi
else
    if [[ $changes -gt 0 ]]; then
        echo "✅ Synced $changes file(s)"
    else
        echo "✅ No changes needed"
    fi
    exit 0
fi
