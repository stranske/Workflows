# Bounded acceptance preflight

Recorded before test edits on 2026-11-11. Checked-out head:
`c416ee365d13c7d87490ef4f6cd2442d1e58f175`. Current main, confirmed through
GitHub's commit API and local `origin/main`:
`49a88b3776e7cc60d13c670d52c81b8303dfec0a`.
The original before-measurement SHA remains
`b25657e57ec09b90f6bac8fa5d892f822b3bc34c`.

`docs/AGENT_ISSUE_FORMAT.md` is still absent. Inspected the available
`docs/ci/ISSUE_FORMAT_GUIDE.md` and `docs/templates/AGENT_ISSUE_TEMPLATE.md`;
neither substitutes for the literal missing-document requirement. That task
remains unchecked. Read #4423 through GitHub and reconfirmed the recovered
extractor: `docs/evidence/issue-4001/extract_target_coverage.py`.

Inspected Gate `python-ci` in `.github/workflows/pr-00-gate.yml`, which calls
job `tests`, step `pytest` in `.github/workflows/reusable-10-ci-python.yml`.
Python 3.14 coverage command (prepare the embedded observer using README.md):

```bash
pytest -p ci_test_growth -m 'not quarantine and not slow' \
  --junitxml=pytest-junit.xml --cov --cov-config=pyproject.toml \
  --cov-report=xml:coverage.xml --cov-report=term-missing \
  --cov-report=json:coverage.json -n auto --dist load \
  --ignore=tests/scripts/test_pr_verifier_delivery_destinations.py \
  --ignore=tests/scripts/test_pr_verifier_prompt_coverage.py \
  --ignore=tests/scripts/test_pr_verifier_body_overall_integration.py \
  -n 4 --dist=loadgroup
```

This round makes the <=46 missing-unit criterion executable via an optional
`--max-missing` argument. Exit 0 accepts a validated total within the inclusive
limit; exit 1 reports a valid over-budget total; exit 2 rejects invalid input.
The JSON-only count-reporting interface remains supported. Planned bounded
acceptance command, using complete retained Gate reports:

```bash
python -m pytest tests/scripts/test_issue_4001_target_coverage.py -m 'not slow' -q
python docs/evidence/issue-4001/extract_target_coverage.py \
  docs/evidence/issue-4502/replay-after/coverage.json.gz \
  --xml docs/evidence/issue-4502/replay-after/coverage.xml.gz --max-missing 46
```

The existing full Gate replay is failing (83 failures); no passing CI claim is
made. PR #4658 was already merged before this round. Its lifecycle cannot meet
the open-PR handoff invariant, and no new branch or PR is authorized.
No workflow or target production-module change is needed for this increment.
