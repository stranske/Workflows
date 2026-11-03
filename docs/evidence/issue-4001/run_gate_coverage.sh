#!/usr/bin/env bash
# Gate-equivalent whole-suite coverage (pr-00-gate.yml + docs/ci-workflow.md).
set -euo pipefail
ROOT="${1:?repo root}"
OUT="${2:?output coverage.json path}"
cd "$ROOT"
rm -f .coverage .coverage.* coverage.json
export PYTHONPATH="${ROOT}"
/opt/anaconda3/bin/python3 -m pytest \
  -m 'not quarantine and not slow' \
  --cov \
  --cov-config=pyproject.toml \
  --cov-report="json:${OUT}" \
  -n auto \
  --dist=loadgroup \
  -q \
  --tb=no
