#!/bin/bash
# Check and report on test environment dependencies
# This script validates that all required tools for running the test suite are available.

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Test Dependencies Check ==="
echo ""

# Track overall status
all_ok=true

# Check Python version
echo "Checking Python version..."
python_version=$(python --version 2>&1 | awk '{print $2}')
python_major=$(echo "$python_version" | cut -d. -f1)
python_minor=$(echo "$python_version" | cut -d. -f2)

if [[ "$python_major" -ge 3 ]] && [[ "$python_minor" -ge 11 ]]; then
    echo -e "${GREEN}✓${NC} Python $python_version (>=3.11 required)"
else
    echo -e "${RED}✗${NC} Python $python_version (>=3.11 required)"
    all_ok=false
fi
echo ""

# Check required Python packages
echo "Checking required Python packages..."
required_packages=(
    "pytest"
    "coverage"
    "hypothesis"
    "pandas"
    "numpy"
    "pydantic"
    "yaml:PyYAML"
    "requests"
    "jsonschema"
)

for pkg_spec in "${required_packages[@]}"; do
    # Handle module:package name mapping (e.g., yaml:PyYAML)
    if [[ "$pkg_spec" == *":"* ]]; then
        module_name=$(echo "$pkg_spec" | cut -d: -f1)
        pkg_name=$(echo "$pkg_spec" | cut -d: -f2)
    else
        module_name="$pkg_spec"
        pkg_name="$pkg_spec"
    fi

    if python -c "import $module_name" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $pkg_name"
    else
        echo -e "${RED}✗${NC} $pkg_name (missing)"
        all_ok=false
    fi
done
echo ""

# Check optional Python packages
echo "Checking optional Python packages..."
optional_packages=(
    "black"
    "ruff"
    "mypy"
    "streamlit"
    "fastapi"
)

for pkg in "${optional_packages[@]}"; do
    if python -c "import $pkg" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $pkg"
    else
        echo -e "${YELLOW}○${NC} $pkg (optional, not installed)"
    fi
done
echo ""

# Check Node.js
echo "Checking Node.js..."
if command -v node &> /dev/null; then
    node_version=$(node --version)
    echo -e "${GREEN}✓${NC} Node.js $node_version"
else
    echo -e "${YELLOW}○${NC} Node.js (not found - JavaScript tests will be skipped)"
    echo "  Install from: https://nodejs.org/"
fi
echo ""

# Check npm
echo "Checking npm..."
if command -v npm &> /dev/null; then
    npm_version=$(npm --version)
    echo -e "${GREEN}✓${NC} npm $npm_version"
else
    echo -e "${YELLOW}○${NC} npm (not found - usually bundled with Node.js)"
fi
echo ""

# Check uv
echo "Checking uv..."
if command -v uv &> /dev/null; then
    uv_version=$(uv --version 2>&1 | head -n1)
    echo -e "${GREEN}✓${NC} uv ($uv_version)"
else
    echo -e "${YELLOW}○${NC} uv (not found - lockfile tests will be skipped)"
    echo "  Install from: https://github.com/astral-sh/uv"
fi
echo ""

# Check coverage CLI
echo "Checking coverage CLI..."
if command -v coverage &> /dev/null; then
    coverage_version=$(coverage --version 2>&1 | head -n1)
    echo -e "${GREEN}✓${NC} coverage ($coverage_version)"
else
    echo -e "${RED}✗${NC} coverage CLI (not found)"
    all_ok=false
fi
echo ""

# Summary
echo "=== Summary ==="
if [ "$all_ok" = true ]; then
    echo -e "${GREEN}All required dependencies are available!${NC}"
    echo ""
    echo "You can run the full test suite with:"
    echo "  ./scripts/run_tests.sh"
    exit 0
else
    echo -e "${RED}Some required dependencies are missing!${NC}"
    echo ""
    echo "Install missing Python packages:"
    echo "  pip install uv"
    echo "  uv pip sync requirements.lock"
    echo "  pip install --no-deps -e '.[dev]'"
    exit 1
fi
