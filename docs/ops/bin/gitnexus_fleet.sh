#!/usr/bin/env bash
# Local GitNexus fleet helper for the stranske Code workspace.
#
# GitNexus is an optional local code-intelligence layer. GitHub remains the
# source of truth; .gitnexus/ indexes are derived local cache and are ignored.

set -euo pipefail

GITNEXUS_VERSION="${GITNEXUS_VERSION:-1.6.3}"
GROUP_NAME="${GITNEXUS_GROUP_NAME:-stranske-code}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOWS_ROOT="${WORKFLOWS_ROOT:-$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)}"
CODE_ROOT="${CODE_ROOT:-$(cd "${WORKFLOWS_ROOT}/.." && pwd)}"
GITNEXUS_BIN="${GITNEXUS_BIN:-gitnexus}"

# Canonical repos only. Workflows-steward is a temporary automation worktree
# and must not be registered in GitNexus.
FLEET_REPOS=(
  "Workflows"
  "Template"
  "Manager-Database"
  "Travel-Plan-Permission"
  "trip-planner"
  "Inv-Man-Intake"
  "Pension-Data"
  "Counter_Risk"
  "Trend_Model_Project"
  "Portable-Alpha-Extension-Model"
  "Collab-Admin"
)

repo_path() {
  printf '%s/%s\n' "${CODE_ROOT}" "$1"
}

run_gitnexus() {
  # shellcheck disable=SC2086
  ${GITNEXUS_BIN} "$@"
}

usage() {
  cat <<USAGE
Usage: docs/ops/bin/gitnexus_fleet.sh <command> [repo-name]

Commands:
  list                 Show canonical repos in the GitNexus fleet.
  ensure-ignores [repo|all]
                       Ensure local GitNexus cache patterns are in .gitignore.
  index [repo|all]     Run gitnexus analyze with local-cache defaults.
  status [repo|all]    Run gitnexus status for indexed repos.
  group-create         Create the ${GROUP_NAME} GitNexus group.
  group-add            Add canonical repos to the ${GROUP_NAME} group.
  group-sync           Run GitNexus group sync for ${GROUP_NAME}.
  group-status         Show GitNexus group staleness for ${GROUP_NAME}.
  install              Install the pinned GitNexus CLI globally with npm.
  check-version        Verify the installed GitNexus CLI matches the pin.
  mcp-config           Print the pinned Codex MCP config snippet.
  version              Print the pinned GitNexus version.

Environment:
  CODE_ROOT            Code workspace root. Default: parent of Workflows.
  GITNEXUS_VERSION     GitNexus npm version. Default: ${GITNEXUS_VERSION}.
  GITNEXUS_BIN         Command prefix. Default: gitnexus.
  GITNEXUS_GROUP_NAME  Group name. Default: ${GROUP_NAME}.

Notes:
  - This script intentionally ignores Workflows-steward.
  - Initial indexing leaves embeddings off and skips AGENTS/CLAUDE rewrites.
  - Use --embeddings manually only after baseline indexing proves useful.
USAGE
}

require_repo() {
  local repo="$1"
  local path
  path="$(repo_path "${repo}")"
  if [[ ! -d "${path}" ]]; then
    echo "Missing repo path: ${path}" >&2
    return 1
  fi
}

ensure_repo_ignores() {
  local repo="$1"
  local ignore_file pattern
  require_repo "${repo}"
  ignore_file="$(repo_path "${repo}")/.gitignore"
  touch "${ignore_file}"
  for pattern in ".gitnexus/" ".claude/skills/gitnexus/"; do
    if ! grep -Fxq "${pattern}" "${ignore_file}"; then
      printf '%s\n' "${pattern}" >> "${ignore_file}"
      echo "Added ${pattern} to ${repo}/.gitignore"
    fi
  done
}

index_repo() {
  local repo="$1"
  require_repo "${repo}"
  ensure_repo_ignores "${repo}"
  echo "Indexing ${repo}"
  run_gitnexus analyze "$(repo_path "${repo}")" --skip-agents-md
}

status_repo() {
  local repo="$1"
  require_repo "${repo}"
  echo "Status ${repo}"
  (cd "$(repo_path "${repo}")" && run_gitnexus status)
}

case "${1:-}" in
  list)
    printf '%s\n' "${FLEET_REPOS[@]}"
    ;;
  ensure-ignores)
    target="${2:-all}"
    if [[ "${target}" == "all" ]]; then
      for repo in "${FLEET_REPOS[@]}"; do
        ensure_repo_ignores "${repo}"
      done
    else
      ensure_repo_ignores "${target}"
    fi
    ;;
  index)
    target="${2:-all}"
    if [[ "${target}" == "all" ]]; then
      for repo in "${FLEET_REPOS[@]}"; do
        index_repo "${repo}"
      done
    else
      index_repo "${target}"
    fi
    ;;
  status)
    target="${2:-all}"
    if [[ "${target}" == "all" ]]; then
      for repo in "${FLEET_REPOS[@]}"; do
        status_repo "${repo}" || true
      done
    else
      status_repo "${target}"
    fi
    ;;
  group-create)
    run_gitnexus group create "${GROUP_NAME}"
    ;;
  group-add)
    for repo in "${FLEET_REPOS[@]}"; do
      run_gitnexus group add "${GROUP_NAME}" "${repo}" "${repo}" || true
    done
    ;;
  group-sync)
    run_gitnexus group sync "${GROUP_NAME}"
    ;;
  group-status)
    run_gitnexus group status "${GROUP_NAME}"
    ;;
  install)
    npm install -g "gitnexus@${GITNEXUS_VERSION}"
    ;;
  check-version)
    installed="$(${GITNEXUS_BIN} --version)"
    if [[ "${installed}" != "${GITNEXUS_VERSION}" ]]; then
      echo "GitNexus version mismatch: installed ${installed}, expected ${GITNEXUS_VERSION}" >&2
      exit 1
    fi
    echo "GitNexus ${installed}"
    ;;
  mcp-config)
    cat <<CONFIG
[mcp_servers.gitnexus]
command = "gitnexus"
args = ["mcp"]
CONFIG
    ;;
  version)
    printf '%s\n' "${GITNEXUS_VERSION}"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $1" >&2
    usage >&2
    exit 2
    ;;
esac
