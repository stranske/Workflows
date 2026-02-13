#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/sync_pat_secrets.sh --repo owner/repo [--repo owner/repo ...] [--dry-run] [--verify]
  scripts/sync_pat_secrets.sh --repos owner/repo,owner/repo [--dry-run] [--verify]
  scripts/sync_pat_secrets.sh --from-file repos.txt [--dry-run] [--verify]

Required environment variables:
  SERVICE_BOT_PAT
  ACTIONS_BOT_PAT
  OWNER_PR_PAT
  AGENTS_AUTOMATION_PAT

Optional behavior:
  --verify   Validates each token with GitHub API before updating secrets
  --dry-run  Prints planned updates without writing secrets

Examples:
  export SERVICE_BOT_PAT='...'
  export ACTIONS_BOT_PAT='...'
  export OWNER_PR_PAT='...'
  export AGENTS_AUTOMATION_PAT='...'
  scripts/sync_pat_secrets.sh --repos stranske/Counter_Risk,stranske/Template --verify

  cat > /tmp/repos.txt <<'LIST'
  stranske/Counter_Risk
  stranske/Template
  LIST
  scripts/sync_pat_secrets.sh --from-file /tmp/repos.txt
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command not found: $cmd" >&2
    exit 1
  fi
}

trim() {
  local value="$1"
  value="${value#${value%%[![:space:]]*}}"
  value="${value%${value##*[![:space:]]}}"
  printf '%s' "$value"
}

assert_required_env() {
  local missing=()
  for name in SERVICE_BOT_PAT ACTIONS_BOT_PAT OWNER_PR_PAT AGENTS_AUTOMATION_PAT; do
    if [[ -z "${!name:-}" ]]; then
      missing+=("$name")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    echo "Error: missing required environment variables: ${missing[*]}" >&2
    exit 1
  fi
}

verify_token() {
  local token_name="$1"
  local token_value="$2"
  if GH_TOKEN="$token_value" gh api user --jq .login >/dev/null 2>&1; then
    echo "  ✓ ${token_name} validated"
  else
    echo "  ✗ ${token_name} failed validation" >&2
    return 1
  fi
}

set_repo_secret() {
  local repo="$1"
  local secret_name="$2"
  local secret_value="$3"
  local dry_run="$4"

  if [[ "$dry_run" == "true" ]]; then
    echo "  - would set ${secret_name}"
    return 0
  fi

  printf '%s' "$secret_value" | gh secret set "$secret_name" --repo "$repo" >/dev/null
  echo "  - set ${secret_name}"
}

main() {
  require_cmd gh

  local dry_run="false"
  local verify="false"
  local from_file=""
  local repos_csv=""
  local repos=()

  while (( "$#" )); do
    case "$1" in
      --repo)
        [[ $# -ge 2 ]] || { echo "Error: --repo requires a value" >&2; exit 1; }
        repos+=("$2")
        shift 2
        ;;
      --repos)
        [[ $# -ge 2 ]] || { echo "Error: --repos requires a value" >&2; exit 1; }
        repos_csv="$2"
        shift 2
        ;;
      --from-file)
        [[ $# -ge 2 ]] || { echo "Error: --from-file requires a path" >&2; exit 1; }
        from_file="$2"
        shift 2
        ;;
      --dry-run)
        dry_run="true"
        shift
        ;;
      --verify)
        verify="true"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Error: unknown argument: $1" >&2
        usage
        exit 1
        ;;
    esac
  done

  if [[ -n "$repos_csv" ]]; then
    IFS=',' read -r -a split_repos <<< "$repos_csv"
    for item in "${split_repos[@]}"; do
      item="$(trim "$item")"
      [[ -n "$item" ]] && repos+=("$item")
    done
  fi

  if [[ -n "$from_file" ]]; then
    [[ -f "$from_file" ]] || { echo "Error: file not found: $from_file" >&2; exit 1; }
    while IFS= read -r line; do
      line="$(trim "$line")"
      [[ -z "$line" || "$line" == \#* ]] && continue
      repos+=("$line")
    done < "$from_file"
  fi

  if (( ${#repos[@]} == 0 )); then
    echo "Error: no repositories provided" >&2
    usage
    exit 1
  fi

  assert_required_env

  if [[ "$verify" == "true" ]]; then
    echo "Validating token values before sync..."
    verify_token "SERVICE_BOT_PAT" "$SERVICE_BOT_PAT"
    verify_token "ACTIONS_BOT_PAT" "$ACTIONS_BOT_PAT"
    verify_token "OWNER_PR_PAT" "$OWNER_PR_PAT"
    verify_token "AGENTS_AUTOMATION_PAT" "$AGENTS_AUTOMATION_PAT"
  fi

  echo "Syncing PAT secrets to ${#repos[@]} repos..."
  for repo in "${repos[@]}"; do
    echo "Repo: $repo"
    set_repo_secret "$repo" "SERVICE_BOT_PAT" "$SERVICE_BOT_PAT" "$dry_run"
    set_repo_secret "$repo" "ACTIONS_BOT_PAT" "$ACTIONS_BOT_PAT" "$dry_run"
    set_repo_secret "$repo" "OWNER_PR_PAT" "$OWNER_PR_PAT" "$dry_run"
    set_repo_secret "$repo" "AGENTS_AUTOMATION_PAT" "$AGENTS_AUTOMATION_PAT" "$dry_run"
  done

  echo "Done."
}

main "$@"
