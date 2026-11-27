#!/bin/bash
set -euo pipefail

format_mode=narrow
case ${1:-} in
    --all|--reviewed)
        format_mode=$1
        shift
        ;;
esac
if [[ $# -gt 1 ]]; then
    echo "Usage: bash $0 [--all|--reviewed] [integration-checkout]" >&2
    exit 1
fi

CDPATH='' cd -- "${1:-.}"
if ! git_prefix=$(git rev-parse --show-prefix 2>/dev/null) || [[ -n "$git_prefix" ||
    ! -f .github/workflows/notify-workflows.yml || -L .github/workflows/notify-workflows.yml ]]; then
    printf 'Use the Workflows-Integration-Tests checkout root. %s is not an integration checkout.\n' \
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

if [[ ! -f pyproject.toml || -L pyproject.toml ]]; then
    printf 'Expected a regular integration formatter configuration at pyproject.toml in %s.\n' \
        "$PWD" >&2
    exit 1
fi

if [[ "$format_mode" == --reviewed ]]; then
    for tool in black ruff python3; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            printf '%s is required. Install the Integration-Tests dev dependencies first.\n' \
                "$tool" >&2
            exit 1
        fi
    done
    echo "Running black on Python files (using pyproject.toml config)..."
    # Black will use line-length=100 from pyproject.toml
    black --extend-exclude '\.workflows-lib' .

    echo "Running ruff fixes..."
    diagnostics=$(mktemp)
    trap 'rm -f "$diagnostics"' EXIT
    ruff_status=0
    ruff check --fix --output-format json --exclude '.workflows-lib' . > "$diagnostics" || ruff_status=$?
    if [ "$ruff_status" -gt 1 ]; then
        echo "Ruff did not complete (exit $ruff_status)." >&2
        exit "$ruff_status"
    fi
    if [ "$ruff_status" -eq 1 ]; then
        python3 - "$diagnostics" <<'PY'
import json
import re
import sys
from pathlib import Path

try:
    diagnostics = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    diagnostics = None

# Exit 1 also covers syntax diagnostics. Accept only ordinary lint rules.
if not isinstance(diagnostics, list) or not diagnostics or any(
    not isinstance(item, dict)
    or not isinstance(code := item.get("code"), str)
    or not re.fullmatch(r"[A-Z]+[0-9]+", code)
    or code in {"E902", "E999"}
    for item in diagnostics
):
    sys.exit("Ruff reported incomplete formatting or unreadable diagnostics.")
codes = ", ".join(sorted({item["code"] for item in diagnostics}))
print(f"Warning: Ruff completed with remaining lint diagnostics: {codes}.")
PY
    fi

    echo 'Formatting complete. Review the changes before committing:'
    git --no-pager diff --stat
elif [[ "$format_mode" == --all ]]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo 'python3 is required for full-checkout formatting.' >&2
        exit 1
    fi
    for tool in black ruff; do
        if ! python3 -m "$tool" --version >/dev/null 2>&1; then
            printf '%s is required. Install the Integration-Tests dev dependencies first.\n' \
                "$tool" >&2
            exit 1
        fi
    done
    python3 -m black .
    python3 -m ruff check --fix .
    echo 'Formatting and linting complete. Review changes with git diff.'
else
    if ! command -v black >/dev/null 2>&1; then
        echo 'black is required. Install the Integration-Tests dev dependencies first.' >&2
        exit 1
    fi
    black "${format_targets[@]}"
    echo 'Formatting complete. Review the changes before committing:'
    git --no-pager diff --stat
fi
