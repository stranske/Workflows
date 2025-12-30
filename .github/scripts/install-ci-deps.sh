#!/usr/bin/env bash
# Shared dependency installation script for CI workflows
# This consolidates duplicate installation logic from reusable-10-ci-python.yml
#
# Usage:
#   source .github/scripts/install-ci-deps.sh
#   install_ci_deps [options]
#
# Environment variables:
#   INPUT_LINT         - Enable lint tools (true/false)
#   INPUT_FORMAT_CHECK - Enable format tools (true/false)
#   INPUT_TYPECHECK    - Enable typecheck tools (true/false)
#   INPUT_RUN_MYPY     - Enable mypy specifically (true/false)
#   INPUT_COVERAGE     - Enable coverage tools (true/false)
#   INPUT_PYTHON_VERSION - Python version for cache key
#   PRIVATE_PYPI_TOKEN - Optional private PyPI token
#   GITHUB_WORKSPACE   - GitHub workspace path
#   GITHUB_STEP_SUMMARY - Path to step summary file

set -euo pipefail

# Convert string to boolean
to_bool() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|y|on) echo "true" ;;
    *) echo "false" ;;
  esac
}

# Resolve package spec with version
resolve_spec() {
  local package=$1
  local version=${2:-}
  local default_version=${3:-}
  if [ -n "$version" ]; then
    echo "${package}==${version}"
  elif [ -n "$default_version" ]; then
    echo "${package}==${default_version}"
  else
    echo "$package"
  fi
}

# Main installation function
install_ci_deps() {
  local start_ts
  start_ts=$(date +%s)

  # Parse environment variables
  local lint_enabled
  local format_enabled
  local typecheck_enabled
  local run_mypy_enabled
  local coverage_enabled
  local mypy_enabled

  lint_enabled=$(to_bool "${INPUT_LINT:-false}")
  format_enabled=$(to_bool "${INPUT_FORMAT_CHECK:-false}")
  typecheck_enabled=$(to_bool "${INPUT_TYPECHECK:-false}")
  run_mypy_enabled=$(to_bool "${INPUT_RUN_MYPY:-false}")
  coverage_enabled=$(to_bool "${INPUT_COVERAGE:-false}")

  mypy_enabled="false"
  if [ "$typecheck_enabled" = "true" ] && [ "$run_mypy_enabled" = "true" ]; then
    mypy_enabled="true"
  fi

  # Initialize arrays
  local specs=()
  local tools_installed=()
  local tools_skipped=()

  add_tool() {
    specs+=("$1")
    tools_installed+=("$2")
  }

  skip_tool() {
    tools_skipped+=("$1")
  }

  # Configure private PyPI if token provided
  if [ -n "${PRIVATE_PYPI_TOKEN:-}" ]; then
    export PIP_INDEX_URL="https://__token__:${PRIVATE_PYPI_TOKEN}@pypi.org/simple"
  fi

  # Add project dependencies if files exist
  if [ -f requirements.lock ]; then
    specs+=('-r' 'requirements.lock')
  fi

  if [ -f pyproject.toml ]; then
    # Check if extras exist before adding them
    if grep -q '\[project.optional-dependencies\]' pyproject.toml 2>/dev/null; then
      if grep -q '^\s*dev\s*=' pyproject.toml 2>/dev/null; then
        specs+=('-e' '.[dev]')
      else
        specs+=('-e' '.')
      fi
    else
      specs+=('-e' '.')
    fi
  elif [ -f setup.cfg ] || [ -f setup.py ]; then
    specs+=('-e' '.')
  fi

  # Tool specs with defaults
  local black_spec="black"
  local docformatter_spec="docformatter"
  local isort_spec="isort"
  local ruff_spec="ruff"
  local mypy_spec="mypy"
  local pytest_spec="pytest"
  local pytest_cov_spec="pytest-cov"
  local coverage_spec="coverage"
  local pytest_xdist_spec="pytest-xdist"
  local base_test_specs=(
    "hypothesis"
    "pandas"
    "numpy"
    "pydantic"
    "pydantic-core"
    "requests"
    "jsonschema"
    "PyYAML"
    "tomlkit"
  )

  # Load versions from autofix-versions.env if available
  local autofix_env="${GITHUB_WORKSPACE:-.}/.github/workflows/autofix-versions.env"
  if [ -f "$autofix_env" ]; then
    # shellcheck source=/dev/null
    source "$autofix_env"
    black_spec=$(resolve_spec "black" "${BLACK_VERSION:-}" "")
    docformatter_spec=$(resolve_spec "docformatter" "${DOCFORMATTER_VERSION:-}" "")
    isort_spec=$(resolve_spec "isort" "${ISORT_VERSION:-}" "")
    ruff_spec=$(resolve_spec "ruff" "${RUFF_VERSION:-}" "")
    mypy_spec=$(resolve_spec "mypy" "${MYPY_VERSION:-}" "")
    pytest_spec=$(resolve_spec "pytest" "${PYTEST_VERSION:-}" "")
    pytest_cov_spec=$(resolve_spec "pytest-cov" "${PYTEST_COV_VERSION:-}" "")
    coverage_spec=$(resolve_spec "coverage" "${COVERAGE_VERSION:-}" "7.2.7")
    pytest_xdist_spec=$(resolve_spec "pytest-xdist" "${PYTEST_XDIST_VERSION:-}" "3.6.1")
    base_test_specs=(
      "$(resolve_spec "hypothesis" "${HYPOTHESIS_VERSION:-}" "6.115.1")"
      "$(resolve_spec "pandas" "${PANDAS_VERSION:-}" "2.3.0")"
      "$(resolve_spec "numpy" "${NUMPY_VERSION:-}" "2.1.0")"
      "$(resolve_spec "pydantic" "${PYDANTIC_VERSION:-}" "2.10.3")"
      "$(resolve_spec "pydantic-core" "${PYDANTIC_CORE_VERSION:-}" "2.27.1")"
      "$(resolve_spec "requests" "${REQUESTS_VERSION:-}" "2.31.0")"
      "$(resolve_spec "jsonschema" "${JSONSCHEMA_VERSION:-}" "4.0.0")"
      "$(resolve_spec "PyYAML" "${PYYAML_VERSION:-}" "6.0.2")"
      "$(resolve_spec "tomlkit" "${TOMLKIT_VERSION:-}" "")"
    )
  else
    echo "Warning: autofix-versions.env not found, installing latest tool versions" >&2
  fi

  # Add format tools if enabled
  if [ "$format_enabled" = "true" ]; then
    add_tool "$black_spec" "black"
    add_tool "$docformatter_spec" "docformatter"
    add_tool "$isort_spec" "isort"
  else
    skip_tool "black (format_check disabled)"
    skip_tool "docformatter (format_check disabled)"
    skip_tool "isort (format_check disabled)"
  fi

  # Add lint tools if enabled
  if [ "$lint_enabled" = "true" ]; then
    add_tool "$ruff_spec" "ruff"
  else
    skip_tool "ruff (lint disabled)"
  fi

  # Add typecheck tools if enabled
  if [ "$mypy_enabled" = "true" ]; then
    add_tool "$mypy_spec" "mypy"
  else
    skip_tool "mypy (typecheck disabled)"
  fi

  # Always add pytest and base test dependencies
  add_tool "$pytest_spec" "pytest"
  add_tool "$pytest_xdist_spec" "pytest-xdist"
  for spec in "${base_test_specs[@]}"; do
    add_tool "$spec" "$spec"
  done

  # Add coverage tools if enabled
  if [ "$coverage_enabled" = "true" ]; then
    add_tool "$pytest_cov_spec" "pytest-cov"
    add_tool "$coverage_spec" "coverage"
  else
    skip_tool "pytest-cov (coverage disabled)"
    skip_tool "coverage (coverage disabled)"
  fi

  # Install dependencies
  if [ ${#specs[@]} -eq 0 ]; then
    echo "No install targets found; skipping dependency installation."
  else
    uv pip install --system "${specs[@]}"
  fi

  # Generate summary
  local end_ts
  end_ts=$(date +%s)
  local duration=$((end_ts - start_ts))

  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    local installed_label="none"
    local skipped_label="none"
    if [ ${#tools_installed[@]} -gt 0 ]; then
      installed_label=$(printf '%s, ' "${tools_installed[@]}")
      installed_label=${installed_label%, }
    fi
    if [ ${#tools_skipped[@]} -gt 0 ]; then
      skipped_label=$(printf '%s, ' "${tools_skipped[@]}")
      skipped_label=${skipped_label%, }
    fi
    {
      printf '## Dependency installation timing\n'
      printf -- '- Duration: %ss\n' "$duration"
      printf -- '- Tools installed: %s\n' "$installed_label"
      printf -- '- Tools skipped (disabled): %s\n' "$skipped_label"
      if [ ${#tools_skipped[@]} -gt 0 ]; then
        printf -- '- Note: skipping %d tool(s) avoids extra setup time when disabled.\n' "${#tools_skipped[@]}"
      fi
    } >>"${GITHUB_STEP_SUMMARY}"
  fi

  echo "Dependency installation complete in ${duration}s"
}

# Run if executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  install_ci_deps "$@"
fi
