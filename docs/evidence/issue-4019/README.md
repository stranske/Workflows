# Coverage round 4019: retained repair and review closure

Measured 2026-11-03, before editing tests. The pre-repair repository already
exceeded the owner's 90% stopping condition: **62,986 / 69,223 =
90.98998887652948%** blended covered statements plus branches. This is computed
from integer counters, not rounded display percentages. No new coverage targets
or test functions were added in this continuation. PR 4021 remains intact.

## Ranking and comparable artifacts

The ranking producer named in issue 4019 is Orchestrator's
`coverage-autopilot.py`; it is not present in this repository. The issue's emitted
ranking is the authoritative task input: escaped-defect signals, then churn,
then uncovered mass. The repository's `docs/reference/coverage-gap-analysis.md`
provides artifact guidance but no implementation of that ranking. We inspected
Gate and its reusable Python workflow before editing.

| Rank | Target | Escaped signals | Churn | Historical issue units | Base missing lines + branches | Head missing lines + branches | Reduction |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: |
| 1 | scripts/aggregate_agent_metrics.py | 16 | 45 | 6 | 0 + 3 | 0 + 3 | 0 |
| 2 | scripts/check_consumer_sync_drift.py | 6 | 14 | 79 | 0 + 0 | 0 + 0 | 0 |
| 3 | tools/llm_provider.py | 3 | 3 | 103 | 77 + 27 | 54 + 16 | 34 |
| Total | | | | 188 | 107 | 73 | 34 |

These are whole-suite **Python 3.14 only** counters. Overlapping Python 3.13
counts are never added. Both Gate artifacts have repository denominators
49,421 statements and 19,802 branches; all three target denominators match.
Whole-repository head counts are 45,698 covered statements and 17,322 covered
branches, 91.03910549961718%. The 34-unit delta is entirely in llm_provider.

- Base Gate: [41557902073](https://github.com/stranske/Workflows/actions/runs/41557902073), PR 4395 head `4800afb5c97fe6d3ecbfd337dbd2713b9d8c1e50`, artifact `gate-coverage-3.14-1` (13195852524).
- That PR merged as `3e513d30e1b11b30bd6a2fdc224adbca97d85930`, the repair's original base. Its [main canonical suite 41561335364](https://github.com/stranske/Workflows/actions/runs/41561335364), artifact `selftest-coverage-3.14-1` (13198385239), independently has identical totals and target counters.
- Retained repair head Gate: [41572375259](https://github.com/stranske/Workflows/actions/runs/41572375259), `a73444c3bd904949c443a24ec129c2d289bb856a`, artifact `gate-coverage-3.14-1` (13202412189), successful hosted pytest.
- `comparable-coverage.json` retains exact counters, missing line/branch lists,
  runtime, run IDs, and downloaded coverage JSON SHA256 hashes.

No claim of 180 units is made. The issue's 82.76%/188-unit snapshot is stale.
The explicit >=90% condition supersedes manufacturing further coverage.
Per target: aggregate has zero missing statements and only three partial branch
arcs; sync drift has no uncovered units; provider still has 70 units after the
retained tests, which could meaningfully be tested in another authorized round.
We do **not** claim these remaining provider paths are untestable. The reason
for stopping is the already-achieved repository threshold, not an unsupported
exception about untestability.

## Previous work and review fixes

The only matching local branch was `closer/issue-4019`, already checked out and
backing existing ready PR 4406. We retained its single commit `a73444c3b` (11
new test functions), and merged current main `c3f3fc5dc` before editing. Nothing
from PR 4021 was redone, reverted, or removed. No prior test was discarded.
The two insufficient assertions identified in review were replaced:

1. Confidence input 0.8 -> 0.6 avoids the independent high-confidence/no-tasks
   rule, so removing the no-evidence rule now fails (0.6 <= 0.35).
2. Anthropic retry must have the identical original prompt and no keyword
   arguments, so retrying with quality_context now fails.

Production code was changed temporarily for mutation experiments and restored
byte-for-byte after each experiment. No production changes are shipped.

## Actual mutation receipts

All 11 retained new test functions were run separately under a deliberate
behavior mutation (exit 1, named FAILED test), then after restoration (exit 0,
1 passed). `mutation-receipts.json` records full node IDs, commands, exact source
replacements and restored SHA256 hashes. The compressed packet
[`original-transcripts.tar.gz`](original-transcripts.tar.gz) preserves all 22
complete outputs under their original `01-red.txt` through `11-green.txt` names.
The unknown-provider mutation raises the wrong error class. The unavailable-provider
mutation omits the required error. The other nine fail assertions about behavior.
Tests 06 and 11 prove the two review repairs. The same files remain readable
individually in the [original #4406 delivery](https://github.com/stranske/Workflows/tree/2bd1aa094698d3e9f2ce91f754f6b00fb748a52d/docs/evidence/issue-4019).

From the repository root, list or read a member without extracting the packet.

```sh
archive=docs/evidence/issue-4019/original-transcripts.tar.gz
tar -tzf "$archive"
tar -xOzf "$archive" 06-red.txt
```

To recover all 22 files offline, check the packet before extracting it into a
new temporary directory.

```sh
archive=docs/evidence/issue-4019/original-transcripts.tar.gz
restore=$(mktemp -d) &&
  printf '%s  %s\n' '2bb8bbfe834c6fa9236991e22562fae21d214a67557db45525bf74fd73edcc3e' "$archive" |
    shasum -a 256 -c - &&
  tar -xzf "$archive" -C "$restore" &&
  printf 'Restored transcripts in %s\n' "$restore"
```

The exact acceptance commands and stop rule are in `acceptance.md`. Required
three-file pytest: **242 passed in 1.20s**, exit 0. Black with line length 100
left both changed test modules unchanged; Ruff passed. Full repository pytest
and release/verify pipelines were not run locally. Hosted CI is the full-suite
authority; local focused coverage cannot establish whole-repository reduction.

Focused Gate invocation: **242 passed in 31.55s**, exit 0, four workers.
[`focused-coverage.txt.gz`](focused-coverage.txt.gz) preserves the complete output.
The [original #4406 text](https://github.com/stranske/Workflows/blob/2bd1aa094698d3e9f2ce91f754f6b00fb748a52d/docs/evidence/issue-4019/focused-coverage.txt)
is readable in GitHub at the immutable delivery revision. The separate
`focused-targets.json` contains the three target counters. The 5.53% whole-source
figure comes from running only three test files. The whole-suite baseline is
reported in the earlier comparable artifact section.

From the repository root, verify the compressed bytes before printing the
original text. Redirect the output to a file to keep an offline copy.

```sh
(
  archive=docs/evidence/issue-4019/focused-coverage.txt.gz
  expected=5c0e0eb442c2bf73569504066173c6ce49b4220c7f790045b3f2212b8d726270
  if ! actual=$(shasum -a 256 "$archive") || [ "${actual%% *}" != "$expected" ]; then
    printf '%s\n' 'Focused coverage log checksum failed' >&2
    exit 1
  fi
  gzip -dc "$archive"
)
```

## Exact hosted CI failure drained

[Selftest 41667310644](https://github.com/stranske/Workflows/actions/runs/41667310644)
on 79a662301 failed two existing live PyPI compatibility tests in both runtimes:
`test_simulated_consumer_repo_sync` and `test_autofix_versions_env_not_stale`.
Both printed `coverage: pinned=7.17.0, latest=7.17.1`. The only configuration
repair is `.github/workflows/autofix-versions.env`'s coverage pin to 7.17.1.
This is an observed freshness failure, not a refactor, threshold change or
new test. The two exact failing node IDs passed locally, **2 passed in 3.26s**,
exit 0; command recorded before editing in acceptance.md and output retained
in pin-checks.txt. No broader dependency refresh was performed.

The first pin-only hosted attempt, Gate 41667929668, then printed a resolver
failure before pytest: `Because you require coverage==7.17.1 and
coverage==7.17.0 ... requirements are unsatisfiable`. The final fix also aligns
`pyproject.toml` and `requirements.lock` to the same 7.17.1. No other dependency
is changed. This supersedes the initial one-line-only description above.

After alignment, the required three-file command again passed: **242 passed
in 7.35s**, exit 0 (`required-after-pins.txt`). Focused pin-sync tests:
`/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_sync_dev_dependencies.py -q`;
see `sync-pin-tests.txt` for the result. No local full suite or install was run.
