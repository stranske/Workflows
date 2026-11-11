# Executable missing-unit acceptance

The recovered extractor now accepts an optional `--max-missing N` argument.
Validated missing statements plus branches are summed across the three targets.
An inclusive total at or below N returns 0; an over-budget total returns 1
and reports the measured counts. Invalid limits or reports return 2 without
publishing a total. JSON-only reporting without a limit retains its interface.
No workflow or target production-module change was made.

The pre-test baseline, concrete Gate job, expanded coverage command and bounded
acceptance command are recorded in [round3-preflight.md](round3-preflight.md).
The missing issue-format document leaves the first task unchecked. The current
main SHA at this round's preflight was
`49a88b3776e7cc60d13c670d52c81b8303dfec0a`; the checked-out head was
`c416ee365d13c7d87490ef4f6cd2442d1e58f175`, with this increment in its working tree.
There is no final commit SHA for this increment because staging failed on the
read-only Git metadata mount.

## Focused verification

The original 46 extractor cases passed before editing. Adding the 10 new cases
first produced **7 failed, 49 passed** against the original CLI. After adding
the option, the identical command produced **56 passed**:

```bash
python -m pytest tests/scripts/test_issue_4001_target_coverage.py -m 'not slow' -q
```

Complete red/green output is retained under [budget-after/](budget-after/).
The new cases cover inclusive boundaries, an over-budget result, invalid limits,
JSON/XML disagreement despite a generous limit, and zero-unit retained Gate
reports with both zero and 46-unit limits. The original JSON-only tests pass.

Two deliberate breaks separately changed `>` to `>=` and removed missing
branches from the sum. The named budget test failed in both cases, then all
four cases passed after exact byte restoration. Complete diffs, reverse diffs,
commands, output and restored digest are in
[exclusive-limit.md](budget-after/exclusive-limit.md) and
[ignore-branches.md](budget-after/ignore-branches.md).

The 268 target cases passed with targeted coverage:

```bash
python -m pytest tests/scripts/test_check_consumer_sync_drift.py \
  tests/scripts/test_validate_run_contract.py \
  tests/scripts/test_aggregate_agent_metrics.py -m 'not slow' \
  --cov=scripts.check_consumer_sync_drift \
  --cov=scripts.validate_run_contract --cov=scripts.aggregate_agent_metrics \
  --cov-config=pyproject.toml --cov-report=term-missing \
  --cov-report=json:/tmp/issue-4502-round3/coverage.json \
  --cov-report=xml:/tmp/issue-4502-round3/coverage.xml
```

| Target | Statements | Missing statements | Branches | Missing branches | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| aggregate_agent_metrics.py | 899 | 0 | 380 | 0 | 100.00% |
| check_consumer_sync_drift.py | 654 | 0 | 298 | 0 | 100.00% |
| validate_run_contract.py | 448 | 0 | 212 | 0 | 100.00% |

The complete targeted reports are `budget-after/target-coverage.json.gz` and
`budget-after/target-coverage.xml.gz`. Both original replay report digests were
also independently checked against `replay-after/artifact-manifest.json`.
An immediately runnable bounded acceptance check on those full Gate reports is:

```bash
python docs/evidence/issue-4001/extract_target_coverage.py \
  docs/evidence/issue-4502/replay-after/coverage.json.gz \
  --xml docs/evidence/issue-4502/replay-after/coverage.xml.gz --max-missing 46
```

It returns 0, reproduces each target's zero missing statements and branches,
and prints `combined_missing_units=0`. There are no remaining target locations
requiring behavioral limitation evidence. Original comparable measurements
remain Gate **2 → 0** and bounded **21 → 0**, as detailed in README.md.
The historical 226-unit observation is 226 above the final zero; this increment
does not claim an additional target-coverage reduction.

Black formatted the changed Python files, and the required whole-repository
check passed: **1,009 files unchanged**, exit 0. As in prior rounds, the temporary
sequential dispatcher calls Black's own `reformat_one` with its original mode
and AST safety check. Default multiprocessing fails in this sandbox; setting
one worker stalled, so that attempt was interrupted. The passing invocation:

```bash
PYTHONPATH=/tmp/issue-4502-round3/black-serial \
GITHUB_OUTPUT=/tmp/issue-4502-round3/black-output \
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

The adapter is the same as the code recorded in README.md. Ruff passed for both
changed Python files; no coverage or formatting exclusion was added.

## Full Gate replay

The configured invocation completed with exit 1: **83 failed, 15,804 passed,
25 skipped, 3 xfailed in 399.38s**. Comparing complete JUnit reports against
the prior replay finds the exact same 83 failing nodes, with zero new or
resolved nodes. All 56 extractor cases passed. This is a failing local Gate
invocation, not a successful hosted CI receipt.

After extracting the unchanged embedded observer as documented in README.md:

```bash
PYTHONPATH=/tmp/issue-4502-round3/plugin:$PWD \
pytest -p ci_test_growth -m 'not quarantine and not slow' \
  --junitxml=/tmp/issue-4502-round3/gate/pytest-junit.xml \
  --cov --cov-config=pyproject.toml \
  --cov-report=xml:/tmp/issue-4502-round3/gate/coverage.xml \
  --cov-report=term-missing \
  --cov-report=json:/tmp/issue-4502-round3/gate/coverage.json \
  -n auto --dist load \
  --ignore=tests/scripts/test_pr_verifier_delivery_destinations.py \
  --ignore=tests/scripts/test_pr_verifier_prompt_coverage.py \
  --ignore=tests/scripts/test_pr_verifier_body_overall_integration.py \
  -n 4 --dist=loadgroup
```

Selection, coverage configuration, observer, markers and worker/distribution
settings match Gate; only report destinations are redirected. Complete reports
and logs are retained in `budget-after/coverage.json.gz`, `coverage.xml.gz`,
`pytest-junit.xml.gz` and `pytest.log.gz`, with source digests in `provenance.json`
and per-artifact digests in `artifact-manifest.json`. Every failing node and the
comparison are retained in `failure-comparison.json`.

The new full reports independently reproduce each target's zero missing
statements and branches, 100.00% coverage and a zero-unit accepted total:

```bash
python docs/evidence/issue-4001/extract_target_coverage.py \
  docs/evidence/issue-4502/budget-after/coverage.json.gz \
  --xml docs/evidence/issue-4502/budget-after/coverage.xml.gz --max-missing 46
```

All six target source/test files were checked against HEAD byte for byte;
this increment contains no changes to those files or deliberate breaks.
The Gate-generated collection inventory was restored to its original bytes.
Full CI acceptance remains open. The complete proposed PR-body update, with
the original target-test transcripts and this round's two additional probes,
is retained in `budget-after/proposed-pr-body.md.gz`; it is unpublished.

## Delivery blockers

Staging the meaningful extractor and test changes failed with:

```text
fatal: Unable to create '/home/runner/work/Workflows/Workflows/.git/index.lock': Read-only file system
```

The GitHub connector rejected the requested `needs-human` label on source issue
#4502: `MCP tool call requires approval, but approval policy is never`.
It rejected the source-issue blocker comment for the same reason; neither
remote write succeeded.
PR #4658 had already merged before this round. Its body was not changed, and no
new branch or PR was created. The open-PR handoff invariant cannot be satisfied
for a merged PR. No task checkbox or full-CI acceptance claim is advanced.
