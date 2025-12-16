#!/bin/bash

# check_branch.sh - Validate Codex commits before merging
# Usage: ./scripts/check_branch.sh [--verbose] [--fix] [--fast]

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Load formatter version pins to stay aligned with CI checks
if [[ -f ".github/workflows/autofix-versions.env" ]]; then
    # shellcheck disable=SC1091
    source .github/workflows/autofix-versions.env
fi
BLACK_VERSION=${BLACK_VERSION:-25.11.0}

ensure_package_version() {
    local package_name="$1"
    local pinned_version="$2"
    local module_name="${3:-$1}"

    if [[ -z "$pinned_version" ]]; then
        return 0
    fi

    local current_version
    current_version=$(python - <<PY 2>/dev/null
try:
    import ${module_name} as _pkg  # type: ignore[import]
    print(getattr(_pkg, "__version__", ""))
except Exception:
    print("")
PY
)

    if [[ "$current_version" != "$pinned_version" ]]; then
        echo -e "${YELLOW}Installing ${package_name}==${pinned_version} to match CI${NC}"
        python -m pip install --disable-pip-version-check --quiet "${package_name}==${pinned_version}"
    fi
}

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}Error: Not in a git repository${NC}"
    exit 1
fi

# TODO Phase 4: Revisit venv activation for workflow repository
# Check if virtual environment is activated
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo -e "${YELLOW}Warning: Virtual environment not activated. Attempting to activate...${NC}"
    if [[ -f ".venv/bin/activate" ]]; then
        source .venv/bin/activate
        echo -e "${GREEN}Virtual environment activated${NC}"
    else
        echo -e "${RED}Error: No virtual environment found at .venv/${NC}"
        exit 1
    fi
fi

ensure_package_version black "$BLACK_VERSION"

# Parse command line arguments
VERBOSE_MODE=false
FIX_MODE=false
FAST_MODE=false

for arg in "$@"; do
    case $arg in
        --verbose)
            VERBOSE_MODE=true
            echo -e "${BLUE}Running in verbose mode - showing detailed output${NC}"
            ;;
        --fix)
            FIX_MODE=true
            echo -e "${BLUE}Running in fix mode - will attempt to auto-fix issues${NC}"
            ;;
        --fast)
            FAST_MODE=true
            echo -e "${BLUE}Running in fast mode - skip slow checks${NC}"
            ;;
    esac
done

echo -e "${BLUE}=== Codex Commit Validation ===${NC}"
echo "Current branch: $(git branch --show-current)"
echo "Latest commit: $(git log --oneline -1)"
echo "Commit author: $(git log -1 --format='%an <%ae>')"
echo ""

if ! python -m scripts.sync_tool_versions --check >/dev/null 2>&1; then
    if [[ "$FIX_MODE" == true ]]; then
        echo -e "${YELLOW}Synchronising tool version pins with --apply${NC}"
        if ! python -m scripts.sync_tool_versions --apply >/dev/null 2>&1; then
            echo -e "${RED}✗ Failed to align tool pins automatically.${NC}" >&2
            python -m scripts.sync_tool_versions --check
            exit 1
        fi
    else
        echo -e "${RED}✗ Tool version pins are out of sync. Re-run with --fix or run 'python -m scripts.sync_tool_versions --apply'.${NC}" >&2
        python -m scripts.sync_tool_versions --check
        exit 1
    fi
fi

# Show recent commits for context
echo -e "${BLUE}Recent commits:${NC}"
git log --oneline -5
echo ""

# Function to run a validation check with auto-fix capability
run_validation() {
    local name="$1"
    local command="$2"
    local fix_command="$3"

    echo -e "${BLUE}Validating $name...${NC}"

    # Run the check
    local check_passed=false
    if [[ "$VERBOSE_MODE" == true ]]; then
        if eval "$command"; then
            check_passed=true
        fi
    else
        if eval "$command" > /tmp/check_output 2>&1; then
            check_passed=true
        fi
    fi

    if [[ "$check_passed" == true ]]; then
        echo -e "${GREEN}✓ $name: PASSED${NC}"
        return 0
    else
        echo -e "${RED}✗ $name: FAILED${NC}"

        # Try to auto-fix if requested and fix command is available
        if [[ "$FIX_MODE" == true && -n "$fix_command" ]]; then
            echo -e "${YELLOW}  Attempting auto-fix...${NC}"
            if eval "$fix_command" > /tmp/fix_output 2>&1; then
                # Re-run the check to see if it's fixed
                if eval "$command" > /tmp/recheck_output 2>&1; then
                    echo -e "${GREEN}✓ $name: FIXED${NC}"
                    return 0
                else
                    echo -e "${RED}✗ $name: Auto-fix failed${NC}"
                    return 1
                fi
            else
                echo -e "${RED}✗ $name: Auto-fix command failed${NC}"
                return 1
            fi
        else
            if [[ "$VERBOSE_MODE" == false ]]; then
                echo -e "${YELLOW}  Use --verbose to see detailed output${NC}"
            fi
            return 1
        fi
    fi
}

# Track validation results
VALIDATION_SUCCESS=true
FAILED_CHECKS=()

echo -e "${BLUE}=== Code Quality Validation ===${NC}"
if ! run_validation "Black formatting" "black --check scripts/ .github/" "black scripts/ .github/"; then
    VALIDATION_SUCCESS=false
    FAILED_CHECKS+=("Black formatting")
fi

echo ""
if ! run_validation "Flake8 linting" "flake8 scripts/" ""; then
    VALIDATION_SUCCESS=false
    FAILED_CHECKS+=("Flake8 linting")
fi

echo ""
# TODO Phase 4: Replace MyPy type checking with workflow-specific validation
# if ! run_validation "MyPy type checking" "mypy src/" "mypy --install-types --non-interactive"; then
#     VALIDATION_SUCCESS=false
#     FAILED_CHECKS+=("MyPy type checking")
# fi
echo -e "${YELLOW}⚠ Type checking deferred to Phase 4 (workflow validation)${NC}"

if [[ "$FAST_MODE" == false ]]; then
    echo ""
    echo -e "${BLUE}=== Functionality Validation ===${NC}"
    # TODO Phase 4: Remove pip install check (not applicable to workflow repo)
    # if ! run_validation "Package installation" "pip install -e ." ""; then
    #     VALIDATION_SUCCESS=false
    #     FAILED_CHECKS+=("Package installation")
    # fi
    echo -e "${YELLOW}⚠ Package installation check deferred to Phase 4 (not applicable to workflows)${NC}"

    echo ""
    # TODO Phase 4: Replace Python import validation with workflow validation
    # if ! run_validation "Import validation" "python -c 'import src.trend_analysis; print(\"All imports successful\")'" ""; then
    #     VALIDATION_SUCCESS=false
    #     FAILED_CHECKS+=("Import validation")
    # fi
    echo -e "${YELLOW}⚠ Import validation deferred to Phase 4 (workflow validation)${NC}"

    echo ""
    # Use conditional verbosity for pytest based on VERBOSE_MODE
    if [[ "$VERBOSE_MODE" == true ]]; then
        PYTEST_VERBOSITY="-v --tb=short"
    else
        PYTEST_VERBOSITY="-q"
    fi

    # Add parallel execution if xdist available
    XDIST_FLAG=""
    if python -c "import xdist" 2>/dev/null; then
        XDIST_FLAG="-n auto"
    fi

    if ! run_validation "Unit tests" "pytest tests/ $PYTEST_VERBOSITY $XDIST_FLAG" ""; then
        VALIDATION_SUCCESS=false
        FAILED_CHECKS+=("Unit tests")
    fi

    echo ""
    # TODO Phase 4: Remove coverage requirement (Python package specific)
    # if ! run_validation "Test coverage" "rm -f .coverage .coverage.* && pytest --cov=src --cov-report=term-missing --cov-fail-under=80 --cov-branch $XDIST_FLAG" ""; then
    #     VALIDATION_SUCCESS=false
    #     FAILED_CHECKS+=("Test coverage")
    # fi
    echo -e "${YELLOW}⚠ Test coverage check deferred to Phase 4 (Python package specific)${NC}"
else
    echo ""
    echo -e "${YELLOW}Skipping slow checks in fast mode${NC}"
fi

# Check for uncommitted changes (important for Codex workflow)
echo ""
echo -e "${BLUE}=== Git Status Check ===${NC}"
if [[ -n "$(git status --porcelain)" ]]; then
    echo -e "${YELLOW}⚠ Uncommitted changes detected:${NC}"
    git status --short
    echo ""
    echo -e "${YELLOW}Note: Codex may have made additional changes not yet committed${NC}"
else
    echo -e "${GREEN}✓ No uncommitted changes${NC}"
fi

# Check if this branch is ahead of its tracking branch
CURRENT_BRANCH=$(git branch --show-current)
TRACKING_BRANCH=$(git for-each-ref --format='%(upstream:short)' refs/heads/$CURRENT_BRANCH)
if [[ -n "$TRACKING_BRANCH" ]]; then
    AHEAD_COUNT=$(git rev-list --count HEAD ^$TRACKING_BRANCH 2>/dev/null || echo "0")
    if [[ "$AHEAD_COUNT" -gt 0 ]]; then
        echo -e "${BLUE}Branch is $AHEAD_COUNT commits ahead of $TRACKING_BRANCH${NC}"
    fi
fi

# Final validation summary
echo ""
echo -e "${BLUE}=== Validation Summary ===${NC}"
if [[ "$VALIDATION_SUCCESS" == true ]]; then
    echo -e "${GREEN}🎉 All validations passed! Codex commits look good for merge${NC}"
    echo -e "${GREEN}✓ Ready to merge or continue development${NC}"
    exit 0
else
    echo -e "${RED}❌ Validation failed. Issues found in Codex commits:${NC}"
    for check in "${FAILED_CHECKS[@]}"; do
        echo -e "${RED}  • $check${NC}"
    done
    echo ""
    echo -e "${YELLOW}Recommendations:${NC}"
    echo "  • Review the failed checks above"
    echo "  • Use --verbose for detailed error output"
    echo "  • Use --fix to auto-fix formatting and type issues"
    echo "  • Use --fast to skip slow tests during development"
    echo "  • Consider requesting Codex to fix the specific issues"
    echo "  • Check recent commits: git log --oneline -5"
    exit 1
fi
