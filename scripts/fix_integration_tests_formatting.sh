#!/usr/bin/env bash
# Fix formatting and lint issues in Workflows-Integration-Tests repo
#
# This script should be run from the Workflows-Integration-Tests repository root.
# It applies black formatting and ruff linting fixes.
#
# Usage:
#   cd /path/to/Workflows-Integration-Tests
#   bash /path/to/this/script.sh

set -euo pipefail

echo "🔍 Checking current directory..."
if [ ! -f "pyproject.toml" ] || [ ! -d "tests" ]; then
    echo "❌ Error: This script must be run from the Workflows-Integration-Tests repository root"
    echo "   Expected files: pyproject.toml, tests/"
    exit 1
fi

echo "✅ Found Integration Tests repository"
echo ""

echo "📦 Installing formatting/linting tools..."
python3 -m pip install --quiet --upgrade black ruff

echo ""
echo "🎨 Running black formatter..."
python3 -m black .

echo ""
echo "🔧 Running ruff linter with auto-fix..."
python3 -m ruff check --fix .

echo ""
echo "✅ Formatting and linting complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Review the changes: git diff"
echo "   2. Commit the changes: git add -A && git commit -m 'fix: auto-format and lint test files'"
echo "   3. Push to remote: git push origin main"
echo ""
echo "   Or create a PR if you prefer:"
echo "   git checkout -b fix/formatting"
echo "   git push origin fix/formatting"
echo "   # Then open a PR on GitHub"
