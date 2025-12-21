#!/usr/bin/env bash
set -euo pipefail

FLOATING_TAG=${1:?"Floating tag name (e.g., v1) is required"}
MAJOR_PREFIX=${2:?"Major prefix (e.g., v1.) is required"}
TARGET_COMMIT=${3:-}
ALLOW_MISSING_RELEASES=${ALLOW_MISSING_RELEASES:-0}
RELEASE_TAG=""

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "This script must be run inside a git repository" >&2
  exit 1
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

if git remote get-url origin >/dev/null 2>&1; then
  git fetch --tags origin
else
  echo "Remote origin not configured; skipping fetch" >&2
fi

if [[ -z "${TARGET_COMMIT}" ]]; then
  RELEASE_TAG=$(git tag -l "${MAJOR_PREFIX}*" --sort=-v:refname | head -n 1)
  if [[ -z "${RELEASE_TAG}" ]]; then
    if [[ "${ALLOW_MISSING_RELEASES}" != "0" ]]; then
      echo "No tags found matching ${MAJOR_PREFIX}*; ALLOW_MISSING_RELEASES enabled, skipping update"
      exit 0
    fi
    echo "No tags found matching ${MAJOR_PREFIX}*" >&2
    exit 1
  fi
  TARGET_COMMIT=$(git rev-list -n 1 "${RELEASE_TAG}")
else
  # Validate the commit exists locally
  if ! git cat-file -e "${TARGET_COMMIT}^{commit}" 2>/dev/null; then
    echo "Commit ${TARGET_COMMIT} does not exist" >&2
    exit 1
  fi

  RELEASE_TAG=$(git tag --list --points-at "${TARGET_COMMIT}" "${MAJOR_PREFIX}*")
  RELEASE_TAG=$(echo "${RELEASE_TAG}" | sort -rV | head -n 1)
  if [[ -z "${RELEASE_TAG}" ]]; then
    if [[ "${ALLOW_MISSING_RELEASES}" != "0" ]]; then
      echo "Commit ${TARGET_COMMIT} is not tagged with ${MAJOR_PREFIX}* release; ALLOW_MISSING_RELEASES enabled, skipping update"
      exit 0
    fi
    echo "Commit ${TARGET_COMMIT} is not tagged with ${MAJOR_PREFIX}* release" >&2
    exit 1
  fi
fi

echo "Updating ${FLOATING_TAG} to point at ${RELEASE_TAG} (${TARGET_COMMIT})" && git tag -f "${FLOATING_TAG}" "${TARGET_COMMIT}"

if [[ "${DRY_RUN:-0}" != "0" ]]; then
  echo "DRY_RUN enabled; skipping push of ${FLOATING_TAG}"
  exit 0
fi

git push origin "refs/tags/${FLOATING_TAG}" --force
