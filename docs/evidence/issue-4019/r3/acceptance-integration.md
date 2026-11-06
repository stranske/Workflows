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
were not measured by a Gate coverage run in this task.

Behavioral explanation: these three lines are `pass` statements in abstract methods
of the `LLMProvider` abstract base class (lines 265: `name` property, line 270: 
`is_available` method, line 292: `analyze_completion` method). Abstract methods cannot
be directly instantiated or called, so they are only covered when concrete
subclasses override them. The abstract base class itself is not exercised by tests
that instantiate concrete providers. This is a structural coverage gap, not a
behavioral one; the methods are intentionally unimplemented at this level.

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

24 mutation tests were executed against the exact delivery candidate:
- **Nodes**: 3 in `scripts/aggregate_agent_metrics.py`, 21 in `tools/llm_provider.py`
  (via `tests/tools/test_llm_provider.py::TestRemainingProviderPaths::` tests).
- **All receipts**: `proof_ok: true` (24/24).
- **Red exit**: All mutations caused test failures (exit code 1 with "FAILED" in output).
- **Green exit**: All restorations passed (exit code 0).
- **Byte restoration**: All SHA256 checks passed (`sha256_before == sha256_restored`).

Nodes and behavioral assertions:
- **aggregate_agent_metrics**: 3 mutations in conditional logic that is exercised
  by the added tests (test 01-03). Each mutation replaces a guard with an unconditional
  or inverted condition, causing the test to fail.
- **llm_provider**: 21 mutations covering:
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

## Task 5: Focused pytest execution on integrated revision

### Setup

- **Interpreter**: `/opt/anaconda3/bin/python3` (as specified in mutate.py and required-tests.txt)
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
- **Mutation evidence**: All 24 receipts validated against mutate.py and source;
  all behavioral assertion failures distinguished from collection errors; all byte
  restorations confirmed.
- **Coverage residuals**: Lines 265, 270, 292 in llm_provider.py are abstract method
  `pass` statements, structurally unavoidable in the base class; behavioral explanation
  provided.
- **Absent runtime coverage**: Python 3.13 coverage explicitly documented as not
  measured by Gate; 3.14 coverage complete at 91.15% with 3 statement residuals.
- **Focused pytest**: Passes on integrated revision with 268 tests.
- **Review and merge**: #4431 ready for normal review; hosted checks green; after
  merge, verify merge commit is ancestor of main.
