# Evidence replay preflight

Recorded before this round's test edits on 2026-11-11 at checked-out head
`16be78c0eb19908fe7a383d8c457164286945e6e`. The local `origin/main` snapshot is
`8084366d968d5c4f68208536ca8bb3956ce99091`; GitHub's branch API independently
confirmed the same live main SHA during this round.
The original pre-test main baseline remains the API-confirmed
`e621d8f0ed8b83b9648b7fa8577b4f236bd57f1d` recorded in `preflight.md`.

`docs/AGENT_ISSUE_FORMAT.md` remains absent. Inspected the available
`docs/ci/ISSUE_FORMAT_GUIDE.md` and `docs/templates/AGENT_ISSUE_TEMPLATE.md`
instead. Neither is claimed to be the missing historical document. The first
task remains unchecked for that literal missing-document requirement.

Read #4423 through GitHub and confirmed the concrete recovered extractor path:
`docs/evidence/issue-4001/extract_target_coverage.py`. Its existing CLI only reads
uncompressed JSON. This round adds compressed report input and an optional XML
cross-check so the retained complete files can be verified directly. The original
JSON-only invocation remains supported.

Rechecked Gate `python-ci` in `.github/workflows/pr-00-gate.yml` and job `tests`,
step `pytest` in `.github/workflows/reusable-10-ci-python.yml`. The expanded
coverage command and observer extraction in `preflight.md` / `README.md` remain
accurate, including Python 3.14, four workers and the three grammar ignores.
Those protected files need no edits. A fresh copy of the embedded observer is
prepared under `/tmp/issue-4502-round2/plugin`.

Bounded acceptance commands, planned before editing tests:

```bash
python -m pytest tests/scripts/test_issue_4001_target_coverage.py -m 'not slow' -q
python -m pytest tests/scripts/test_check_consumer_sync_drift.py \
  tests/scripts/test_validate_run_contract.py \
  tests/scripts/test_aggregate_agent_metrics.py -m 'not slow' \
  --cov=scripts.check_consumer_sync_drift \
  --cov=scripts.validate_run_contract --cov=scripts.aggregate_agent_metrics \
  --cov-config=pyproject.toml --cov-report=term-missing \
  --cov-report=json:/tmp/issue-4502-round2/coverage.json \
  --cov-report=xml:/tmp/issue-4502-round2/coverage.xml
python docs/evidence/issue-4001/extract_target_coverage.py \
  /tmp/issue-4502-round2/coverage.json --xml /tmp/issue-4502-round2/coverage.xml
```

The same full Gate command will be replayed with its reports redirected under
`/tmp/issue-4502-round2/gate` and the embedded observer on `PYTHONPATH`. Existing
before/after evidence is preserved. Coverage totals alone do not establish CI
success; a failing replay leaves that acceptance criterion open.
