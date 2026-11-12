# Issue 4019 integration acceptance (PR for #4433)

Written to `acceptance-integration.md` rather than `acceptance.md` because
PR #4431 already adds `docs/evidence/issue-4019/r3/acceptance.md`; a second
copy would be an add/add conflict when #4431 merges.

## Task 1: #4431 state

- Acceptance date: 2026-11-06 (readback via `gh pr view 4431`).
- Checked head: `69e5b6d6cd3fb154be29890f2ae212772de8ce45`
- State: OPEN, `mergeCommit: null`, mergeable MERGEABLE, base `main`
  (branch `closer-r3/issue-4019`). Not delivered on main.
- Hosted checks on that head: Gate / gate, python ci / python 3.13 and 3.14,
  slow compatibility 3.13/3.14, CodeQL, Semgrep, test-quality: SUCCESS.
- `docs/AGENT_ISSUE_FORMAT.md` does not exist at repo root; only
  `templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md` does.

## Task 2 (partial): previously merged work

- #4021 merge commit `5dee9a65400f` and #4406 merge commit `2bd1aa094698`
  are both ancestors of `origin/main` (`git merge-base --is-ancestor`).
- Test function counts, main vs #4431 head: aggregate 71 -> 74,
  sync drift 66 -> 66, llm_provider 91 -> 112. No test file shrinks.
- Main's `tools/llm_provider.py::_supports_quality_context` still has
  `if supports is not None` after the `try/except`; #4431 changes it to
  `elif`. The raising-helper fix is therefore not on main.

## Task 2 (complete): retention verified

- `gh pr view 4021` -> MERGED, `5dee9a65400f`; adds 18/55/13 lines (all
  additions) to `tests/scripts/test_aggregate_agent_metrics.py`,
  `tests/scripts/test_check_consumer_sync_drift.py`,
  `tests/tools/test_llm_provider.py`.
- `gh pr view 4406` -> MERGED, `2bd1aa094698`; adds the 33 files under
  `docs/evidence/issue-4019/` (additions only, plus one line in
  `.github/workflows/autofix-versions.env`).
- #4431 file list (`gh pr view 4431 --json files`): the only files with
  deletions are `tools/llm_provider.py` (1+/1-, the `if` -> `elif` fix). Tests
  gain +29 (aggregate) and +221 (llm_provider) lines with 0 deletions, the
  sync-drift test is untouched, and all new evidence lives under
  `docs/evidence/issue-4019/r3/`, so no existing evidence file is overwritten.
- Conclusion: delivered behavior from #4021/#4406 is retained on main and is
  not removed or altered by #4431.

## Task 3: raw Gate coverage per target

Script: `docs/evidence/issue-4019/r3/target_missing.py` (from #4431 head
`69e5b6d6`; not on main yet). Syntax inspected: `python -I target_missing.py
<coverage.json>`; it reads `totals` and per-file `summary.missing_lines` /
`missing_branches`. Run from `/tmp/scripts` against artifacts downloaded
(`gh run download <run> -n gate-coverage-<py>-1`) into fresh `/tmp/art/<run>-<py>/`.
Artifacts are not expired. All three runs: workflow `Gate`, conclusion success.

| Run | Gate head SHA | Role |
|---|---|---|
| 41557902073 | `4800afb5c97f` | earlier baseline (2026-11-03) |
| 41668857273 | `79c84f753656` | baseline in #4431 evidence |
| 41717668636 | `f485bbc251a7` | head in #4431 evidence |

Denominator = `num_statements + num_branches` (branch coverage on, coverage 7.17.x).
Missing = missing statements + missing branches, three targets only.

### Python 3.14 (only runtime with coverage data)

| Run | Total covered/units (denominator) | aggregate_agent_metrics | check_consumer_sync_drift | llm_provider | Target missing | pytest tests / time |
|---|---|---|---|---|---|---|
| 41557902073 | 62986 / 69223 (90.99%) | 0+3 | 0+0 | 77+27=104 | 107 | 50339 / 711.6s |
| 41668857273 | 63040 / 69241 (91.04%) | 0+3 | 0+0 | 54+16=70 | 73 | 50377 / 691.5s |
| 41717668636 | 63110 / 69241 (91.15%) | 0+0 | 0+0 | 3+0=3 | 3 | 50403 / 668.9s |

Residuals at run 41717668636 (3.14): `tools/llm_provider.py` lines 265, 270, 292
(3 statements, 0 branches). Run 41668857273 residuals for aggregate were
branches 492->481, 954->910, 1011->996, all closed by 41717668636.

### Python 3.13 (discrepancy)

`summary.json` for every run shows `coverage_json: false`, `coverage_xml: false`,
`coverage_minimum: skipped`; the 3.13 artifact has no `coverage.json`. Gate runs
coverage only on 3.14, so **no per-runtime comparable 3.13 baseline/head missing
count exists in these artifacts**; the script cannot run on 3.13. Tests passed
on 3.13 (50339 / 50377 / 50403 tests, 0 failures, 30 skipped; junit 632.5s /
629.0s / 628.6s). The acceptance criterion's "separately report each runtime"
is therefore only satisfiable as: 3.14 measured, 3.13 not measured by Gate.
(`index.ndjson` in each artifact carries accumulated historical entries with
92.xx percentages; they are not per-run and were not used.)

### Residual explanation (3.14, head)

The three llm_provider lines (265, 270, 292) are still uncovered at the Gate
head `f485bbc`; #4431's later commits (head `69e5b6d6`) may change this and
were not measured at this earlier investigation stage; the continuation below
adds current-candidate run 41720166203.

Behavioral explanation: these three lines are `pass` statements in abstract methods
of the `LLMProvider` abstract base class (lines 265: `name` property, line 270: 
`is_available` method, line 292: `analyze_completion` method). The abstract class cannot be instantiated while those methods remain abstract,
but the base bodies can be called explicitly or via `super()` from a concrete
subclass. Overriding a method does not execute its base body. These empty base
bodies define no provider behavior to assert; retaining their three uncovered
statements is an explicit residual disposition, not a claim of unreachability
or 100% coverage. No exclusion or synthetic test was added to inflate coverage.

## Task 4: Capability fallback and mutation evidence review

### Capability fallback issue identified

The `tools/llm_provider.py::_supports_quality_context` helper has a control-flow
bug on main (head `57058e3b2`): line 315 uses `if supports is not None:`
instead of `elif supports is not None:`. This causes incorrect fallback behavior
when a provider's `supports_quality_context` method is callable but raises an
exception:

- **Buggy path**: If `supports()` raises, execution falls through to `if supports is not None:`,
  which evaluates the truthiness of the bound method object itself (always truthy),
  returning `True` even when the method raised an exception.
- **Expected path**: After a raised exception, execution should fall through to signature
  inspection of `analyze_completion` to check for a `quality_context` parameter.
- **Fix**: Change `if` to `elif` so that the `supports is not None` branch is only
evaluated when the callable branch did NOT execute (i.e., `supports` is not callable).

Demonstrated failure:
- Provider with `supports_quality_context()` that raises `Exception` and `analyze_completion`
  WITHOUT `quality_context` parameter: buggy code returns `True`, fixed code returns `False`.
- Provider with `supports_quality_context()` that raises `Exception` and `analyze_completion`
  WITH `quality_context` parameter: both return `True` (signature inspection finds it).

This is **not** a collection error; it is a behavioral assertion failure in the
capability detection logic. #4431 fixes this with the `if` -> `elif` change.

### Mutation evidence validation

Source: `docs/evidence/issue-4019/r3/mutations/mutation-receipts.json` from #4431
head `69e5b6d6cd3fb154be29890f2ae212772de8ce45`.

Script: `docs/evidence/issue-4019/r3/mutate.py` (run from repo root).

27 mutation receipts were inspected for runs executed against the exact delivery candidate:
- **Operators**: 3 in `scripts/aggregate_agent_metrics.py`, 24 in `tools/llm_provider.py`
  (via `tests/tools/test_llm_provider.py::TestRemainingProviderPaths::` tests).
- **All receipts**: `proof_ok: true` (27/27).
- **Red exit**: All mutations caused test failures (exit code 1 with "FAILED" in output).
- **Green exit**: All restorations passed (exit code 0).
- **Byte restoration**: All SHA256 checks passed (`sha256_before == sha256_restored`).

Nodes and behavioral assertions:
- **aggregate_agent_metrics**: 3 mutations in conditional logic that is exercised
  by the added tests (test 01-03). Each mutation replaces a guard with an unconditional
  or inverted condition, causing the test to fail.
- **llm_provider**: 24 mutations covering:
  - Exception handling fallbacks (04, 07, 08, 09, 11, 16)
  - Conditional inversion (05, 06, 12, 14, 15, 17, 18, 23a-c, 24)
  - Return value changes (10, 13, 19-22b)
  
All mutations target **behavioral assertion failures**, not collection errors.
The mutation operator replacements are exact, the test nodes are precise, and
all byte-restoration checks confirm the source was perfectly restored.

### Mutation 09: the capability fallback fix itself

Mutation 09 specifically tests the fix:
- **Node**: `tests/tools/test_llm_provider.py::TestRemainingProviderPaths::test_supports_quality_context_error_falls_back_to_legacy_signature`
- **Replace**: `elif supports is not None:` -> `if supports is not None:`
- **Result**: Test fails (red exit 1) because the bug is reintroduced; test passes (green exit 0) after restoration.

This mutation directly validates that the `elif` fix is necessary and correct:
the test checks that when a callable `supports_quality_context` raises, the code
falls back to signature inspection. Reverting to `if` breaks this fallback,
proving the fix addresses a real behavioral failure.

## Task 5: Historical focused pytest execution on candidate revision

### Setup

- **Interpreter**: `/opt/anaconda3/bin/python3` (owner-selected local runtime;
  portable reproduction uses the checkout-selected supported Python environment)
- **Working directory**: Repository root
- **Changes applied**: tools/llm_provider.py (1 line: `if` -> `elif` fix),
  tests/scripts/test_aggregate_agent_metrics.py (+29 lines),
  tests/tools/test_llm_provider.py (+221 lines)
- **Revision under test**: `69e5b6d6cd3fb154be29890f2ae212772de8ce45` (head of #4431)
- **Base acceptance-integration.md commit**: `57058e3b2a7b05dc0919177a6e7166dd6ad5ec24`

### Command

```bash
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_aggregate_agent_metrics.py tests/scripts/test_check_consumer_sync_drift.py tests/tools/test_llm_provider.py
```

### Results

```
============================= 268 passed in 0.93s ==============================
```

- **Exit status**: 0
- **Test count**: 268 passed, 0 failed, 0 skipped
- **Duration**: 0.93 seconds
- **Date**: 2026-11-06

All three target files pass. The 268 tests include:
- 74 tests in test_aggregate_agent_metrics.py (from 71 on main, +3 added)
- 66 tests in test_check_consumer_sync_drift.py (unchanged)
- 128 tests in test_llm_provider.py (from 112 on main, +16 added, including
  24 new TestRemainingProviderPaths tests covering the mutation nodes)

### Routing #4431 through normal review

- **PR**: #4431 (closer-r3/issue-4019)
- **Head**: `69e5b6d6cd3fb154be29890f2ae212772de8ce45`
- **State**: OPEN, mergeable MERGEABLE, base `main`
- **Hosted checks**: All SUCCESS (Gate/gate, python ci 3.13/3.14, slow compatibility, CodeQL, Semgrep, test-quality)
- **Normal review**: PR must go through standard review process without bypassing active writer ownership
- **After integration**: Rerun focused pytest command and verify:
  - `gh pr view 4431 --repo stranske/Workflows --json state,headRefOid,mergeCommit,statusCheckRollup`
  - `git merge-base --is-ancestor <mergeCommit> origin/main`

## Conclusion

- **Capability fallback**: Demonstrated failure in `_supports_quality_context` with
  raising callable helpers; fix verified with mutation 09 and behavioral tests.
- **Mutation evidence**: All 27 receipts inspected against mutate.py and source;
  all behavioral assertion failures distinguished from collection errors; all byte
  restorations confirmed.
- **Coverage residuals**: Lines 265, 270, 292 in llm_provider.py are abstract method
  `pass` statements, intentionally empty base bodies; they remain an explicitly accepted
  measurement residual rather than an unreachable-code claim.
- **Absent runtime coverage**: Python 3.13 coverage explicitly documented as not
  measured by Gate; 3.14 coverage complete at 91.15% with 3 statement residuals.
- **Focused pytest**: Historical candidate run passed with 268 tests; integrated
  revision acceptance remains UNMET until #4431 reaches main and is retested.
- **Review and merge**: #4431 ready for normal review; hosted checks green; after
  merge, verify merge commit is ancestor of main.

## Verified continuation corrections (2026-11-06)

Outcome 1 = UNMET: #4431 is still OPEN, so neither integrated focused pytest
nor delivered-final-tree coverage has been established. Historical candidate
results above are preserved and are not integration proof. Acceptance command:

```sh
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_aggregate_agent_metrics.py tests/scripts/test_check_consumer_sync_drift.py tests/tools/test_llm_provider.py
```

Use the repository-selected virtual environment when applicable; otherwise the
owner selects `/opt/anaconda3/bin/python3` locally. Portable instructions use
`python3` from the selected supported environment (Python 3.13 or newer).
Stop rule: two failures at the same step or 60 minutes; preserve ownership and
report the first broken step. No pins, historical receipts, or dependency
worktrees were changed by this continuation.

### Tested checkout provenance (discussion_r4497764977)

The Python 3.14 checkout log in each downloaded run archive prints the merge
checkout below, including its base in `HEAD is now at ... Merge HEAD into BASE`.
`git show -s --format=%P CHECKOUT` independently confirms base/head parents.
The run API's `head_sha` identifies the PR head, not the tested checkout.

| Gate run | Recorded PR head | Tested checkout | Tested base (first parent) |
|---|---|---|---|
| [41557902073](https://github.com/stranske/Workflows/actions/runs/41557902073) | `4800afb5c97fe6d3ecbfd337dbd2713b9d8c1e50` | `67e188fefd21d38304641e70ba4bc628be9d0555` | `c4633a95058d927c309dc7d666ff1d8dc85c2cc3` |
| [41668857273](https://github.com/stranske/Workflows/actions/runs/41668857273) | `79c84f753656a5fcf594aa0cae30e23ab3b76119` | `72f06668e4dba889030199c03541c6f18930b905` | `4cbdbac8b54f4fe1b2479ce79c855489e9f4d168` |
| [41717668636](https://github.com/stranske/Workflows/actions/runs/41717668636) | `f485bbc251a7b79216746071591d291023c38bb5` | `0e7a70ad474b0c0287a14331b4923ce67b432d25` | `2bd1aa094698d3e9f2ce91f754f6b00fb748a52d` |

For **each** row, `git rev-parse CHECKOUT:PATH` equals
`git rev-parse HEAD:PATH` for all three targets (nine comparisons). Blob IDs:

| Target | 41557902073 checkout = head | 41668857273 checkout = head | 41717668636 checkout = head |
|---|---|---|---|
| `scripts/aggregate_agent_metrics.py` | `ff8693012c52ab0966d818557d396d83011ed4e5` | `ff8693012c52ab0966d818557d396d83011ed4e5` | `ff8693012c52ab0966d818557d396d83011ed4e5` |
| `scripts/check_consumer_sync_drift.py` | `383a70446744e679bccbe66fb4f57c41f4933b5a` | `383a70446744e679bccbe66fb4f57c41f4933b5a` | `383a70446744e679bccbe66fb4f57c41f4933b5a` |
| `tools/llm_provider.py` | `e5f662c015c73a9d5f506ac876d45e1640f31e55` | `5848bd7ff360c5778e9ef6c1d3ec6aa64a0ee3d5` | `96d848a4385ed7299cd858aa10774d6f0476f129` |

This establishes target-source equivalence within each run, not whole-tree or
final-head equivalence. The provider source differs across runs; equal
statement/branch denominators do not imply identical behavior.

### Per-target denominators (discussion_r4497764999)

Values read separately from each artifact's `files[PATH].summary`:

| Gate run | Target | num_statements | num_branches | Sum |
|---|---|---:|---:|---:|
| 41557902073 | `scripts/aggregate_agent_metrics.py` | 899 | 380 | 1279 |
| 41557902073 | `scripts/check_consumer_sync_drift.py` | 633 | 296 | 929 |
| 41557902073 | `tools/llm_provider.py` | 447 | 114 | 561 |
| 41668857273 | `scripts/aggregate_agent_metrics.py` | 899 | 380 | 1279 |
| 41668857273 | `scripts/check_consumer_sync_drift.py` | 633 | 296 | 929 |
| 41668857273 | `tools/llm_provider.py` | 447 | 114 | 561 |
| 41717668636 | `scripts/aggregate_agent_metrics.py` | 899 | 380 | 1279 |
| 41717668636 | `scripts/check_consumer_sync_drift.py` | 633 | 296 | 929 |
| 41717668636 | `tools/llm_provider.py` | 447 | 114 | 561 |

Repository-wide denominators remain 69,223 / 69,241 / 69,241 as recorded above;
they are distinct from these per-target denominators. Python 3.13 has no
coverage.json in the historical artifacts and no missing-unit comparison is
claimed for it.

### Positional script results and behavioral interpretation

Extracted `target_missing.py` unchanged from #4431 head `69e5b6d6` and ran,
for each run ID, the positional invocation:

```sh
/opt/anaconda3/bin/python3 /tmp/w4495/target_missing.py /tmp/w4495/RUN/runtimes/3.14/coverage.json
```

All three invocations exited 0. Full printed missing line/branch lists follow;
empty lists mean no uncovered units of that kind.

Run 41557902073:

```text
TOTAL 62986 69223 90.98998887652948
scripts/aggregate_agent_metrics.py 0 + 3 = 3 [] [[492, 481], [954, 910], [1011, 996]]
scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []
tools/llm_provider.py 77 + 27 = 104 [48, 49, 204, 205, 209, 211, 212, 213, 265, 270, 292, 298, 299, 317, 318, 319, 320, 321, 349, 350, 351, 352, 353, 355, 356, 357, 358, 359, 360, 376, 385, 386, 387, 430, 436, 437, 456, 460, 469, 470, 481, 485, 614, 615, 616, 625, 666, 667, 668, 690, 691, 692, 703, 725, 726, 727, 728, 729, 732, 884, 885, 886, 934, 971, 987, 1003, 1018, 1043, 1048, 1054, 1055, 1058, 1059, 1060, 1061, 1065, 1066] [[119, 131], [203, 204], [315, 317], [356, 357], [356, 359], [375, 376], [424, 430], [440, 451], [451, 456], [465, 469], [480, 481], [622, 625], [700, 703], [727, 728], [727, 729], [884, 885], [884, 886], [932, 934], [970, 971], [986, 987], [1017, 1018], [1042, 1043], [1047, 1048], [1054, 1055], [1054, 1058], [1060, 1061], [1060, 1065]]
TARGET_MISSING 107
```

Run 41668857273:

```text
TOTAL 63040 69241 91.04432344997906
scripts/aggregate_agent_metrics.py 0 + 3 = 3 [] [[492, 481], [954, 910], [1011, 996]]
scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []
tools/llm_provider.py 54 + 16 = 70 [48, 49, 204, 205, 209, 211, 212, 213, 265, 270, 292, 298, 299, 317, 318, 319, 320, 321, 349, 350, 351, 352, 353, 355, 356, 357, 358, 359, 360, 376, 385, 386, 387, 614, 615, 616, 625, 666, 667, 668, 690, 691, 692, 703, 728, 886, 934, 971, 987, 1003, 1018, 1043, 1065, 1066] [[119, 131], [203, 204], [315, 317], [356, 357], [356, 359], [375, 376], [622, 625], [700, 703], [727, 728], [884, 886], [932, 934], [970, 971], [986, 987], [1017, 1018], [1042, 1043], [1060, 1065]]
TARGET_MISSING 73
```

Run 41717668636:

```text
TOTAL 63110 69241 91.14541962132263
scripts/aggregate_agent_metrics.py 0 + 0 = 0 [] []
scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []
tools/llm_provider.py 3 + 0 = 3 [265, 270, 292] []
TARGET_MISSING 3
```

The aggregate baseline branches cover skipping a trace-list item without an ID
or URL (492→481), ignoring an unknown step success value (954→910), and
ignoring missing/non-list update targets (1011→996). Both baselines miss those
three branches; the measured candidate closes them. Sync drift has no missing
units in any of these measurements.

Provider baseline misses include registry import fallback, trace ID extraction
and exception handling, capability inspection/signature fallback, absent or
unconfigured clients, provider request/error paths, confidence normalization,
fallback-chain naming/retry/error handling, subscription availability, and
forced-provider selection. The second baseline covers confidence normalization
and some provider/factory branches that the first misses. The third measurement
closes all listed provider branches and all statements except the three empty
abstract bodies discussed above. These are coverage observations, not proof
that every possible provider behavior is tested.

### Mutation receipt correction and owner handoff

Inspected all 27 original JSON receipts at `69e5b6d6`: 3 aggregate and 24 provider
mutation operators, including 22a/22b and 23a/23b/23c. Every receipt reports
red_exit=1, green_exit=0, proof_ok=true, and equal before/restored SHA256.
These are historical receipt readbacks, not 27 fresh mutation executions in
this continuation. The earlier count of 24 confused numbered groups with
operators. The 24 new provider test methods are also not an operator count.
Mutation 09's recorded AssertionError remains the demonstrated fallback failure.

[Existing-owner handoff on #4431](https://github.com/stranske/Workflows/pull/4431#issuecomment-6699801278)
contains a minimal proposed repair, verified only in a disposable archive of
`69e5b6d6cd3fb154be29890f2ae212772de8ce45`. No takeover or dependency push occurred.
The injected partial-write check failed on the original driver (1 failed,
1 passed in 0.21s); moving the write into try/finally restored original bytes
(2 passed in 0.55s). The second check verifies subprocess argv uses
sys.executable. Local interpreter paths happen to match on this machine;
portability follows from the argv implementation, not a missing-Anaconda run.

With `WORKFLOWS_ANALYSIS_CLI=codex`, the named forced-provider test failed with
actual SubscriptionCLIProvider (1 failed in 0.40s); adding monkeypatch.delenv
for that variable passed (1 passed in 0.35s). Neither this temporary patch nor
its test results constitutes reviewed dependency delivery. Original receipts
were preserved. Any owner rerun must use a separate output directory.

### Remaining integration boundary

`gh pr view 4431 --repo stranske/Workflows --json state,headRefOid,mergeCommit,statusCheckRollup`
on 2026-11-06 reports OPEN, head `69e5b6d6cd3fb154be29890f2ae212772de8ce45`,
mergeCommit null. All five dependency review threads remain unresolved. Blocking:
undelivered reviewed dependency. Drainable: existing owner applies the verified
repairs, supplies final reviewed checkout/base-bound hosted pytest/coverage,
and obtains normal thread dispositions and guarded merge. No lock is released
or merge gate bypassed by this handoff.

Final integrated revision, focused-command exit/output, final coverage, merge
commit, and `git merge-base --is-ancestor <mergeCommit> origin/main` are **UNMET**;
there is no merge commit on which to run the ancestry check. #4495 must remain
open until those observations exist. Historical successful checks do not close
this gap, and the pending final-head coverage finding on #4431 stays open.

### Current #4495 focused check (candidate only)

While this continuation prepared evidence, the hosted writer pushed
`ab8cee5b4f70f84d92dd661e94def449a72fc220` to the existing branch (provider
fallback fix, mirrored template, and focused regression tests). Its trusted
runner completion receipt for workflow attempt `stranske/Workflows:42319635424:1`
reports completed and observed head `ab8cee5b4f70f84d92dd661e94def449a72fc220`.
The exact receipt is read-only authority; no reservation was released here.
After observing the completed writer, this checkout fast-forwarded to that
commit; this continuation preserved its changes. Git emitted a packed-refs.lock
permission warning during the fast-forward; HEAD and changed files were then
read back rather than inferring failure or removing locks.

The command in this continuation's acceptance section ran on that exact code
revision, with the documentation corrections uncommitted. Exit status 0:

```text
platform darwin -- Python 3.12.2, pytest-9.1.1
collected 243 items
============================= 243 passed in 1.05s ==============================
```

This is the owner's selected local interpreter, not hosted Python 3.13/3.14.
It is a current-branch focused check, not the requested post-#4431-integration
acceptance. The 243 versus historical candidate 268 count reflects different
candidate test trees and does not establish loss from an integrated delivery.

### Additional current-candidate hosted evidence

A later readback located [Gate 41720166203](https://github.com/stranske/Workflows/actions/runs/41720166203),
whose API head is the current #4431 candidate
`69e5b6d6cd3fb154be29890f2ae212772de8ce45`. Both Python job logs print tested
checkout `d3997d8478a07a9a2d5ba98cb761a8717fe4494c`, base
`2bd1aa094698d3e9f2ce91f754f6b00fb748a52d`. Git commit parents confirm that
base/head pair. The three target blob IDs match the candidate head and the
41717668636 row above: aggregate `ff8693012c52ab0966d818557d396d83011ed4e5`,
sync drift `383a70446744e679bccbe66fb4f57c41f4933b5a`, provider
`96d848a4385ed7299cd858aa10774d6f0476f129`.

Hosted logs (both jobs SUCCESS) print:

```text
Python 3.13: 50373 passed, 27 skipped, 3 xfailed in 651.12s (0:10:51)
Python 3.14: 50373 passed, 27 skipped, 3 xfailed in 430.57s (0:07:10)
```

Downloaded artifacts separately from the earlier runs. The positional script
exits 0 on this run's Python 3.14 coverage.json:

```text
TOTAL 63110 69241 91.14541962132263
scripts/aggregate_agent_metrics.py 0 + 0 = 0 [] []
scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []
tools/llm_provider.py 3 + 0 = 3 [265, 270, 292] []
TARGET_MISSING 3
```

Per-file statement/branch denominators are respectively 899/380, 633/296,
447/114. The 3.14 summary.json's 92.57 percent disagrees with the raw
coverage.json total of 91.14541962132263; the raw counters above are used,
not that summary percentage. Python 3.13's separately downloaded artifact
reports coverage_json=false and coverage_xml=false and contains no
coverage.json. Its runtime coverage discrepancy remains explicit.

This supplies hosted pytest and raw coverage for the **current** candidate,
correcting the earlier stage's lack of current-head artifact evidence. It is
not acceptance for future owner repairs, the final integrated tree, or #4495's
current tree. The restoration and environment-isolation fixes still require
owner application and new final-reviewed-tree evidence before delivery.

## Fresh mutation reproduction (2026-11-07)

Readback 2026-11-07: #4431 is still OPEN, head
`69e5b6d6cd3fb154be29890f2ae212772de8ce45`, `mergeCommit: null`, `isDraft=false`.

Reproduced all 27 break-and-revert operators from `mutate.py` in a disposable
`git worktree` of that exact head (removed afterwards; no tracked file changed,
original receipts in #4431 untouched). Only `PY` was rewritten to the local
`python3` (3.14.10), output went to a separate directory, and
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` was needed because the installed `langsmith`
pytest plugin fails to import on this runner's Python 3.14.10 (without it every
run exits 3 with a plugin load error — an environment failure, discarded, not
mutation evidence).

- Result: 27/27 `proof_ok`: red exit 1 with `FAILED`, green exit 0 after
  restoration, `sha256_before == sha256_restored`.
- Nodes and hashes match the original receipts one-for-one (same 27 ids, same
  node ids, same pre-mutation source hashes).
- No red run is a collection error. Red failures are assertion/behavior
  failures (e.g. 09: `assert True is False`; 15/18: `DID NOT RAISE`; 19/22a/22b:
  call_count `2 == 1`; 13: expected call not found) except 14, where the mutated
  code raises `AttributeError: 'NoneType' object has no attribute 'invoke'` at
  runtime inside the exercised function.
- `required-tests.txt` records the 268-test focused command at the candidate;
  not re-run against #4431's head here.

The mutation-receipt task is satisfied for the candidate head
`69e5b6d6cd3fb154be29890f2ae212772de8ce45` (under `docs/evidence/issue-4019/r3/mutations/`,
where e.g. `04-red.txt` fails at `tests/tools/test_llm_provider.py:2154` prior to #4495's
24-line regression addition) and for the post-#4495 integrated tree
`c1f18728c6b215fa7a66353b311fa12277074437` / cherry-pick `7ba92707` (under
`docs/evidence/issue-4019/r3/integration-rerun/mutations/`, where `04-red.txt` fails at
`tests/tools/test_llm_provider.py:2178`). Integration
(merge commit, final focused pytest, ancestry check) remains UNMET until #4431
merges.

## Task 1 re-read (2026-11-07)

- `gh pr view 4431 --repo stranske/Workflows --json state,headRefOid,mergeCommit,...`
  re-run on 2026-11-07: state OPEN, head `69e5b6d6cd3fb154be29890f2ae212772de8ce45`
  (unchanged since 2026-11-06), `mergeCommit: null`, `isDraft=false`,
  mergeable MERGEABLE, `reviewDecision` empty (no review recorded).
- #4431 is still not merged, so its results remain undelivered on main and the
  merge-dependent acceptance criteria stay open. Merging is an outward-facing
  action that this run does not take without explicit authorization.

## Task 1 record (2026-11-07)

- Checked head: `69e5b6d6cd3fb154be29890f2ae212772de8ce45`; acceptance date
  2026-11-07; state OPEN, `mergeCommit: null`, `isDraft=false`, MERGEABLE,
  `reviewDecision` empty (re-read via `gh pr view 4431`).
- `docs/AGENT_ISSUE_FORMAT.md` does not exist on this branch; the only copy is
  the consumer template `templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`,
  which is the one inspected.
- `docs/evidence/issue-4019/r3/acceptance.md` exists only on #4431's branch
  (not on this branch), so this record lives in `acceptance-integration.md`.
  It should be reconciled once #4431 merges. Merge remains unauthorized here.


## #4433 remainder acceptance recorded before code (2026-11-06 CST)

Check time: 2026-11-07T03:36:40Z. Outcome 1 is the delivered integration's
`TARGET_MISSING <= 5` from identified raw hosted Python 3.14 coverage, with each
residual explained; focused pytest and both hosted runtime jobs must pass.
Command: `/opt/anaconda3/bin/python3 docs/evidence/issue-4019/r3/target_missing.py <artifact>/runtimes/3.14/coverage.json`.
Focused command: `/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_aggregate_agent_metrics.py tests/scripts/test_check_consumer_sync_drift.py tests/tools/test_llm_provider.py`.
Current outcome: UNKNOWN; integration is not delivered. Stop rule: two failures
at one step or 60 minutes from 2026-11-07T03:36:40Z, whichever occurs first.
First broken step must be reported; no next repair is authorized by elapsed time.
Blocking/drainable: no integration result yet / integrate the named immutable
#4431 payload under #4433's existing claim and run focused validation plus hosted CI.
Original #4431 owner's dispatch is terminal with explicit released:true; no
#4019/#4431 local claim exists. Coordination notice could not be posted: connector approval policy is never.
The original owner is terminal; its source branch/worktree remain untouched.
Only closer-r1/issue-4433 exists among closer*/issue-4433 branches; it equals
current origin/main 0fb506e6ab16f1b4105a587021d28d60c0f6eb8b. Nothing to recover
from another local #4433 branch; nothing discarded.

## Current integration status (supersedes historical open-#4495 statements above)

#4495 merged as `0fb506e6ab16f1b4105a587021d28d60c0f6eb8b`, current
`origin/main` at the start of this run. Its production/template fix and focused
regression are retained byte-for-byte; this integration changes no production
source, dependency pins, or existing historical receipts. The payload is the
three aggregate tests, remaining provider tests, and r3 evidence from #4431
head `69e5b6d6cd3fb154be29890f2ae212772de8ce45`. No earlier tests were removed.

The original #4431 owner's terminal dispatch and released claim were read; the
source branch/worktree are untouched. An attempted coordination comment was
rejected by connector approval policy `never`, so no remote handoff was posted.
Its five unresolved review findings are accounted for here: active interpreter
and protected write in mutate.py, partial-write/interpreter regressions,
forced-provider environment isolation, portable documentation, and explicit
final-head acceptance status. Its threads are not resolved by this integration.

Reruns are separate in `integration-rerun/`; original `mutations/` receipts
remain byte-identical to #4431. `driver-before.txt` records two behavioral
assertion failures; `forced-before.txt` records the actual SubscriptionCLIProvider
mismatch. Deliberate failing controls are expected evidence, not failed repair
attempts. After files are corrected, the same commands are rerun.

Final-head hosted Python 3.13/3.14 jobs, final raw coverage residuals, merge
commit, main ancestry, and delivered-revision focused pytest remain PENDING.
Historical counts above are not relabeled as current integration results.
The historical 3.13 artifacts lacked coverage.json; a new artifact inventory
must confirm whether that is still true. Historical summary.json percentages
disagreed with raw coverage counters; use raw counters and report separately.

Local integrated validation: 269 passed in 0.73s; driver regressions 2 passed
in 0.20s; forced-provider test with CLI=codex initially set 1 passed in 0.23s.
Fresh mutation reproduction: 27/27 behavioral red -> restored green; every
source digest restored, no collection-error substitutes. Retention verification
confirms 55 original mutation files unchanged and both provider production
copies plus the sync-drift tests identical to current main. See
`integration-rerun/retention.json` and separate raw outputs.


## Integrated-tree hosted checkpoint (2026-11-06 CST)

Outcome 1: `TARGET_MISSING 3` at integration head
`c4c91e4c91e3860c3519eb8bc61c7943b7cd8c5b`, base
`0fb506e6ab16f1b4105a587021d28d60c0f6eb8b`.
[Gate 42335283865](https://github.com/stranske/Workflows/actions/runs/42335283865)
tested synthetic merge `5acad2470870e89618f92f7e58fe7c39d15dda21`; its
parents are that base and head, and `git diff HEAD 5acad247` was empty.
This whole-tree comparison is stronger than selected-blob identity alone.
Python 3.13 job 128291070061: 50292 passed, 27 skipped, 3 xfailed, 504.50s.
Python 3.14 job 128291069864: 50292 passed, 27 skipped, 3 xfailed, 552.87s.

Downloaded raw artifacts are separately identified and digest-verified in
`integration-rerun/green-3.13-manifest.json` and `green-3.14-manifest.json`.
3.14 artifact 13559676412 prints:

```text
TOTAL 63868 70054 91.169669112399
scripts/aggregate_agent_metrics.py 0 + 0 = 0 [] []
scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []
tools/llm_provider.py 3 + 0 = 3 [265, 270, 292] []
TARGET_MISSING 3
```

All residuals: provider lines 265, 270, 292 are abstract-method `pass` bodies
(`name`, `is_available`, `analyze_completion`); zero residual branches and no
other target residuals. We retain these in coverage rather than adding padding.
The 3.14 summary percentage is 92.60, distinct from raw blended 91.169669112399;
raw counters above are authoritative for this criterion.
3.13 artifact 13558944592 contains JUnit but no coverage.json or coverage.xml;
its summary marks coverage minimum skipped. No 3.13 uncovered count is claimed.

The freshly downloaded historical baseline 41668857273 has distinct artifacts
13248466557 (3.14) and 13248291385 (3.13), identified by the baseline manifests.
`target_missing.py` prints raw TOTAL 63040/69241 (91.04432344997906), target
missing 73 (aggregate 0+3, sync 0+0, provider 54+16). Its summary reports 92.47.
Its 3.13 artifact also lacks coverage JSON. Repository denominators changed
69241 -> 70054 between historical baseline and this current-main integration;
no causal repository-percentage gain is attributed to this test-only change.
The historical round's whole target list contained only 107 units, so 180 was
not reachable within scope; the three behaviorless residual lines explain
the remaining target shortfall.

This documentation reconciliation changes the PR head. The resulting final-head
Gate and raw-artifact confirmation, merge commit, main ancestry, and delivered
focused rerun must be recorded in the final acceptance section of
[integration PR #4516](https://github.com/stranske/Workflows/pull/4516).
They remain pending at this checkpoint; no parent-head result is relabeled.
The README function count is corrected to 24 (3 aggregate, 21 provider);
original receipts remain unchanged. Four optional review items are recorded
in `integration-rerun/review-dispositions.md`, per the owner's narrow scope.

## #4523 cherry-pick integration and verification (2026-11-12 UTC)

- **PR #4516 state**: `CLOSED` unmerged (`mergeCommit: null`) on 2026-11-09; branch
  `closer-r1/issue-4433` retained at final head
  `59c11ae720b4b57c406a5da54c1225af8b483f0d`.
- **Cherry-pick path (PR #4674, `gemini/issue-4523`)**: Cherry-picked the four commits
  from `closer-r1/issue-4433` (`c1f18728`, `c4c91e4c`, `b3db3da3`, `59c11ae7`) onto
  `gemini/issue-4523` (branched from `origin/main`
  `650ccf6d98a25b8a17a1e031880e4091f65b9843`), delivering:
  - `tests/scripts/test_aggregate_agent_metrics.py`
  - `tests/tools/test_llm_provider.py`
  - `tests/tools/test_issue_4019_mutation_driver.py`
  - `docs/evidence/issue-4019/r3/mutate.py`
  - `docs/evidence/issue-4019/r3/target_missing.py`
  - `docs/evidence/issue-4019/r3/mutations/mutation-receipts.json` (27 verified receipts
    with `proof_ok: true`, `red_exit == 1`, `green_exit == 0`, and matching
    `sha256_before == sha256_restored`; annotated with
    `"revision": "69e5b6d6cd3fb154be29890f2ae212772de8ce45"` and `# revision:` transcript
    headers from #4431 candidate head `69e5b6d6cd3fb154be29890f2ae212772de8ce45`,
    annotated SHA-256 `ad3c82caf1ad3ab834d6a2c4bbc2b16e13a472619ab5728450fc9ad983421166`
    and pre-annotation SHA-256 `9658a61c23ebf1c7aa23d3d8fddadac11ba46d70a721334981dbd25f849f48af`,
    where `mutations/04-red.txt` reports `tests/tools/test_llm_provider.py:2154`, alongside
    the post-#4495 rerun annotated with
    `"revision": "c1f18728c6b215fa7a66353b311fa12277074437"` / `7ba92707` in
    `docs/evidence/issue-4019/r3/integration-rerun/mutations/`, where
    `integration-rerun/mutations/04-red.txt` reports `tests/tools/test_llm_provider.py:2178`).
- **Merged `origin/main` ancestry**:
  - PR #4495 merge commit `0fb506e6ab16f1b4105a587021d28d60c0f6eb8b`:
    `git merge-base --is-ancestor 0fb506e6ab16f1b4105a587021d28d60c0f6eb8b origin/main`
    exits `0`.
  - PR #4602 merge commit `97532090dc5836381564f565bb056d9dcd91cfe1` (carried the 3
    `test_aggregate_agent_metrics.py` tests and 16 `test_llm_provider.py` fallback
    tests onto `main`):
    `git merge-base --is-ancestor 97532090dc5836381564f565bb056d9dcd91cfe1 origin/main`
    exits `0`.
  - Current `origin/main` base `650ccf6d98a25b8a17a1e031880e4091f65b9843`:
    `git merge-base --is-ancestor 650ccf6d98a25b8a17a1e031880e4091f65b9843 origin/main`
    exits `0`.
- **Focused pytest on integrated revision**:
  ```text
  $ python3 -m pytest tests/scripts/test_aggregate_agent_metrics.py tests/scripts/test_check_consumer_sync_drift.py tests/tools/test_llm_provider.py
  ============================= 290 passed in 3.39s ==============================
  exit=0
  ```
  Driver and helper regression suite (`tests/tools/test_issue_4019_mutation_driver.py`)
  passes (`12 passed`, covering partial-write restoration, `get_revision()` git SHA and
  fallback handling, active interpreter selection, `TimeoutExpired` string and bytes/None
  handling, empty subprocess output fallback, runtime occurrence-count verification,
  successful red-to-green mutation execution with revision headers, timeout loop
  termination, `mutate.cli()` argument validation, `target_missing.py` missing-unit
  summation and CLI/zero-denominator guards, and the 27-receipt identity, operator,
  revision, transcript header, and live-source digest inventory),
  and fresh `mutate.py` execution against a temporary output directory confirms
  `27/27 proof_ok`.
- **Final-head hosted Gate coverage (`42342628461` on `59c11ae720b4b57c406a5da54c1225af8b483f0d`, `43166948933` on `3ccdb9bb7f0b162e0ea0ea9e017acb0c0a8396f4`, `43170114463` on `6f3df09f9719eca8ba9d73b2fbac84566f0143fa`, `43172506542` on `ade144b93e473e8017409e5ca5603a2f3c26a43e`, and `43175869464` on `37f7e8cd1a6a8861860ce575e68d670603831892`)**:
  - [Gate 42342628461](https://github.com/stranske/Workflows/actions/runs/42342628461):
    `conclusion: success` (Python 3.13 job `128313615973` `success`; Python 3.14 job
    `128313616019` `success`).
  - Executed `python3 docs/evidence/issue-4019/r3/target_missing.py` against downloaded
    hosted Python 3.14 Gate coverage artifact `gate-coverage-3.14-1` (artifact ID
    `13562643111`):
    ```text
    TOTAL 63868 70054 91.169669112399
    scripts/aggregate_agent_metrics.py 0 + 0 = 0 [] []
    scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []
    tools/llm_provider.py 3 + 0 = 3 [265, 270, 292] []
    TARGET_MISSING 3
    ```
  - [Gate 43166948933](https://github.com/stranske/Workflows/actions/runs/43166948933)
    on PR #4674 head `3ccdb9bb7f0b162e0ea0ea9e017acb0c0a8396f4`: `conclusion: success`
    (Python 3.13 job `131011150858` `success`; Python 3.14 job `131011150993` `success`).
    Executed `python3 docs/evidence/issue-4019/r3/target_missing.py` against downloaded
    hosted Python 3.14 Gate coverage artifact `gate-coverage-3.14-1` (artifact ID
    `13920802310`, `sha256:9555a25ab5fe2ba25aca75c5640c29cb414f7944fa51e67025fa5ebfb618493e`):
    ```text
    TOTAL 68032 74698 91.07606629360893
    scripts/aggregate_agent_metrics.py 0 + 0 = 0 [] []
    scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []
    tools/llm_provider.py 3 + 0 = 3 [265, 270, 292] []
    TARGET_MISSING 3
    ```
  - [Gate 43170114463](https://github.com/stranske/Workflows/actions/runs/43170114463)
    on PR #4674 head `6f3df09f9719eca8ba9d73b2fbac84566f0143fa`: `conclusion: success`
    (Python 3.13 job `131021375149` `success`; Python 3.14 job `131021375037` `success`).
    Executed `python3 docs/evidence/issue-4019/r3/target_missing.py` against downloaded
    hosted Python 3.14 Gate coverage artifact `gate-coverage-3.14-1` (artifact ID
    `13921568022`, `sha256:565a45c357a8a1defb4f1d03d6d5b89a327af76163a1fb7dc6433a1a93372e17`,
    `coverage.json` `sha256:a6cc9fdf4e71f233e2a37e156cba0a57de3025d093fecac26c0f8de2df320090`):
    ```text
    TOTAL 68030 74698 91.07338884575223
    scripts/aggregate_agent_metrics.py 0 + 0 = 0 [] []
    scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []
    tools/llm_provider.py 3 + 0 = 3 [265, 270, 292] []
    TARGET_MISSING 3
    ```
  - [Gate 43172506542](https://github.com/stranske/Workflows/actions/runs/43172506542)
    on PR #4674 head `ade144b93e473e8017409e5ca5603a2f3c26a43e`: `conclusion: success`
    (Python 3.13 job `131029172202` `success`; Python 3.14 job `131029172220` `success`).
    Executed `python3 docs/evidence/issue-4019/r3/target_missing.py` against downloaded
    hosted Python 3.14 Gate coverage artifact `gate-coverage-3.14-1` (artifact ID
    `13923071251`, `sha256:b0f28bd8a5f14a5cc44b4ff48027b24a8c8df1ca5e9bbed0bc30a6dabdbb2ceb`,
    `coverage.json` `sha256:2b3e5adc7e676033105bef33058ef7aaab024e329e865300479fcabcc6993511`):
    ```text
    TOTAL 68032 74698 91.07606629360893
    scripts/aggregate_agent_metrics.py 0 + 0 = 0 [] []
    scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []
    tools/llm_provider.py 3 + 0 = 3 [265, 270, 292] []
    TARGET_MISSING 3
    ```
  - [Gate 43175869464](https://github.com/stranske/Workflows/actions/runs/43175869464)
    on PR #4674 head `37f7e8cd1a6a8861860ce575e68d670603831892`: `conclusion: success`
    (Python 3.13 job `131040182178` `success`; Python 3.14 job `131040182265` `success`).
    Executed `python3 docs/evidence/issue-4019/r3/target_missing.py` against downloaded
    hosted Python 3.14 Gate coverage artifact `gate-coverage-3.14-1` (artifact ID
    `13924153688`, `sha256:68373d0ff09b8daf872fe5f0134e5a3517ed5373564b4642debb3035d5035901`,
    `coverage.json` `sha256:a75c514d635eeb60edf819714501bbd03ad4a957a28a2edbae12615d6d7f5cd1`):
    ```text
    TOTAL 68032 74698 91.07606629360893
    scripts/aggregate_agent_metrics.py 0 + 0 = 0 [] []
    scripts/check_consumer_sync_drift.py 0 + 0 = 0 [] []
    tools/llm_provider.py 3 + 0 = 3 [265, 270, 292] []
    TARGET_MISSING 3
    ```
    confirming `TARGET_MISSING` equals 3 statements in `tools/llm_provider.py` (lines
    265, 270, 292).



