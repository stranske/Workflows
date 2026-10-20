# Ranked coverage round 15: verified partial handoff

Adds 33 test cases for docs lookup failures and upstream-reference boundaries,
ledger probe/fetch caching and malformed inputs, and evidence artifact failures
and warn-only CLI reporting. No production code changes or real bug fixes were
needed. Temporary production mutations were restored after every probe.

## Baseline and target selection

Use the supplied whole-CI **87.08%** blended coverage as the repository baseline.
The checked-in `coverage.json` is an unrelated February report covering five
`src/` files; its 93.12% does not establish repository coverage above 90%.
GitHub API access failed, so current Gate artifacts and the authoritative
escaped-defect/churn ranking could not be retrieved. This run retains the six
targets already selected by commit `1828632fbf1593dffbabd717fd22c4d2f595bb22`;
it does not claim to have independently verified their ranking.

The initial six-module local suite had 340 passing tests and 80.39% coverage of
those targets. Including the other three existing docs/contract test modules
gave a proper matched local baseline of 469 passing tests and 92.22% target
coverage. This difference is existing coverage, not improvement from this run.

| Target | Missing statements before → after | Missing branches before → after | After coverage |
| --- | --- | --- | --- |
| `scripts/api_client.py` | 1 → 1 | 1 → 1 | 98.92% |
| `scripts/check_docs_drift.py` | 22 → 5 | 16 → 5 | 97.39% |
| `scripts/langchain/task_validator.py` | 3 → 3 | 3 → 3 | 98.11% |
| `scripts/ledger_validate.py` | 30 → 13 | 26 → 12 | 95.58% |
| `scripts/validate_run_contract.py` | 41 → 20 | 27 → 19 | 94.09% |
| `tools/langchain_client.py` | 17 → 17 | 7 → 7 | 93.72% |

The matched suite now has **502 passing tests**, 95.75% target coverage, and
**88 additional covered units** (55 statements + 33 branches). This is **92
units short of 180 locally**; the whole-CI reduction remains unverified. The
API client's final exhaustion raise is unreachable under its bounded loop's
normal behavior, so no artificial iteration mock was added to cover it. Task
validator and client-builder gaps remain unchanged in this iteration. Remaining
docs, ledger, contract, and client gaps are follow-up work; none are claimed as
covered. Publication is blocked by the runner's read-only `.git` mount and
unavailable GitHub network access, so this handoff does not establish completion
of the PR's delivery or CI acceptance criteria.

## Validation

```bash
python -m pytest tests/scripts/test_api_client.py tests/scripts/test_check_docs_drift.py tests/scripts/test_ledger_validate.py tests/scripts/test_task_validator.py tests/scripts/test_validate_run_contract.py tests/tools/test_langchain_client.py tests/test_check_docs_drift.py tests/contracts/test_document_identity.py tests/contracts/test_validate_run_contract.py --cov=scripts.api_client --cov=scripts.check_docs_drift --cov=scripts.ledger_validate --cov=scripts.langchain.task_validator --cov=scripts.validate_run_contract --cov=tools.langchain_client --cov-report=term-missing -m 'not slow' -q
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
black --check --line-length 100 --exclude '(\.venv|\.workflows-lib|node_modules)' .
ruff check --output-format github --extend-exclude .workflows-lib .
git diff --check
```

Results: 502 tests passed; both Black checks passed for 820 files; Ruff and diff
checks passed. Each changed Python file was also formatted with
`black --line-length 100` individually. The sandbox denied Black's process
workers, and its threaded multi-file path hung. Serial single-file Black checks
using the same root configuration populated `/tmp/black-round15`; both exact
whole-tree commands then passed with `BLACK_CACHE_DIR=/tmp/black-round15` and
`BLACK_NUM_WORKERS=1`. No formatter, lint, or coverage configuration was changed.

Actual break-and-revert runs covered all 33 new parameter cases across 23
mutation/reversion pairs. Each mutation produced pytest exit 1 with an executed
test failure; restoring source produced exit 0. The receipt in
[`verification.json`](verification.json) records each source mutation, selected
test, failed case names, and restored passing case names. The last CLI probe
changes warn-only exit behavior and catches both valid and invalid inputs.
The combined 502-test suite was rerun successfully after all source restoration.

## Delivery blocker

`git add` failed with `Unable to create .git/index.lock: Read-only file system`.
`gh pr view` failed connecting to `api.github.com`. No commit, push, PR-body edit,
comment, label, or draft-state change was possible. Verified source tests and
this evidence remain in the workspace for an authorized publishing runner.
