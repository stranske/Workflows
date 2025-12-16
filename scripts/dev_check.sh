#!/bin/bash

# dev_check.sh - Ultra-fast development validation for Codex workflow
# Usage: ./scripts/dev_check.sh [--fix] [--changed] [--verbose]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Load shared formatter/tool version pins (align with CI defaults)
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

# Command line options
FIX_MODE=false
CHANGED_ONLY=false
VERBOSE_MODE=false
CHECK_TIMEOUT=${DEV_CHECK_TIMEOUT:-120}
BLACK_TARGETS=${DEV_CHECK_BLACK_TARGETS:-"scripts .github"}

for arg in "$@"; do
    case $arg in
        --fix)
            FIX_MODE=true
            ;;
        --changed)
            CHANGED_ONLY=true
            ;;
        --verbose)
            VERBOSE_MODE=true
            ;;
    esac
done

if [[ "$CHANGED_ONLY" == true && -z "${DEV_CHECK_TIMEOUT:-}" ]]; then
    CHECK_TIMEOUT=25
fi

echo -e "${CYAN}=== Ultra-Fast Development Check ===${NC}"

# Activate virtual environment if needed
if [[ -z "$VIRTUAL_ENV" && -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate > /dev/null 2>&1
fi

# Ensure formatter tooling is available (black, isort, docformatter, ruff) and include lint tooling.
ensure_python_packages() {
    local missing=()
    for package in "$@"; do
        if python - <<PY 2>/dev/null
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec("${package}") else 1)
PY
        then
            continue
        else
            missing+=("$package")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo -e "${YELLOW}Installing formatter tooling: ${missing[*]}${NC}"
        if python -m pip install --disable-pip-version-check --quiet "${missing[@]}" > /tmp/dev_check_install 2>&1; then
            echo -e "${GREEN}✓ Formatter tooling ready${NC}"
        else
            echo -e "${RED}✗ Failed to install formatter tooling${NC}"
            head -10 /tmp/dev_check_install | sed 's/^/  /'
            exit 1
        fi
    fi
}

# Ensure lint tooling (flake8) is also available for critical error checks.
ensure_python_packages black isort docformatter ruff flake8
ensure_package_version black "$BLACK_VERSION"
ensure_package_version ruff "$RUFF_VERSION"
ensure_package_version isort "$ISORT_VERSION"
ensure_package_version docformatter "$DOCFORMATTER_VERSION"
ensure_package_version mypy "$MYPY_VERSION"

# Ensure repo-wide tool pins stay aligned before running further checks.
if ! python -m scripts.sync_tool_versions --check >/dev/null 2>&1; then
    if [[ "$FIX_MODE" == true ]]; then
        echo -e "${YELLOW}Synchronising tool version pins with --apply${NC}"
        python -m scripts.sync_tool_versions --apply >/dev/null
    else
        echo -e "${RED}✗ Tool version pins are out of sync. Run 'python -m scripts.sync_tool_versions --apply' or re-run with --fix.${NC}" >&2
        python -m scripts.sync_tool_versions --check
        exit 1
    fi
fi

# Guarantee the Python scripts directory (where flake8 entry point lives) is on PATH.
if ! command -v flake8 >/dev/null 2>&1; then
    FLK_BIN=$(python - <<'PY'
import sysconfig
print(sysconfig.get_path('scripts') or '')
PY
)
    if [[ -n "$FLK_BIN" ]]; then
        export PATH="${FLK_BIN}:${PATH}"
    fi
fi

# Determine files to check
if [[ "$CHANGED_ONLY" == true ]]; then
    # Only check files changed in the last commit or working directory
    if git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
        PYTHON_FILES=$(git diff --name-only HEAD~1 2>/dev/null | grep -E '\.(py)$' 2>/dev/null | grep -v -E '^(archive/|\.extraction/)' 2>/dev/null || echo "")
    else
        # Shallow / single-commit clone fallback: skip HEAD~1 diff for speed
        PYTHON_FILES=""
    fi

    UNSTAGED_FILES=$(git diff --name-only 2>/dev/null | grep -E '\.(py)$' 2>/dev/null | grep -v -E '^(archive/|\.extraction/)' 2>/dev/null || echo "")
    ALL_FILES=$(echo -e "$PYTHON_FILES\n$UNSTAGED_FILES" | sort -u | grep -v '^$' 2>/dev/null || echo "")

    if [[ -z "$ALL_FILES" ]]; then
        echo -e "${GREEN}No Python files changed (excluding old folders) - nothing to check${NC}"
        exit 0
    fi

    echo -e "${BLUE}Checking only changed files (excluding old folders):${NC}"
    echo "$ALL_FILES" | sed 's/^/  /'
    echo ""
else
    ALL_FILES="scripts/ .github/"
fi

# Function to run quick checks
quick_check() {
    local name="$1"
    local command="$2"
    local fix_command="$3"
    local output_file
    output_file=$(mktemp -t "devcheck_${name// /_}.XXXX")
    local fix_file
    fix_file=$(mktemp -t "devcheck_${name// /_}_fix.XXXX")
    local recheck_file
    recheck_file=$(mktemp -t "devcheck_${name// /_}_re.XXXX")

    if [[ "$VERBOSE_MODE" == true ]]; then
        echo -e "${BLUE}Running: $command${NC}"
    fi

    if timeout "$CHECK_TIMEOUT" bash -c "$command" > "$output_file" 2>&1; then
        echo -e "${GREEN}✓ $name${NC}"
        rm -f "$output_file" "$fix_file" "$recheck_file"
        return 0
    else
        local exit_code=$?
        local timed_out=false
        if [[ $exit_code -eq 124 ]]; then
            timed_out=true
            echo -e "${RED}✗ $name (timed out after ${CHECK_TIMEOUT}s)${NC}"
            if [[ "$VERBOSE_MODE" == false ]]; then
                echo -e "${YELLOW}  Re-run with --verbose or increase DEV_CHECK_TIMEOUT to see details.${NC}"
            fi
        else
            echo -e "${RED}✗ $name${NC}"
        fi

        if [[ "$FIX_MODE" == true && -n "$fix_command" && $timed_out == false ]]; then
            echo -e "${YELLOW}  Fixing...${NC}"
            if timeout "$CHECK_TIMEOUT" bash -c "$fix_command" > "$fix_file" 2>&1; then
                # Re-check
                if timeout "$CHECK_TIMEOUT" bash -c "$command" > "$recheck_file" 2>&1; then
                    echo -e "${GREEN}✓ $name (fixed)${NC}"
                    rm -f "$output_file" "$fix_file" "$recheck_file"
                    return 0
                fi
            fi
            echo -e "${RED}✗ $name (fix failed)${NC}"
        fi

        if [[ "$VERBOSE_MODE" == true ]]; then
            echo -e "${YELLOW}Output:${NC}"
            if [[ -f "$output_file" ]]; then
                head -10 "$output_file" | sed 's/^/  /'
            fi
            if [[ -f "$fix_file" ]]; then
                echo -e "${YELLOW}Fix output:${NC}"
                head -10 "$fix_file" | sed 's/^/  /'
            fi
            if [[ -f "$recheck_file" ]]; then
                head -10 "$recheck_file" | sed 's/^/  /'
            fi
        fi
        rm -f "$output_file" "$fix_file" "$recheck_file"
        return 1
    fi
}

# Quick syntax check first (fastest)
echo -e "${BLUE}1. Syntax check...${NC}"
if [[ "$CHANGED_ONLY" == true && -n "$ALL_FILES" ]]; then
    SYNTAX_OK=true
    for file in $ALL_FILES; do
        if [[ -f "$file" ]]; then
            if ! python -m py_compile "$file" 2>/dev/null; then
                echo -e "${RED}✗ Syntax error in $file${NC}"
                SYNTAX_OK=false
            fi
        fi
    done
    if [[ "$SYNTAX_OK" == true ]]; then
        echo -e "${GREEN}✓ Syntax check${NC}"
    fi
else
    # TODO Phase 4: Replace with workflow validation (actionlint/yamllint)
    # quick_check "Syntax check" "python -m compileall src/ -q" ""
    echo -e "${YELLOW}⚠ Full syntax check deferred to Phase 4 (workflow validation)${NC}"
fi

# TODO Phase 4: Add workflow YAML validation
# TODO Phase 5: Add Node.js validation for keepalive scripts
# quick_check "Import test" "python -c 'import src.trend_analysis' 2>/dev/null" ""
echo -e "${BLUE}2. Workflow validation...${NC}"
echo -e "${YELLOW}⚠ Workflow validation deferred to Phase 4${NC}"

# Formatting check (very fast)
echo -e "${BLUE}3. Formatting...${NC}"
if [[ "$CHANGED_ONLY" == true && -n "$ALL_FILES" ]]; then
    FMT_CMD="echo '$ALL_FILES' | xargs black --check"
    FIX_CMD="echo '$ALL_FILES' | xargs black"
else
    FMT_CMD="black --check ${BLACK_TARGETS}"
    FIX_CMD="black ${BLACK_TARGETS}"
fi
quick_check "Black formatting" "$FMT_CMD" "$FIX_CMD"

# Basic linting (only critical issues)
echo -e "${BLUE}4. Critical linting...${NC}"
if [[ "$CHANGED_ONLY" == true && -n "$ALL_FILES" ]]; then
    # Only check for critical errors (E9**, F***)
    LINT_CMD="echo '$ALL_FILES' | xargs flake8 --select=E9,F --statistics"
else
    LINT_CMD="flake8 scripts/ --select=E9,F --statistics"
fi
quick_check "Critical lint errors" "$LINT_CMD" ""

# TODO Phase 4: Replace with actionlint or workflow-specific type validation
echo -e "${BLUE}5. Type check...${NC}"
echo -e "${YELLOW}⚠ Type checking deferred to Phase 4 (workflow validation)${NC}"
# if [[ "$CHANGED_ONLY" == true && -n "$ALL_FILES" ]]; then
#     TYPE_CMD="printf '%s\n' '$ALL_FILES' | head -3 | xargs -r mypy --follow-imports=silent --ignore-missing-imports"
# else
#     TYPE_CMD="mypy src/ --follow-imports=silent --ignore-missing-imports"
# fi
# quick_check "Basic type check" "$TYPE_CMD" "mypy --install-types --non-interactive"

# TODO Phase 5: Update test path when keepalive system extracted
echo -e "${BLUE}6. Keepalive harness tests...${NC}"
if command -v node >/dev/null 2>&1; then
    # TODO Phase 5: Update path to match extracted keepalive structure
    # quick_check "Keepalive workflow harness" "pytest tests/workflows/test_keepalive_workflow.py" ""
    echo -e "${YELLOW}⚠ Keepalive tests deferred to Phase 5${NC}"
else
    echo -e "${YELLOW}⚠ Node.js not available; skipping keepalive harness tests${NC}"
fi

echo ""
echo -e "${CYAN}=== Quick Check Complete ===${NC}"
echo -e "${BLUE}For comprehensive validation, run: ./scripts/check_branch.sh${NC}"
echo -e "${BLUE}For auto-fixes, run with: --fix${NC}"
echo -e "${BLUE}For changed files only: --changed${NC}"
