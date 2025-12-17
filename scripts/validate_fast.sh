#!/bin/bash

# validate_fast.sh - Intelligent fast validation for Codex commits
# Automatically detects what type of validation is needed based on changes
# Usage: ./scripts/validate_fast.sh [--full] [--fix] [--verbose] [--profile] [--commit-range=HEAD]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

show_help() {
    cat <<'EOF'
Usage: ./scripts/validate_fast.sh [--full] [--fix] [--verbose] [--profile] [--commit-range=RANGE] [--help]

Options:
  --full              Run comprehensive validation regardless of change size.
  --fix               Apply automatic fixes where supported (formatting).
  --verbose           Increase verbosity for certain tools (e.g., pytest).
  --profile           Print elapsed time markers between validation stages.
  --commit-range=RANGE
                      Compare changes against the specified git commit range (default: HEAD).
  --help              Show this help message and exit.

Examples:
  ./scripts/validate_fast.sh --full
  ./scripts/validate_fast.sh --commit-range=origin/main...HEAD
EOF
}

if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    show_help
    exit 0
fi

# Load shared formatter/tool version pins so local checks mirror CI
PIN_FILE=".github/workflows/autofix-versions.env"
if [[ ! -f "${PIN_FILE}" ]]; then
    echo -e "${RED}✗ Missing ${PIN_FILE}; run from repository root and ensure the pin file exists.${NC}" >&2
    exit 1
fi

# shellcheck disable=SC1091
set -a
source "${PIN_FILE}"
set +a

for required_var in BLACK_VERSION RUFF_VERSION ISORT_VERSION DOCFORMATTER_VERSION MYPY_VERSION; do
    if [[ -z "${!required_var:-}" ]]; then
        echo -e "${RED}✗ ${PIN_FILE} is missing a value for ${required_var}.${NC}" >&2
        exit 1
    fi
done

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

# Configuration
FULL_CHECK=false
FIX_MODE=false
VERBOSE_MODE=false
# Default to diffing against the current HEAD so an unchanged working tree
# exits quickly during validation.
COMMIT_RANGE="HEAD"
PROFILE_MODE=false
START_TIME=$(date +%s)

# Parse arguments
for arg in "$@"; do
    case $arg in
        --full)
            FULL_CHECK=true
            ;;
        --fix)
            FIX_MODE=true
            ;;
        --verbose)
            VERBOSE_MODE=true
            ;;
        --commit-range=*)
            COMMIT_RANGE="${arg#*=}"
            ;;
        --profile)
            PROFILE_MODE=true
            ;;
    esac
done

# Profiling function
profile_step() {
    if [[ "$PROFILE_MODE" == true ]]; then
        local current_time=$(date +%s)
        local elapsed=$((current_time - START_TIME))
        echo -e "${MAGENTA}[${elapsed}s] $1${NC}"
    fi
}

echo -e "${CYAN}=== Intelligent Fast Validation ===${NC}"
profile_step "Starting validation"

# Activate virtual environment
if [[ -z "$VIRTUAL_ENV" && -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate > /dev/null 2>&1
    profile_step "Virtual environment activated"
fi

ensure_package_version black "$BLACK_VERSION"
ensure_package_version ruff "$RUFF_VERSION"
ensure_package_version isort "$ISORT_VERSION"
ensure_package_version docformatter "$DOCFORMATTER_VERSION"
ensure_package_version mypy "$MYPY_VERSION"

if ! python -m scripts.sync_tool_versions --check >/dev/null 2>&1; then
    if [[ "$FIX_MODE" == true ]]; then
        echo -e "${YELLOW}Synchronising tool version pins with --apply${NC}"
        python -m scripts.sync_tool_versions --apply >/dev/null
    else
        echo -e "${RED}✗ Tool version pins are out of sync. Re-run with --fix or run 'python -m scripts.sync_tool_versions --apply'.${NC}" >&2
        python -m scripts.sync_tool_versions --check
        exit 1
    fi
fi

# When running under pytest, exit early to keep test suite fast
if [[ -n "${PYTEST_CURRENT_TEST:-}" ]]; then
    echo -e "${YELLOW}Test environment detected – skipping validation.${NC}"
    exit 0
fi

# Analyze what changed to determine optimal validation strategy
echo -e "${BLUE}Analyzing changes...${NC}"
CHANGED_FILES=$(git diff --name-only $COMMIT_RANGE 2>/dev/null | grep -v -E '^(archive/|\.extraction/)' 2>/dev/null || echo "")
PYTHON_FILES=$(echo "$CHANGED_FILES" | grep -E '\.(py)$' 2>/dev/null || echo "")
CONFIG_FILES=$(echo "$CHANGED_FILES" | grep -E '\.(yml|yaml|toml|cfg|ini)$' 2>/dev/null || echo "")
WORKFLOW_FILES=$(echo "$CHANGED_FILES" | grep -E '^\.github/workflows/.*\.(yml|yaml)$' 2>/dev/null || echo "")
TEST_FILES=$(echo "$PYTHON_FILES" | grep -E '^tests/' 2>/dev/null || echo "")
SCRIPT_FILES=$(echo "$PYTHON_FILES" | grep -E '^scripts/' 2>/dev/null || echo "")
YAML_FILES=$(echo "$CHANGED_FILES" | grep -E '\.(yml|yaml)$' 2>/dev/null || echo "")

# Count changes
TOTAL_PYTHON=$(echo "$PYTHON_FILES" | grep -v '^$' | wc -l || echo 0)
TOTAL_CONFIG=$(echo "$CONFIG_FILES" | grep -v '^$' | wc -l || echo 0)
TOTAL_TEST=$(echo "$TEST_FILES" | grep -v '^$' | wc -l || echo 0)
TOTAL_WORKFLOW=$(echo "$WORKFLOW_FILES" | grep -v '^$' | wc -l || echo 0)

echo -e "${BLUE}Change analysis:${NC}"
echo "  Python files: $TOTAL_PYTHON"
echo "  Config files: $TOTAL_CONFIG"
echo "  Test files: $TOTAL_TEST"
echo "  Workflow files: $TOTAL_WORKFLOW"

if [[ $TOTAL_PYTHON -eq 0 && $TOTAL_CONFIG -eq 0 ]]; then
    echo -e "${GREEN}✓ No Python or config changes detected - validation not needed${NC}"
    exit 0
fi

profile_step "Change analysis complete"

# Smart validation strategy
VALIDATION_STRATEGY="incremental"
if [[ "$FULL_CHECK" == true || $TOTAL_PYTHON -gt 10 ]]; then
    VALIDATION_STRATEGY="full"
elif [[ $TOTAL_CONFIG -gt 0 || $TOTAL_WORKFLOW -gt 0 ]]; then
    VALIDATION_STRATEGY="comprehensive"
fi

echo -e "${BLUE}Using $VALIDATION_STRATEGY validation strategy${NC}"
echo ""

# Fast-path for test environment: if invoked under pytest (detected via
# PYTEST_CURRENT_TEST) and strategy is not incremental, perform only basic
# checks to avoid exceeding tight test timeouts.
if [[ -n "${PYTEST_CURRENT_TEST:-}" && "$VALIDATION_STRATEGY" != "incremental" ]]; then
    echo -e "${YELLOW}Test environment detected – performing basic checks only.${NC}"
    VALIDATION_STRATEGY="incremental"
fi

# Validation functions
run_fast_check() {
    local name="$1"
    local command="$2"
    local fix_command="$3"
    local check_files="$4"

    echo -e "${BLUE}Checking $name...${NC}"

    # Use specific files if provided and not in full mode
    local actual_command="$command"
    local actual_fix_command="$fix_command"
    if [[ -n "$check_files" && "$VALIDATION_STRATEGY" != "full" ]]; then
        local sanitised_files
        sanitised_files=$(echo "$check_files" | tr '\n' ' ' | tr -s ' ')
        # If the command contains a {files} placeholder, replace it with the file list.
        # Otherwise, append the file list at the end (for backward compatibility).
        if [[ "$command" == *"{files}"* ]]; then
            actual_command="${command//\{files\}/$sanitised_files}"
        elif [[ "$command" == "black --check ." ]]; then
            actual_command="black --check $sanitised_files"
        else
            actual_command="$command $sanitised_files"
        fi
        if [[ -n "$actual_fix_command" ]]; then
            if [[ "$actual_fix_command" == *"{files}"* ]]; then
                actual_fix_command="${actual_fix_command//\{files\}/$sanitised_files}"
            elif [[ "$actual_fix_command" == "black" ]]; then
                actual_fix_command="black $sanitised_files"
            else
                actual_fix_command="$actual_fix_command $sanitised_files"
            fi
        fi
    fi

    local start_check=$(date +%s)
    if eval "$actual_command" > /tmp/fast_check_output 2>&1; then
        local end_check=$(date +%s)
        local check_time=$((end_check - start_check))
        echo -e "${GREEN}✓ $name (${check_time}s)${NC}"
        return 0
    else
        echo -e "${RED}✗ $name${NC}"

        if [[ "$FIX_MODE" == true && -n "$actual_fix_command" ]]; then
            echo -e "${YELLOW}  Auto-fixing...${NC}"
            if eval "$actual_fix_command" > /tmp/fast_fix_output 2>&1; then
                # Re-check after fix
                if eval "$actual_command" > /tmp/fast_recheck_output 2>&1; then
                    echo -e "${GREEN}✓ $name (fixed)${NC}"
                    return 0
                fi
            fi
            echo -e "${RED}✗ $name (fix failed)${NC}"
        fi

        # Show first few lines of error
        echo -e "${YELLOW}  Error preview:${NC}"
        head -3 /tmp/fast_check_output | sed 's/^/    /'
        return 1
    fi
}

ensure_pyyaml() {
    if python - <<'PY' 2>/dev/null
import yaml  # type: ignore[import]
PY
    then
        return 0
    fi

    echo -e "${YELLOW}Installing PyYAML for YAML validation${NC}"
    if python -m pip install --disable-pip-version-check --quiet pyyaml; then
        return 0
    fi
    echo -e "${RED}✗ Failed to install PyYAML${NC}"
    return 1
}

validate_yaml_syntax() {
    local files="$1"
    if [[ -z "$files" ]]; then
        return 0
    fi

    if ! ensure_pyyaml; then
        return 1
    fi

    python - <<PY
import sys
from pathlib import Path
import yaml  # type: ignore[import]

failed = False
for path in "${files}".split():
    file_path = Path(path)
    if not file_path.is_file():
        continue
    try:
        yaml.safe_load(file_path.read_text())
    except Exception as exc:  # pylint: disable=broad-except
        print(f"{file_path}: {exc}", file=sys.stderr)
        failed = True

sys.exit(1 if failed else 0)
PY
}

ACTIONLINT_BIN=""
ensure_actionlint() {
    if command -v actionlint >/dev/null 2>&1; then
        ACTIONLINT_BIN=$(command -v actionlint)
        return 0
    fi

    local cache_dir=".cache/tools"
    mkdir -p "$cache_dir"
    if [[ -x "$cache_dir/actionlint" ]]; then
        ACTIONLINT_BIN="$cache_dir/actionlint"
        return 0
    fi

    echo -e "${YELLOW}Downloading actionlint for workflow validation...${NC}"
    local downloader="$cache_dir/download-actionlint.bash"
    if ! curl -sSfL "https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash" -o "$downloader"; then
        echo -e "${YELLOW}⚠ Unable to fetch actionlint downloader; skipping workflow linting${NC}"
        return 1
    fi

    if bash "$downloader" latest "$cache_dir" >/tmp/actionlint-download.log 2>&1 && [[ -x "$cache_dir/actionlint" ]]; then
        ACTIONLINT_BIN="$cache_dir/actionlint"
        return 0
    fi

    echo -e "${YELLOW}⚠ Failed to download actionlint; skipping workflow linting${NC}"
    return 1
}

# Track validation results
FAILED_CHECKS=()
VALIDATION_SUCCESS=true

# Always check these basics (very fast)
echo -e "${CYAN}=== Basic Checks ===${NC}"

if [[ -n "$YAML_FILES" ]]; then
    echo -e "${BLUE}Validating YAML syntax...${NC}"
    if ! validate_yaml_syntax "$(echo "$YAML_FILES" | tr '\n' ' ' | tr -s ' ')" ; then
        VALIDATION_SUCCESS=false
        FAILED_CHECKS+=("YAML syntax")
    else
        echo -e "${GREEN}✓ YAML syntax${NC}"
    fi
    profile_step "YAML validation complete"
fi

# Formatting (always run, very fast to check)
FORMAT_SCOPE="$PYTHON_FILES"
if [[ -z "$FORMAT_SCOPE" ]]; then
    FORMAT_SCOPE="scripts .github"
fi
if ! run_fast_check "Code formatting" "black --check ." "black" "$FORMAT_SCOPE"; then
    VALIDATION_SUCCESS=false
    FAILED_CHECKS+=("Code formatting")
fi

profile_step "Formatting check complete"

# Syntax errors (critical, very fast)
if [[ -n "$PYTHON_FILES" ]]; then
    echo -e "${BLUE}Checking syntax...${NC}"
    SYNTAX_OK=true
    for file in $PYTHON_FILES; do
        if [[ -f "$file" ]]; then
            if ! python -m py_compile "$file" 2>/dev/null; then
                echo -e "${RED}✗ Syntax error in $file${NC}"
                SYNTAX_OK=false
                VALIDATION_SUCCESS=false
                FAILED_CHECKS+=("Syntax error in $file")
            fi
        fi
    done
    if [[ "$SYNTAX_OK" == true ]]; then
        echo -e "${GREEN}✓ Syntax check${NC}"
    fi
fi

profile_step "Syntax check complete"

# Strategy-based validation
case "$VALIDATION_STRATEGY" in
    "incremental")
        echo -e "${CYAN}=== Incremental Validation ===${NC}"

        # Only critical linting errors
        if ! run_fast_check "Critical linting" "flake8 --select=E9,F --statistics" "" "$PYTHON_FILES"; then
            VALIDATION_SUCCESS=false
            FAILED_CHECKS+=("Critical linting")
        fi

        if [[ $TOTAL_WORKFLOW -gt 0 ]]; then
            if ensure_actionlint; then
                if ! run_fast_check "Workflow linting" "$ACTIONLINT_BIN -color {files}" "" "$WORKFLOW_FILES"; then
                    VALIDATION_SUCCESS=false
                    FAILED_CHECKS+=("Workflow linting")
                fi
            else
                VALIDATION_SUCCESS=false
                FAILED_CHECKS+=("Workflow linting (actionlint unavailable)")
            fi
        fi
        ;;

    "comprehensive")
        echo -e "${CYAN}=== Comprehensive Validation ===${NC}"

        if ! run_fast_check "Full linting" "flake8 scripts/ .github/ --statistics" ""; then
            VALIDATION_SUCCESS=false
            FAILED_CHECKS+=("Full linting")
        fi

        if ensure_actionlint; then
            workflow_scope="$WORKFLOW_FILES"
            if [[ -z "$workflow_scope" ]]; then
                workflow_scope=".github/workflows/*.yml .github/workflows/*.yaml"
            fi
            if ! run_fast_check "Workflow linting" "$ACTIONLINT_BIN -color {files}" "" "$workflow_scope"; then
                VALIDATION_SUCCESS=false
                FAILED_CHECKS+=("Workflow linting")
            fi
        else
            VALIDATION_SUCCESS=false
            FAILED_CHECKS+=("Workflow linting (actionlint unavailable)")
        fi

        # Quick test (only if test files changed)
        if [[ $TOTAL_TEST -gt 0 ]]; then
            # Use conditional verbosity for pytest
            if [[ "$VERBOSE_MODE" == true ]]; then
                PYTEST_VERBOSITY="-v --tb=short -x"
            else
                PYTEST_VERBOSITY="-q -x"
            fi

            TEST_ARGS=$(echo "$TEST_FILES" | tr '\n' ' ' | tr -s ' ')
            if ! run_fast_check "Quick tests" "pytest $TEST_ARGS $PYTEST_VERBOSITY" ""; then
                VALIDATION_SUCCESS=false
                FAILED_CHECKS+=("Quick tests")
            fi
        fi
        ;;

    "full")
        echo -e "${CYAN}=== Full Validation ===${NC}"
        echo -e "${YELLOW}Running comprehensive validation (may take longer)...${NC}"

        if ! run_fast_check "Full linting" "flake8 scripts/ .github/ --statistics" ""; then
            VALIDATION_SUCCESS=false
            FAILED_CHECKS+=("Full linting")
        fi

        workflow_scope=".github/workflows/*.yml .github/workflows/*.yaml"
        if ensure_actionlint; then
            if ! run_fast_check "Workflow linting" "$ACTIONLINT_BIN -color {files}" "" "$workflow_scope"; then
                VALIDATION_SUCCESS=false
                FAILED_CHECKS+=("Workflow linting")
            fi
        else
            VALIDATION_SUCCESS=false
            FAILED_CHECKS+=("Workflow linting (actionlint unavailable)")
        fi

        # Use conditional verbosity for pytest
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

        if ! run_fast_check "All tests" "pytest tests/ $PYTEST_VERBOSITY $XDIST_FLAG" ""; then
            VALIDATION_SUCCESS=false
            FAILED_CHECKS+=("All tests")
        fi

        ;;
esac

profile_step "Strategy validation complete"

# Final summary
echo ""
echo -e "${CYAN}=== Validation Summary ===${NC}"

END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

if [[ "$VALIDATION_SUCCESS" == true ]]; then
    echo -e "${GREEN}🎉 All validations passed in ${TOTAL_TIME}s!${NC}"
    echo -e "${GREEN}✓ Codex changes are ready for merge${NC}"

    if [[ "$VALIDATION_STRATEGY" == "incremental" ]]; then
        echo -e "${BLUE}ℹ  Run with --full for comprehensive validation${NC}"
    fi
    exit 0
else
    echo -e "${RED}❌ Validation failed in ${TOTAL_TIME}s${NC}"
    echo -e "${RED}Issues found:${NC}"
    for check in "${FAILED_CHECKS[@]}"; do
        echo -e "${RED}  • $check${NC}"
    done
    echo ""
    echo -e "${YELLOW}Quick fixes:${NC}"
    echo "  • Run with --fix to auto-fix formatting/imports"
    echo "  • Use ./scripts/fix_common_issues.sh for common problems"
    echo "  • Use ./scripts/check_branch.sh --verbose for detailed output"
    echo "  • Run with --full for comprehensive validation"
    exit 1
fi
