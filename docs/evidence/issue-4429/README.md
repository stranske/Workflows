# Issue #4429 coverage evidence

Four new behavioral tests pass. The targeted measurement decreases combined missing
statements plus branches from **3 to 0**. This is **not** a completed CI Gate
measurement or a claim that this PR recovered the historical 107-unit shortfall.

## Baseline identity and measurement contract

Live main was `408651629f027292c94f38f2c5aa0c1d3e24fe79`, confirmed through the
GitHub commit API on 2026-11-06. Measurements ran in the provisioned checkout
`babf0c0a3c23549cf3542831702077deaea068b2` before the changes and with this PR's
test changes afterward. [baseline-blobs.json](baseline-blobs.json) records identical
Git blob IDs between that checkout and live main for all three targets, their four
test modules, `pyproject.toml`, and the two Gate workflows. Other parts of the
checkout differ from main; these results are not a pristine-main full-suite run.

`docs/AGENT_ISSUE_FORMAT.md` does not exist in this checkout or at live main
(GitHub contents API returned 404). The existing canonical issue template,
`docs/templates/AGENT_ISSUE_TEMPLATE.md`, was inspected instead. No content was
inferred for the absent document.

Gate's `python-ci` call in `.github/workflows/pr-00-gate.yml` invokes
`.github/workflows/reusable-10-ci-python.yml`, job `tests`, step
`Pytest (unit tests with coverage)` (step ID `pytest`).
Python 3.14 instruments coverage; Python 3.13 is the other selected runtime.
The configured invocation, including the arguments appended by both the caller
and reusable workflow, is:

```bash
pytest -p ci_test_growth -m 'not quarantine and not slow' \
  --junitxml=pytest-junit.xml --cov --cov-config=pyproject.toml \
  --cov-report=xml:coverage.xml --cov-report=term-missing \
  --cov-report=json:coverage.json -n auto --dist load -n 4 --dist=loadgroup
```

The final `-n 4 --dist=loadgroup` takes precedence. No positional test paths are
passed. The testpaths and strict options come from `pyproject.toml`; branch
measurement and the existing exclusions also come from that file. The observer
is extracted verbatim from the workflow's `ci_test_growth.py` heredoc into
`/tmp/issue-4429/observer`, then loaded through `PYTHONPATH`.

The [extractor](extract_target_coverage.py) is byte-identical to
[#4423's extractor at f6650810](https://github.com/stranske/Workflows/blob/f6650810fb2056598652ff9039fc920cdb386099/docs/evidence/issue-4001/extract_target_coverage.py),
Git blob `9c2f2a054db24a0027d85bb89671bd49012325cb`. Both measurements use its
`summary.missing_lines + summary.missing_branches`, never the partial-branch count:

```bash
python docs/evidence/issue-4429/extract_target_coverage.py \
  docs/evidence/issue-4429/targeted/before/coverage.json
python docs/evidence/issue-4429/extract_target_coverage.py \
  docs/evidence/issue-4429/targeted/after/coverage.json
```

## Complete targeted measurements

This exact targeted command ran before and after, with `PHASE` set to `before`
and `after` respectively. Runtime: Python 3.14.10, pytest 9.2.0, pytest-cov 7.1.0.
It uses Gate's coverage configuration and the three requested module targets;
it does not use Gate's complete test selection.

```bash
COVERAGE_FILE=/tmp/issue-4429/$PHASE/target.coverage pytest \
  tests/scripts/test_check_consumer_sync_drift.py \
  tests/scripts/test_validate_run_contract.py \
  tests/contracts/test_validate_run_contract.py \
  tests/scripts/test_aggregate_agent_metrics.py \
  --cov=scripts.check_consumer_sync_drift \
  --cov=scripts.validate_run_contract \
  --cov=scripts.aggregate_agent_metrics --cov-report=term-missing \
  --cov-report=json:/tmp/issue-4429/$PHASE/target-coverage.json \
  --cov-report=xml:/tmp/issue-4429/$PHASE/target-coverage.xml -m 'not slow' -q
```

| Target | Before missing statements | Before missing branches | Before total | After missing statements | After missing branches | After total | This round's reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| aggregate_agent_metrics.py | 0 | 3 | 3 | 0 | 0 | 0 | 3 |
| check_consumer_sync_drift.py | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| validate_run_contract.py | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **Combined** | **0** | **3** | **3** | **0** | **0** | **0** | **3** |

Before: **324 passed in 4.74s**. After: **328 passed in 3.34s**.
Complete files, including all per-function detail, are retained:

- Before: [coverage.json](targeted/before/coverage.json),
  [coverage.xml](targeted/before/coverage.xml), [pytest output](targeted/before/pytest.log),
  [extractor output](targeted/before/extracted.txt).
- After: [coverage.json](targeted/after/coverage.json),
  [coverage.xml](targeted/after/coverage.xml), [pytest output](targeted/after/pytest.log),
  [extractor output](targeted/after/extracted.txt).

The three initial missing branches were metrics `492→481`, `954→910`, and
`1011→996`. Their input cases are empty trace dictionaries, unknown/missing step
success values, and non-list freshness update targets followed by another record.
All three are now covered; no units remain in the targeted result. These cases
also assert downstream behavior: retain later valid references, preserve durations
without counting unknown outcomes, and retain later valid update paths.

Drift and contract validation already had no uncovered units. Existing drift
tests cover main's preflight errors, remote/session helpers and report writers.
The new drift test discriminates cache lifetime: a failed blob read is reused
within one invocation, another SHA is independently readable, and the next
invocation retries the previously unreadable SHA. It asserts parsed report
fields and complete counts. There are no new exception assertions requiring
conversion to `pytest.raises`.

Existing validator tests exercise fail-closed manifest/evidence paths and assert
violations and rejection. No duplicate validator tests were added to an already
fully covered target. An existing validator test was rerun with a deliberate
behavioral break to preserve full validator mutation evidence.

Historical Gate counts recovered in #4423 remain **226 → 153**, a reduction of
**73** by #4012. The current targeted totals would be 223 and 226 fewer units
than 226 respectively, but those are cumulative, differently selected local
measurements. Only **3 units** are attributable to this round. A local result
below 46 does not establish the required hosted Gate result.

## Mutation evidence and remaining work

[mutation-evidence.md](mutation-evidence.md) retains complete stdout/stderr and
exit status for each named test under its deliberate break, the byte-for-byte
reversion, and the same test passing. All four new tests have RED=1 and GREEN=0.
The existing validator test's evidence is included in full as well. Probes ran in
an isolated copy, so the working target sources were never mutated. Only trailing
whitespace in the Markdown transcript was normalized; all output lines remain.

No production bug was found and no production target, workflow, coverage setting,
or existing test was changed. The final diff must continue to contain only the
test additions and evidence. Hosted Gate before/after artifacts and a successful
configured full-suite result remain outstanding; targeted artifacts above must
not be presented as Gate artifacts.

## Full-suite attempts and delivery limits

The first local full-suite attempt stalled and was interrupted. The subsequent
working-checkout attempt used the exact pytest arguments above, with output
paths under `/tmp/issue-4429/after`. It ended with process exit **3**:

```text
63 failed, 50585 passed, 25 skipped, 3 xfailed in 1071.72s (0:17:51)
coverage.exceptions.DataError: Can't combine branch coverage data with statement data
```

JUnit independently records **328 target-module test cases and zero failures**
in those cases. [full-suite-after.json](full-suite-after.json) records all failing
test identifiers, suite counters, the exit code, and the coverage error. This is
a failed local run, not a successful CI receipt.

For local isolation, that command set
`COVERAGE_FILE=/tmp/issue-4429/after/.coverage`. A nested flat-module-consumer
fixture inherited that absolute destination and wrote statement-only data there.
Read-only SQLite inspection confirmed `has_arcs=0` and only the fixture's
`test_thing.py` and `thing.py` in that file. The outer run's branch data could not
combine with it. **No full-suite coverage.json or coverage.xml was produced.**
The separate targeted reports were completed earlier with their own destinations
and remain valid. An authoritative full-suite rerun needs the normal CI environment
without this absolute `COVERAGE_FILE` override.

Both full-suite attempts loaded the workflow's observer from
`/tmp/issue-4429/observer`. A temporary `sitecustomize.py` under `/tmp` supplied
periodic asyncio polling for this sandbox. The current-main control runs in a
separate local clone at `408651629f027292c94f38f2c5aa0c1d3e24fe79`; its outcome is
recorded in [full-suite-before.json](full-suite-before.json). It also exited 3:

```text
63 failed, 49752 passed, 25 skipped, 3 xfailed in 992.51s (0:16:32)
coverage.exceptions.DataError: Can't combine branch coverage data with statement data
```

All **324** baseline target-module tests passed in that full run. Its absolute
`COVERAGE_FILE=/tmp/issue-4429/main-before/.coverage` override produced the same
collision, so it also produced no full-suite JSON/XML coverage reports. These
local full-suite attempts establish neither a Gate baseline nor Gate acceptance.
The exact command for each phase used the arguments above with the respective
output directories, `timeout --signal=INT --kill-after=30s 1200s`, and these
environment prefixes:

```bash
# Before, cwd=/tmp/issue-4429/main
PYTHONPATH=/tmp/issue-4429/async-wakeup:/tmp/issue-4429/observer:.
COVERAGE_FILE=/tmp/issue-4429/main-before/.coverage
# After, cwd=/home/runner/work/Workflows/Workflows
PYTHONPATH=/tmp/issue-4429/black-wakeup:/tmp/issue-4429/observer:.
COVERAGE_FILE=/tmp/issue-4429/after/.coverage
```

Black's required repository-wide check passed for **892 files**, and Ruff passed
for the two changed test modules and the retained extractor. The Black command
used `BLACK_NUM_WORKERS=1` and the temporary polling helper through `PYTHONPATH`;
its format rules and checks were unchanged.

The meaningful source commit is
`aee4391524b15e2755bdb4b8f0df076833f1a141`, in a local delivery clone because the
workspace's `.git` is read-only. The GitHub connector also refused the first blob
write: `MCP tool call requires approval, but approval policy is never`.
[publication-status.json](publication-status.json) records that failure. No remote
write succeeded. PR #4494 was independently merged during the session, before
these changes were published; its bootstrap Gate skipped Python CI and produced
no coverage artifact. Publishing the bundle requires an authorized write path and
a ready-for-review implementation PR. The complete prepared PR body is supplied
as a separate delivery artifact; it has not been published.
