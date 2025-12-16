#!/usr/bin/env bash

set -euo pipefail

path_label=${PATH_LABEL:-unknown}
dispatch_value=${DISPATCH:-}
trace_value=${TRACE:-}
pr_value_raw=${PR_NUMBER:-}
fallback_pr=${FALLBACK_PR:-}
activation_raw=${ACTIVATION_ID:-}
activation_fallback=${ACTIVATION_FALLBACK:-}
reason_value=${DISPATCH_REASON:-}
agent_value=${DISPATCH_AGENT:-}
head_raw=${HEAD_SHA:-}
active_raw=${ACTIVE_RUNS:-}
cap_raw=${RUN_CAP:-}

if [[ -z "${trace_value}" ]]; then
  trace_value='-'
fi

if [[ -z "${pr_value_raw}" || "${pr_value_raw}" == '0' || "${pr_value_raw}" == 'unknown' ]]; then
  pr_value_raw="${fallback_pr:-}"
fi

if [[ -z "${activation_raw}" || "${activation_raw}" == '0' || "${activation_raw}" == 'unknown' ]]; then
  activation_raw="${activation_fallback:-}"
fi

format_pr() {
  local raw="${1:-}"
  if [[ -n "${raw}" && "${raw}" != 'unknown' && "${raw}" != '0' ]]; then
    printf '#%s' "${raw}"
  else
    printf '#?'
  fi
}

normalise_path() {
  local raw=$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')
  case "${raw}" in
    gate|comment) printf '%s' "${raw}" ;;
    *) printf 'unknown' ;;
  esac
}

normalise_reason() {
  local raw=$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')
  case "${raw}" in
    ''|unspecified) printf 'gate-failed' ;;
    ok|success|keepalive-detected) printf 'ok' ;;
    missing-label|keepalive-label-missing|missing-keepalive-label) printf 'missing-label' ;;
    gate-pending|gate-not-concluded) printf 'gate-pending' ;;
    gate-not-success|gate-run-missing|gate-failed|gate-error|gate-missing|sync-required) printf 'gate-failed' ;;
    run-cap-reached|cap-reached) printf 'cap-reached' ;;
    no-linked-pr|missing-pr|missing-pr-number) printf 'no-linked-pr' ;;
    no-activation-found|missing-activation-comment|invalid-activation-comment|missing-pr-number|activation-comment-missing|no-human-comment) printf 'no-activation-found' ;;
    lock-held|duplicate-keepalive|lock-failed|lock-error) printf 'lock-held' ;;
    instruction-empty|no-instruction-segment|instruction-missing|instruction-parse-failed) printf 'instruction-empty' ;;
    no-human-activation|unauthorised-author|unauthorized-author|missing-sentinel|missing-round|invalid-round|missing-comment-id|missing-trace|pull-fetch-failed|fork-pr|missing-issue-reference|instruction-reaction-failed|missing-instruction-reaction|not-keepalive) printf 'no-human-activation' ;;
    *) printf 'gate-failed' ;;
  esac
}

pr_value=$(format_pr "${pr_value_raw}")

if [[ -z "${activation_raw}" ]]; then
  activation_value='none'
else
  activation_value=${activation_raw}
fi

if [[ -z "${agent_value}" ]]; then
  agent_value='?'
fi

head_value='unknown'
if [[ -n "${head_raw}" && "${head_raw}" != 'unknown' ]]; then
  head_value=$(printf '%.7s' "${head_raw}")
fi

active_value=${active_raw:-}
if [[ -z "${active_value}" || "${active_value}" == 'unknown' ]]; then
  active_value='0'
fi

cap_value=${cap_raw:-}
if [[ -z "${cap_value}" || "${cap_value}" == 'unknown' ]]; then
  cap_value='?'
fi

dispatch_normalised=$(printf '%s' "${dispatch_value}" | tr '[:upper:]' '[:lower:]')
if [[ "${dispatch_normalised}" == 'true' ]]; then
  ok_value='true'
else
  ok_value='false'
fi

reason_value=$(normalise_reason "${reason_value}")
if [[ "${ok_value}" == 'true' ]]; then
  reason_value='ok'
fi

path_value=$(normalise_path "${path_label}")

summary_line="DISPATCH: ok=${ok_value} path=${path_value} reason=${reason_value} pr=${pr_value} activation=${activation_value} agent=${agent_value} head=${head_value} cap=${cap_value} active=${active_value} trace=${trace_value}"

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  printf '%s\n' "${summary_line}" >>"${GITHUB_STEP_SUMMARY}"
fi

printf '%s\n' "${summary_line}"
