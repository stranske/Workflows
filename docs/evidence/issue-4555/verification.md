# Issue #4555: closer capacity fixture verification

Verified on 2026-11-08. The implementation belongs to Orchestrator and already
merged in [PR #1251](https://github.com/stranske/Orchestrator/pull/1251), commit
`f141cf330a4a303276e7b04d31bc9e3a73d77ca0`. No Workflows production change or
duplicate consumer repair is justified. The source owner's
[handoff](https://github.com/stranske/Workflows/issues/4555#issuecomment-6726070925)
explicitly requests regeneration without duplicating that repair.

## Root cause

The failing expression is `receipt["targets"]["a"]` in the test assertion, at
line 1569 of `tests/test_closer_pipeline.py` on the reported head
`7ba7006dc3243a7bf0221d709e4de5562c89f042`. The fixture allows only 0.06 seconds
of wall time. A scheduling pause before admission consumes this budget.
`src/closer_pipeline.py::_run_pipeline_impl` correctly returns
`reason="admission_deadline_expired"` and `targets={}` before creating state.
The test then assumes target `a` was admitted. This is a fixture timing defect;
the production deadline guard must remain intact.

The repaired fixture injects the same logical clock into deadline construction
and admission. It deliberately advances wall time across that deadline, retains
the original missing-target assertion, checks the worker-capacity evidence and
valid stop, then verifies a later invocation resamples positive capacity and
completes the target.

## Local verification

The named test does not exist in Workflows: running its requested node ID here
exits 4 with `file or directory not found`. Read-only GitHub retrieval populated
a disposable `/tmp/issue-4555-orchestrator` directory with the original test and
its real source dependencies. No generated sync branch was modified.

- [x] Reproduce the original named test's `KeyError: 'a'` by delaying
  `closer_resources.rollback_fence` by 0.1 seconds before admission. Without
  the injected pause the original named test passes. The full traceback is in
  [original-traceback.txt](original-traceback.txt).
- [x] Identify the lookup and distinguish the fixture defect from the valid
  production admission refusal.
- [x] Verify the existing source-owner repair: retrieve the repaired test and
  its real source dependencies at Orchestrator main
  `610d084bae028b6a8e3c215903e24b9c125cc212`; the named test passes.
- [x] Temporarily replace the repaired fixture's first injected logical clock
  with `time.time` in the disposable test. The same named test fails with
  `KeyError: 'a'`. Restore the file byte-for-byte in `finally`, then rerun:
  the named test passes. Retained outputs: [deliberate-break.txt](deliberate-break.txt)
  and [restored-pass.txt](restored-pass.txt).
- [x] Run six focused pytest admission/capacity tests: **6 passed**, 246 deselected.
- [x] Run the existing real-source Node regression:
  `node --test --test-isolation=none --test-reporter=tap tests/test_closer_pipeline_capacity_clock.js`:
  **6 passed**, including all three wall-clock negative controls and restored passes.

These pytest runs used `PYTHONPATH=/tmp/issue-4555-orchestrator/src`, `-c /dev/null`
to avoid applying Workflows' configuration to the disposable consumer files,
and `-m 'not slow'`. They do not establish a complete consumer checkout or a
full local repository-suite pass.

## Regenerated consumer check

Read-only GitHub connector verification confirms regenerated Orchestrator #1247
head `c0c5cb6aa8bf79aa855a54258c0ed423011cebeb` has successful CI run
[42518195788](https://github.com/stranske/Orchestrator/actions/runs/42518195788).
The exact named job
[verify.py aggregate + combined coverage](https://github.com/stranske/Orchestrator/actions/runs/42518195788/job/128847594079)
completed successfully. Its log reports **15042 passed, 0 failed**, 15075 collected,
141 combined instrumented processes, and 87.8% combined coverage.

The requested `gh run view` invocation cannot connect to `api.github.com` in
this sandbox; the connector supplies the independent readback above. The old
Evidence run remains a historical failure and is not the regenerated result.

- [ ] Establish full local repository-suite success.
- [ ] Observe a subsequent sync-core round explicitly clearing this finding.

The bounded local command
`timeout 300 python -m pytest tests/ -m 'not slow' -q -x` exited **124** after
300 seconds, at approximately 4% progress. There is no terminal pytest summary
and no full-suite pass. Its partial output is retained in
[workflows-suite.txt](workflows-suite.txt). No unrelated test or timeout change
was made to force acceptance.

No protected workflow was edited or triggered, no CI was retried, and no
consumer PR was edited. Workflows #4556 and Orchestrator #1247 were both
confirmed open and ready for review (`draft=false`). No new source commit is
claimed: the source repair is already merged in its owning repository.

Updating Workflows #4556's managed task block was attempted after verification.
The GitHub connector rejected the mutation: `MCP tool call requires approval,
but approval policy is never`. The prepared replacement body is retained at
`/tmp/issue-4555-reconciled-pr-body.md`. No remote checkbox update is claimed.
