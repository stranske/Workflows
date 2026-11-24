#!/bin/bash
set -euo pipefail

format_all=false
if [[ ${1:-} == --all ]]; then
    format_all=true
    shift
fi
if [[ $# -gt 1 ]]; then
    echo "Usage: bash $0 [--all] [integration-checkout]" >&2
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

if "$format_all"; then
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
