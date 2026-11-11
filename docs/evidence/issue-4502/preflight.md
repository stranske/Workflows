# Coverage preflight, recorded before test edits

- Checked-out baseline: `b25657e57ec09b90f6bac8fa5d892f822b3bc34c`.
- Current main, confirmed through GitHub's commit API on 2026-11-11:
  `e621d8f0ed8b83b9648b7fa8577b4f236bd57f1d` (also local `origin/main`).
- Gate: `.github/workflows/pr-00-gate.yml`, `python-ci` / `python ci`, calls
  `.github/workflows/reusable-10-ci-python.yml`, job `tests`, step
  `Pytest (unit tests with coverage)`. Coverage runtime: Python 3.14.
- `docs/AGENT_ISSUE_FORMAT.md` is absent from the checkout and GitHub main;
  fetching it at the historical repair SHA also returned HTTP 404. Its contents
  cannot be inspected. This limitation does not require workflow edits.
- #4423 resolves the extractor to
  `docs/evidence/issue-4001/extract_target_coverage.py`. It too is absent on main.
  Recovered verbatim from `f6650810fb2056598652ff9039fc920cdb386099`, blob
  `9c2f2a054db24a0027d85bb89671bd49012325cb`, at that same path.
  It rejects missing/duplicate targets and invalid counts.

The current Gate command expands to the following (the earlier #4423 command
predates the grammar-suite split and current worker cap):

```bash
pytest -p ci_test_growth -m 'not quarantine and not slow' \
  --junitxml=pytest-junit.xml --cov --cov-config=pyproject.toml \
  --cov-report=xml:coverage.xml --cov-report=term-missing \
  --cov-report=json:coverage.json \
  -n auto --dist load \
  --ignore=tests/scripts/test_pr_verifier_delivery_destinations.py \
  --ignore=tests/scripts/test_pr_verifier_prompt_coverage.py \
  --ignore=tests/scripts/test_pr_verifier_body_overall_integration.py \
  -n 4 --dist=loadgroup
python docs/evidence/issue-4001/extract_target_coverage.py coverage.json
```

The plugin is embedded in the reusable workflow, not the similarly named
`scripts/ci_test_growth.py`. To reproduce, extract the step's `cat` heredoc
without changing its contents into a temporary directory and prepend that
directory and the repository to `PYTHONPATH`. The final repeated worker and
distribution options win, matching the workflow argument order.

Bounded acceptance command (target coverage only, **not full Gate evidence**):

```bash
python -m pytest tests/scripts/test_check_consumer_sync_drift.py \
  tests/scripts/test_validate_run_contract.py \
  tests/scripts/test_aggregate_agent_metrics.py -m 'not slow' \
  --cov=scripts.check_consumer_sync_drift \
  --cov=scripts.validate_run_contract --cov=scripts.aggregate_agent_metrics \
  --cov-config=pyproject.toml --cov-report=term-missing \
  --cov-report=json:coverage.json --cov-report=xml:coverage.xml
python docs/evidence/issue-4001/extract_target_coverage.py coverage.json
```

The importable dotted module names are intentional: coverage's path form
`--cov=scripts/foo` does not measure a single `.py` module correctly. The same
three source modules, branch settings and exclusions are used for both bounded
measurements. No percentage target is inferred from the combined-unit criterion.
