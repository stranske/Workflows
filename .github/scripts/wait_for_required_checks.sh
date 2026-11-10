#!/usr/bin/env bash
# Wait until a PR's required checks have REPORTED, then until they pass.
#
# usage: wait_for_required_checks.sh <pr-number> [appear-seconds] [watch-seconds] [interval-seconds]
# exit 0: required checks reported and passed
# exit 1: a required check failed, or none reported / none finished in time (the caller leaves the PR alone)
#
# Why (stranske/Workflows#4133, 2026-11-10): `gh pr checks --required --watch` exits at once with "no required
# checks reported" when Gate has not created its `summary` check-run yet. That took ~2 min after the weekly
# corpus push until mid-October and 22 min on 2026-11-09, so the harvest's auto-merge never armed from 10-19 on.
# "Not reported yet" is now waited for instead of read as a failure.
set -uo pipefail
pr="$1"; appear="${2:-2400}"; watch="${3:-1200}"; interval="${4:-30}"
deadline=$((SECONDS + appear))
while :; do
  out="$(gh pr checks "$pr" --required 2>&1)"
  case "$out" in
    *"no required checks reported"*|"") ;;
    *) break ;;
  esac
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "no required check reported within ${appear}s"
    exit 1
  fi
  sleep "$interval"
done
if ! result="$(timeout "$watch" gh pr checks "$pr" --required --watch --interval "$interval" 2>&1)"; then
  printf '%s\n' "$result"
  exit 1
fi
if [ -z "$result" ]; then
  echo "required checks returned no rows"
  exit 1
fi
printf '%s\n' "$result"
exit 0
