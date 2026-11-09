# Issue #4555: closer capacity fixture verification

Verified on 2026-11-08. The implementation belongs to Orchestrator and already
merged in [PR #1251](https://github.com/stranske/Orchestrator/pull/1251), commit
`f141cf330a4a303276e7b04d31bc9e3a73d77ca0`. No Workflows production change or
duplicate consumer repair is justified. The source owner's
[handoff](https://github.com/stranske/Workflows/issues/4555#issuecomment-6726070925)
explicitly requests regeneration without duplicating that repair.

**PR Status Distinction**: 
- **Workflows PR #4556**: **Merged** at 2026-11-09T03:03:01Z (merge commit
  `cd30d3f58784ffcf759a0b8c65961ac0b2be407f`, head `d263beb62a38c0488027b64e470e02e09f46a6e3`).
  It delivered evidence and bookkeeping only, with no production code changes. Its merge closed #4555.
  It was open when the earlier sections were written.
- **Orchestrator PR #1247** (consumer/sync PR): **Merged** at 2026-11-08T20:49:16Z with successful CI (run 42518195788).

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
- [x] Run Orchestrator's existing real-source Node regression (the file lives in
  Orchestrator, not Workflows):
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

A later round confirmed this with the requested command:
`gh run view 42518195788 -R stranske/Orchestrator` reports conclusion `success`
on head `c0c5cb6aa8bf79aa855a54258c0ed423011cebeb`, and both
`verify.py aggregate + combined coverage` and
`verify.py aggregate in the flat exec-mirror shape` report `success`.
Orchestrator #1247 then merged at 2026-11-08T20:49:16Z. The old Evidence run
remains a historical failure and is not the regenerated result.

## Re-verification on Orchestrator main `fd139a1` (post-merge)

A fresh shallow clone of Orchestrator main
`fd139a1ab922252111b7e4376df1b3a3569637ae` in `/tmp` (not a Workflows file,
and not the sync branch):

- [x] `python -m pytest tests/test_closer_pipeline.py::test_capacity_is_read_fresh_and_zero_defers`:
  **1 passed**.
- [x] Deliberate break: line 1070 of the `run()` test helper was changed to
  ignore the injected `now` and build the deadline from `time.time`. This is
  the original behavior. The named test fails with `KeyError: 'a'` at
  `row = receipt["targets"]["a"]`. After `git checkout` restored the file
  (clean `git status`), the test passes again. Output is in
  [rerun-main-fd139a1.txt](rerun-main-fd139a1.txt).
- [x] `python -m pytest tests/test_closer_pipeline.py -m 'not slow'`: **252 passed**.
- [x] `node --test --test-isolation=none tests/test_closer_pipeline_capacity_clock.js`:
  **6 passed, 0 failed**.

Orchestrator's full aggregate suite was not run locally. The regenerated sync
PR's CI aggregate job (15042 passed, 0 failed) is the full-suite evidence.

## Still open (human/sync-core owned)

- [ ] Establish full local repository-suite success.
- [ ] Observe a subsequent sync-core round explicitly clearing this finding.
  #1247 has merged, so the finding can no longer reappear on that head. A
  sync-core comment confirming the clearance was not observed when this was
  written.

The bounded local command
`timeout 300 python -m pytest tests/ -m 'not slow' -q -x` exited **124** after
300 seconds, at approximately 4% progress. There is no terminal pytest summary
and no full-suite pass. Its partial output is retained in
[workflows-suite.txt](workflows-suite.txt). No unrelated test or timeout change
was made to force acceptance.

**Timeout Disclosure**: Local full repository-suite pass remains **unclaimed**. The timeout disclosure is preserved as evidence that the local-suite portion cannot be completed within 300 seconds.

No protected workflow was edited or triggered, no CI was retried, and no
consumer PR was edited. At that time Workflows #4556 and Orchestrator #1247 were both
confirmed open and ready for review (`draft=false`). Both have since merged (see the
closer repair section at the end). No new source commit is
claimed: the source repair is already merged in its owning repository.

Updating Workflows #4556's managed task block was attempted after verification.
The GitHub connector rejected the mutation: `MCP tool call requires approval,
but approval policy is never`. The prepared replacement body is retained at
`/tmp/issue-4555-reconciled-pr-body.md`. No remote checkbox update is claimed.

## Re-verification on Orchestrator main `69d32fa` (keepalive round 3)

Fresh shallow clone of Orchestrator main
`69d32fa9a5ca3a8058d37ba9ce75bf590a6495d5` in `/tmp` (disposable, not the sync
branch):

- [x] Named test: **1 passed**.
- [x] Deliberate break: the `run()` helper's `clock = kw.pop("now", time.time)`
  was replaced with `kw.pop("now", None); clock = time.time`, which restores the
  original wall-clock deadline. The named test fails with
  `KeyError: 'a'` at `tests/test_closer_pipeline.py:1586`. `git checkout`
  restored the file (`git status --short` empty) and the test passes again.
- [x] `gh run view 42518195788 -R stranske/Orchestrator` reports conclusion
  `success` on `c0c5cb6aa8bf79aa855a54258c0ed423011cebeb`. Both
  `verify.py aggregate + combined coverage` and
  `verify.py aggregate in the flat exec-mirror shape` report `success`.
- [ ] Sync-core clearance: no sync-core comment appeared on #4555 after
  Orchestrator #1247 merged at 2026-11-08T20:49:16Z. This stays human/sync-core
  owned.

The unchecked "Additional PR tasks" in Workflows #4556 repeat the original
task list with its sub-bullets split. The evidence above and in the sections
before it covers them. There is no Workflows source change to make: the
defect was in an Orchestrator-owned test fixture, which Orchestrator #1251
fixed in its owning repo. `scripts/sync_core_shipment_finding.py` here is a
one-off fingerprint check for #4508, not the classifier that produced this
finding.

## Continuation round (2026-11-09): completed checks vs. missing outcomes

Completed checks (observed this round):

- [x] `gh run view 42518195788 -R stranske/Orchestrator` re-read: conclusion
  `success`, event `pull_request`, branch `sync/workflows-delivery`, head
  `c0c5cb6aa8bf79aa855a54258c0ed423011cebeb`. Named jobs
  `verify.py aggregate + combined coverage` (job 128847594079) and
  `verify.py aggregate in the flat exec-mirror shape` (job 128847837873) both
  report `success`. All 12 shard jobs succeeded. `reconcile the collection floor
  (main only)` was skipped, as expected on a PR.
- [x] Review thread `PRRT_kwDOQprj9M61Dwgw` re-read: it is outdated. Ledger tasks
  08, 10, 13, 14 and 15 already carry `status: deferred` with notes, which is
  the change it asked for. No source repair was duplicated.

Missing outcomes (still unknown; the issue is **not** complete):

- [ ] **Local repository suite: unclaimed.** Orchestrator's configured test
  command is `python3 src/verify.py` (its CLAUDE.md says "Verify with
  `python3 src/verify.py`"; CI runs the same script in shards with
  `VERIFY_PYTEST_WORKERS=4`). One bounded attempt ran on a fresh, clean
  Orchestrator clone at `27266f8165064f88256ee2a97f99762db51f129a` (the merge
  commit of #1247). It used `/opt/anaconda3/bin/python3`, Python 3.12.2,
  because the canonical clone has no virtual environment. The command was
  `VERIFY_PYTEST_WORKERS=8 timeout 1500 /opt/anaconda3/bin/python3 src/verify.py`
  and it exited **124** after 1500 s. verify.py buffers pytest output until it
  finishes, so the killed run printed no terminal summary. The full record is
  in [orchestrator-local-suite.txt](orchestrator-local-suite.txt). A timeout is
  not a pass. The earlier
  `timeout 300 python -m pytest tests/ -m 'not slow' -q -x` record
  ([workflows-suite.txt](workflows-suite.txt)) does not name its repository or
  head, and it is not Orchestrator's configured command. It is kept as history
  only.
- [ ] **Subsequent sync-core classification: none found; still deferred.**
  Re-read on 2026-11-09: #4555's last comment is the auto-pilot handoff at
  2026-11-08T20:28:23Z. Nothing was posted after #1247 merged at 20:49:16Z, and
  none of its comments is a sync-core classification. Orchestrator #1247 has no
  comment after 19:30Z. No later `sync/workflows-delivery` PR exists after #1247.
  No Workflows issue created after #1247 merged references #1247 or #4555. No
  protected workflow was triggered.

The combined acceptance criterion ("passes on regenerated sync PR …; the
repository's test command passes locally") has its remote half observed and
its local half unclaimed. It must therefore stay unchecked.

## Closer repair round 1 (2026-11-09): lifecycle, sync-core receipt, local suite

### Lifecycle and review thread

- Workflows #4556 merged at 2026-11-09T03:03:01Z (`cd30d3f5`), and its merge closed
  #4555. Orchestrator #1251 merged at 2026-11-08T18:59:16Z (`f141cf33`).
  Orchestrator #1247 merged at 2026-11-08T20:49:16Z (`27266f81`, head `c0c5cb6a`).
- The #1251 `tests/test_closer_pipeline.py` diff was re-read. It monkeypatches
  `time.time` and wraps `run_pipeline` so that wall time crosses the 0.06 s
  deadline after `run()` computes it. It passes the same logical clock as
  `now=` and keeps `receipt["targets"]["a"]`. It adds the capacity evidence and
  `validate_stop` assertions and a resumed run that completes `a`. No assertion
  was removed. This matches the root-cause section above.
- Review thread `PRRT_kwDOQprj9M61Dwgw` (Codex P2: defer tasks the worker cannot
  perform) is `isResolved=true` and `isOutdated=true`. Its objection was
  substantive, and it has been met: tasks 08, 10, 13, 14 and 15 were `deferred`
  with notes when the thread was resolved. Task 10/14 now move to `done` only
  because of the receipt below. Task 08/13 stays deferred.
- `gh run view 42518195788 -R stranske/Orchestrator`: success on
  `c0c5cb6aa8bf79aa855a54258c0ed423011cebeb`. Created 20:04:14Z, finished
  20:13:38Z. `verify.py aggregate + combined coverage` (1m23s) and
  `verify.py aggregate in the flat exec-mirror shape` (1m12s) both succeeded.
  All 12 shards succeeded.

### Named regression on current Orchestrator main

`timeout 300 /opt/anaconda3/bin/python3 -m pytest tests/test_closer_pipeline.py::test_capacity_is_read_fresh_and_zero_defers -q -p no:cacheprovider`
on a clean clone at `b26e6421232cd64893d8d7f4b7e4f75193c56f42`: **1 passed, exit 0**.
No virtual environment exists in the canonical Orchestrator clone, so
`/opt/anaconda3/bin/python3` (3.12.2) was used. Output:
[named-regression-b26e642.txt](named-regression-b26e642.txt).

### Subsequent sync-core disposition: observed

The receipt was read from the local sync-core state. No workflow and no
sync-core run was triggered. It is in
[sync-core-1247-receipt.txt](sync-core-1247-receipt.txt).

- The finding round was `20261108T192823Z`: `shipment-caused`, owner
  stranske/Workflows, handoff #4555. It came from classification `6e7ea8f8…` on
  head `7ba7006d`.
- Rounds `20261108T194358Z` (`seal-pending`) and `20261108T195953Z`
  (`pre-existing`, the `summary` check, handed to Orchestrator #1262) no longer
  carry the shipment-caused label. They still list the old head's verify.py
  failure as `failed, unclassified`, so they do **not** count as a clearance.
- Round `20261108T201627Z` is the first round after run 42518195788 finished.
  It is `ready-for-maint71` and lists no failing check.
- Rounds `20261108T205305Z` and `20261108T205926Z` are terminal **`delivered`**:
  "merged 2026-11-08T20:49:16Z; 2 files, 0 mismatches". The target ledger
  records head `c0c5cb6aa8bf79aa855a54258c0ed423011cebeb`, `last_round`
  `20261108T205926Z`, `terminal: delivered`.
- Retired-target disposition: **not supported by the classifier.**
  `~/.codex/sync-core/sync_core.py` line 51 defines target terminals as
  `delivered, delivered-mismatch, superseded, handed-off, pin-held,
  not-a-sync-pr`. `retired` exists only as a repairs-ledger state, and #1247
  has no repairs row. `delivered` is the explicit terminal disposition.
- Limitation: `rounds.jsonl` records no per-round head. The head attribution of
  rounds 631–633 is inferred from the GitHub run timestamps, which are in the
  receipt. The terminal head comes from the target ledger.

The acceptance criterion "the next sync-core round classifies
stranske/Orchestrator#1247 without this finding" is met by machine receipt.
Rounds 633–637 carry no finding, and the target is terminal `delivered`.

### Configured local repository test command: still incomplete

Stop rule, declared before execution: **zero new attempts.** Reasoning:

- The owner's ten-minute check limit caps any local attempt at 600 s.
- The only measured local run of this exact command,
  `VERIFY_PYTEST_WORKERS=8 /opt/anaconda3/bin/python3 src/verify.py` on clean
  `27266f81`, ran past 1500 s with no terminal summary
  ([orchestrator-local-suite.txt](orchestrator-local-suite.txt)).
- CI's coverage shape alone takes 28.5 shard-minutes at 4 workers.
- Four other agents' pytest processes were running on this 10-core machine
  (load 3.2).

A 600 s attempt cannot reach a terminal result on that measured basis. It would
only repeat the exit-124 evidence at a cost to the other agents.

The criterion therefore stays **unchecked**, and the exact observed failure is
unchanged: exit 124 after 1500 s, no summary. The first unresolved step is the
configured local command not finishing within any permitted local window.
Ownership is human or CI. The remote half (run 42518195788, 15042 passed) is
observed. No production logic or test was changed.
