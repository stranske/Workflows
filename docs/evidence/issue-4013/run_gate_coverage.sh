#!/usr/bin/env bash
# Gate-equivalent coverage capture for issue #4013 (see pr-00-gate.yml python-ci inputs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
SHA="$1"
OUT="$2"
START_REF="$(git rev-parse HEAD)"
cleanup() {
  git checkout -q "$START_REF" 2>/dev/null || git checkout -q --detach "$START_REF"
}
trap cleanup EXIT
git checkout -q "$SHA"
rm -f coverage.json .coverage .coverage.*
/opt/anaconda3/bin/python3 -m pytest tests/ \
  -m "not quarantine and not slow" \
  -n auto --dist load \
  --cov --cov-config=pyproject.toml \
  --cov-branch \
  --cov-report=json:coverage.json \
  -q
cp coverage.json "$OUT"
/opt/anaconda3/bin/python3 docs/evidence/issue-4013/count_target_gaps.py "$OUT" | tee "${OUT%.json}.txt"
