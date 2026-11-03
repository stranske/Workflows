# Round 3 lane B closer evidence recovery (#4018)

Checked 2026-11-03. Refs #4018. This documents tests already delivered by
[#4023](https://github.com/stranske/Workflows/pull/4023); it does not replace
that implementation. No production or test files are changed by this repair.
The provisioned branch `closer-r2/issue-4018` started clean at current `main`
(including squash `c468727c3`). Local `closer/issue-4018` had no commits absent
from `main`; nothing was merged or discarded.

**Real-input acceptance outcome:** all four tests added in #4023 fail on a
deliberate production mutation and pass after `git checkout --` restoration;
recovered Gate CI pytest success for #4023 is recorded below; pre/post #4023
target miss counts were replayed from archived trees.

**Focused validation command (named in repair brief):**

```bash
/opt/anaconda3/bin/python3 -m pytest -q \
  tests/scripts/test_issue_formatter.py \
  tests/tools/test_ci_failure_triage.py
```

**Check date:** 2026-11-03. **Stop rule:** two failed acceptance attempts at a
required evidence step, or 60 minutes elapsed.

**Repository-selected interpreter:** no `.venv` in the provisioned worktree.
Per owner runtime policy and prior #4023/#4161 recovery, local runs used
`/opt/anaconda3/bin/python3` (Conda Python 3.12.2, pytest 9.1.1, coverage
7.16.2). This differs from hosted Gate (Linux, Python 3.14). Recovered hosted
CI establishes supported-runtime success; local replay is for deltas and
break/revert only.

## Gate acceptance (recovered CI, not re-run locally)

Gate pytest step from
[run 39033148390](https://github.com/stranske/Workflows/actions/runs/39033148390)
(PRs #4023 synthetic merge):

| Python job | Result |
| --- | --- |
| 3.13 | `50977 passed, 25 skipped, 3 xfailed in 474.45s` |
| 3.14 | `50977 passed, 25 skipped, 3 xfailed in 506.44s` |

Gate-equivalent command (from `.github/workflows/reusable-10-ci-python.yml`,
`Pytest (unit tests with coverage)`):

```bash
python -m pytest -m 'not quarantine and not slow' \
  --cov --cov-config=pyproject.toml \
  --cov-report=xml:coverage.xml \
  --cov-report=term-missing \
  --cov-report=json:coverage.json \
  -n auto --dist load tests/
```

That whole-suite command was **not** executed locally (machine policy: do not
starve other agents). The table above is the authoritative passing CI record.

## Target ranking (issue #4018, historical)

Sort order: escaped-defect signals, then churn, then uncovered
statement+branch mass (Orchestrator coverage-autopilot ranking embedded in the
issue body). File size was not the selection rule.

| Rank | Target | Escaped-defect signals | Churn | Issue CI uncovered units |
| ---: | --- | ---: | ---: | ---: |
| 1 | `scripts/langchain/issue_formatter.py` | 3 | 6 | 35 |
| 2 | `tools/ci_failure_triage.py` | 3 | 3 | 171 |

Combined issue baseline: **206** units across both targets.

## Replayed pre/post #4023 coverage (like-for-like, not whole-suite Gate)

Trees extracted with `git archive` under `/tmp/wf4018-recovery/{parent,merged}`:

- Parent (pre-#4023): `5dee9a65400fd2f6c9a2692a6069e4d20c6109db`
- Merged #4023: `c468727c3b961de849d9056517bec81278f72768`

Replay command (both trees; same markers and cov config as Gate, **only** the
two lane test modules — not a whole-suite Gate rerun):

```bash
/opt/anaconda3/bin/python3 -m pytest -m 'not quarantine and not slow' \
  --cov --cov-config=pyproject.toml \
  --cov-report=json:/tmp/wf4018-recovery/out/LABEL-coverage.json \
  --cov-report=term-missing -q \
  tests/scripts/test_issue_formatter.py \
  tests/tools/test_ci_failure_triage.py
```

Results: parent **64 passed** in 29.32s; merged **68 passed** in 26.96s.

Count **missing statements + missing branch outcomes** (len of `missing_lines`
and `missing_branches` in coverage JSON), not `Miss + BrPart`:

| Target | Parent missed stmts / branches | Merged missed stmts / branches | Reduction |
| --- | ---: | ---: | ---: |
| `scripts/langchain/issue_formatter.py` | 16 / 19 (35) | 12 / 17 (29) | **6** |
| `tools/ci_failure_triage.py` | 114 / 59 (173) | 1 / 5 (6) | **167** |
| **Total** | **208** | **35** | **173** |

**Chunk attribution:** #4023’s four new tests account for **173** covered units
in this like-for-like replay (7 below the issue’s “about 180” bundle target).
The gap is expected: `issue_formatter.py` was already heavily exercised by its
existing focused module before #4023; the issue’s **35** figure is whole-CI,
while this replay’s parent baseline for that file is also **35** — the new test
only closes **6** additional units here. No further tests were added in this
repair PR because production code and tests on `main` already include #4023;
adding tests now would rewrite merged work rather than finish missing evidence.

**Remaining merged-replay limits (`tools/ci_failure_triage.py`, 6 units):**
line 232 and branch gaps around LLM client import failure paths and CLI
`main()` edges that require live `langchain_openai` import failures or the
`if __name__ == "__main__"` entry (excluded from coverage by repository policy
in `pyproject.toml` `exclude_also`). Meaningful additional coverage without
policy changes would be low value.

Raw JSON and break/revert transcripts: `proof.tar.gz` in this directory.

## Break-and-revert proof (all four #4023 tests)

| Test | Break | Named assertion failure | Revert pass |
| --- | --- | --- | --- |
| `test_formatter_helpers_handle_missing_prompt_tasks_and_cli_input` | Disabled nested-task `indent` guard in `_extract_tasks_from_formatted` | `AssertionError: assert ['Keep this', 'nested'] == ['Keep this']` | `1 passed` |
| `test_triage_detects_patterns_deduplicates_paths_and_formats_reports` | Renamed mypy pattern `error_type` to `not_mypy` | `AssertionError: assert ['not_mypy', ...] == ['mypy', ...]` | `1 passed` |
| `test_triage_helpers_handle_unknown_and_malformed_llm_data` | `_format_suggested_fix` empty-file placeholder → `WRONG` | `AssertionError: assert 'fix WRONG' == 'fix the reported files'` | `1 passed` |
| `test_llm_prompt_client_and_cli_paths` | Prefixed CLI empty output with ` BROKEN` | `AssertionError` on `capsys.readouterr().out` | `1 passed` |

Full terminal captures are in `proof.tar.gz` (`break-revert/*.txt`).
