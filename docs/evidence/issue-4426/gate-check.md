# Issue #4426 Gate check and stop rule

Recorded 2026-11-06T17:31:27Z, after the contract and inventory commits. This
stop rule binds the remaining coverage work. It was not in place before those
two commits.

## Stop rule

- Attempt limit: two failed runs of the same required check. The second failure
  is the stop.
- Elapsed-time limit: 10 minutes for one command, and 20 minutes for the whole
  step that contains it.
- The focused check below must finish in under two minutes. A run that exceeds
  two minutes is the first broken step.
- When a limit trips, report that step and stop. Do not start another fix in
  the same step.

## Real input

Command:

```bash
python3 -m pytest tests/docs/test_issue_4426_contract_record.py tests/docs/test_issue_4426_pr_inventory.py -q -m "not slow" --tb=line
```

Outcome at 2026-11-06T17:31:27Z: `6 passed in 0.30s`, exit 0. That is under
two minutes. Adding `tests/docs/test_issue_4426_gate_check.py` to that command
then printed `7 passed in 0.31s`, exit 0.

## Gate pytest and coverage command

`pr-00-gate.yml` job `python ci` calls
`.github/workflows/reusable-10-ci-python.yml` with:

- `primary-python-version` and `coverage-python-version`: `3.14`
- `python-versions`: `["3.13", "3.14"]`
- `pytest-workers`: `4`
- marker `not quarantine and not slow`
- `pytest_args`: `-n auto --dist load`
- `coverage-min`: `70`
- `artifact-prefix`: `gate-`

The reusable Pytest step builds arguments and runs
`pytest -p ci_test_growth "${args[@]}"`. When coverage is enabled and
`pyproject.toml` exists, the arguments include `--cov`,
`--cov-config=pyproject.toml`, `--cov-report=xml:coverage.xml`,
`--cov-report=term-missing`, and `--cov-report=json:coverage.json`. Coverage is
enabled only for the coverage Python version, so Gate's comparable artifact is
the Python 3.14 bundle. The xdist branch then appends `-n` with the worker
count and `--dist=loadgroup`.

`pyproject.toml` sets `branch = true` and
`source = ["scripts", "tools", "src"]`. Blended statement-plus-branch
accounting is covered lines plus covered branches over statements plus
branches. The coverage minimum step reads `coverage.xml` `line-rate`, which is
not that blended total.
