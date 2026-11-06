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
