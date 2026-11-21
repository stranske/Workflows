#!/bin/bash
# Script to fix formatting issues in Workflows-Integration-Tests repository
# This applies the black formatter to the files that were causing CI failures

set -euo pipefail

REPO_DIR="${1:-.}"

CDPATH='' cd -- "$REPO_DIR"

if [[ ! -f .github/workflows/notify-workflows.yml ]]; then
    printf 'Use the Workflows-Integration-Tests checkout. %s has no integration notifier.\n' \
        "$PWD" >&2
    exit 1
fi

format_targets=(
    scripts/validate_dependency_test_setup.py
    tests/test_dependency_version_alignment.py
)

for target in "${format_targets[@]}"; do
    if [[ ! -f "$target" || -L "$target" ]]; then
        printf 'Expected a regular integration formatting input at %s in %s.\n' \
            "$target" "$PWD" >&2
        exit 1
    fi
done

echo "Fixing formatting issues in Integration-Tests repository..."

# Install black if not available
if ! command -v black &> /dev/null; then
    echo "Installing black..."
    python3 -m pip install black --quiet
fi

# Format the problematic files
black "${format_targets[@]}"

echo "✅ Formatting complete!"
echo ""
echo "Changes made:"
git --no-pager diff --stat

echo ""
echo "To commit and push these changes:"
echo "  git add -A"
echo "  git commit -m 'fix: Auto-format files to meet lint standards'"
echo "  git push"
