#!/bin/bash
# Quick validation of extracted file
# Usage: ./scripts/validate-extraction.sh <file>

set -e

FILE=$1

if [ -z "$FILE" ]; then
    echo "Usage: $0 <file>"
    echo "Example: $0 .github/workflows/reusable-10-ci-python.yml"
    exit 1
fi

if [ ! -f "$FILE" ]; then
    echo "❌ File not found: $FILE"
    exit 1
fi

echo "Validating $FILE..."
echo

ERRORS=0
WARNINGS=0

# Check for project-specific terms
echo "🔍 Checking for project-specific terms..."

if grep -qi "stranske" "$FILE"; then
    echo "❌ Contains 'stranske'"
    grep -ni "stranske" "$FILE" | head -3
    ERRORS=$((ERRORS + 1))
fi

if grep -qi "trend[-_]model" "$FILE"; then
    echo "❌ Contains 'trend_model' or 'trend-model'"
    grep -ni "trend[-_]model" "$FILE" | head -3
    ERRORS=$((ERRORS + 1))
fi

if grep -q "phase-2-dev" "$FILE"; then
    echo "❌ Contains 'phase-2-dev' branch reference"
    grep -n "phase-2-dev" "$FILE"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "Issue #[0-9]" "$FILE"; then
    echo "⚠️  Contains issue references (may be OK in docs/comments)"
    grep -n "Issue #[0-9]" "$FILE" | head -3
    WARNINGS=$((WARNINGS + 1))
fi

if grep -q "PR #[0-9]" "$FILE"; then
    echo "⚠️  Contains PR references (may be OK in docs/comments)"
    grep -n "PR #[0-9]" "$FILE" | head -3
    WARNINGS=$((WARNINGS + 1))
fi

# Check for hardcoded Python versions (may be intentional defaults)
if grep -q '"3\.11"' "$FILE" || grep -q '"3\.12"' "$FILE"; then
    echo "⚠️  Contains hardcoded Python versions (check if should be parameterized)"
    grep -n '"3\.1[12]"' "$FILE" | head -3
    WARNINGS=$((WARNINGS + 1))
fi

# For workflow files, check for parameterization
if [[ "$FILE" == *.yml ]] || [[ "$FILE" == *.yaml ]]; then
    echo
    echo "🔍 Checking workflow-specific requirements..."
    
    if ! grep -q '\${{ inputs\.' "$FILE" && ! grep -q 'workflow_dispatch' "$FILE"; then
        echo "⚠️  Workflow doesn't use inputs (may need parameterization)"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    # Check for hardcoded repository references
    if grep -q "uses:.*Trend_Model_Project" "$FILE"; then
        echo "❌ Contains hardcoded Trend_Model_Project repository reference"
        grep -n "uses:.*Trend_Model_Project" "$FILE"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Validate YAML syntax
    if command -v yq &> /dev/null; then
        if ! yq eval '.' "$FILE" > /dev/null 2>&1; then
            echo "❌ Invalid YAML syntax"
            ERRORS=$((ERRORS + 1))
        else
            echo "✅ Valid YAML syntax"
        fi
    else
        echo "ℹ️  yq not installed, skipping YAML syntax validation"
    fi
    
    # Check for actionlint if available
    if command -v actionlint &> /dev/null; then
        if ! actionlint "$FILE" > /dev/null 2>&1; then
            echo "⚠️  actionlint found issues (run 'actionlint $FILE' for details)"
            WARNINGS=$((WARNINGS + 1))
        else
            echo "✅ actionlint validation passed"
        fi
    else
        echo "ℹ️  actionlint not installed, skipping workflow linting"
    fi
fi

# For Python files, check for imports
if [[ "$FILE" == *.py ]]; then
    echo
    echo "🔍 Checking Python-specific requirements..."
    
    if grep -q "^import trend_model" "$FILE" || grep -q "^from trend_model" "$FILE"; then
        echo "❌ Contains direct import of trend_model package"
        grep -n "trend_model" "$FILE" | head -3
        ERRORS=$((ERRORS + 1))
    fi
    
    # Check for hardcoded paths
    if grep -q 'Path.*trend_model' "$FILE"; then
        echo "❌ Contains hardcoded trend_model path"
        grep -n 'Path.*trend_model' "$FILE"
        ERRORS=$((ERRORS + 1))
    fi
fi

# Summary
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "✅ Validation passed - no issues found"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo "⚠️  Validation passed with $WARNINGS warning(s)"
    echo "Review warnings and determine if they need fixing"
    exit 0
else
    echo "❌ Validation failed"
    echo "   Errors: $ERRORS"
    echo "   Warnings: $WARNINGS"
    echo
    echo "Please fix errors before proceeding"
    exit 1
fi
