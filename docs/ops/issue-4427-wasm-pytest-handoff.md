# Issue #4427: consumer WASM pytest pin handoff

## Current status (2026-11-10, issue #4612)

**Source repair (complete, merged).** PR #4446 (`fac332ae`) extends Maint 52 so
`scripts/sync_dev_dependencies.py` rewrites quoted dev-tool pins in
`.github/workflows/pages-wasm-demo.yml` when present, and
`maint-52-sync-dev-versions.yml` stages that file in the dev-tool commit.
Workflows already pinned `pytest==9.2.0` in `pyproject.toml`, `requirements.lock`,
and `PYTEST_VERSION`; no further Workflows source pin change was required.

**Local proof (complete).** Regression tests apply Maint 52's
`--apply --pre-commit --resolve-locks` on the reported consumer split (development
dependency at `9.2.0`, workflow install still `pytest==9.1.1`) and read back
`pytest==9.2.0` from `pages-wasm-demo.yml`. Deliberate-break runs are recorded in
PR #4446 (aligner stub -> expected failure; restored rewriter -> pass).

**Consumer candidate.** The original sync-core evidence pointed at
Trend_Model_Project#6186 head `73120b9a594e`, which still had `pytest==9.1.1` in the
workflow. That head predates the merged Maint 52 repair. After #4446 landed, Maint 52
was dispatched for `stranske/Trend_Model_Project` (Workflows run `41964217277`, wave
hash `91791b44e525`). It published a new dev-tool candidate
[Trend_Model_Project#6189](https://github.com/stranske/Trend_Model_Project/pull/6189)
on branch `deps/sync-dev-versions-91791b44e525`. The previously inspected candidate
head was `3083f697e6e9bb675b67fe5dc5b71192935873fb`; at that head `pyproject.toml`
declared `pytest==9.2.0` and `pages-wasm-demo.yml` installed `pytest==9.2.0`.

**Gate blocker for #6189 (resolved before merge).** Trend_Model_Project Actions run
`41964883333` (Gate for #6189) failed first in Python CI / python 3.14 job
`127041978995` with `AssertionError: Expected at least 1 CSV output, found 0` in
`tests/golden/test_demo.py::TestDemoGoldenMaster::test_demo_pipeline_end_to_end`.
Cause: under pytest 9.2.0, pytest-xdist 3.8.0 loadgroup grouping degraded to plain load
scheduling, so one worker's `rmtree` of `demo/exports` raced another worker's CSV check.
Trend_Model_Project#6192 (merged 2026-11-06T14:10:04Z, before #6189) restored loadgroup
grouping with a `trylast` collection hook that copies the stranded suffix into
`Node._id`. The pytest pin alignment in #6189 was not the cause.

**Consumer delivery (merged).**
- Trend_Model_Project#6189 merged via the Maint 52 native lane on
  2026-11-08T05:33:47Z, merge commit `9937ec146bcd9416b638b2e1889f89fa8b2f7650`.
  Delivered head (final commit of #6189): `ad09728581df4a27d421f272f9e307efaa581e63`.
- Trend_Model_Project#6186 (head `73120b9a594e`) was closed unmerged on
  2026-11-05T05:34:58Z, superseded by #6189.
- Review thread [r4457616005](https://github.com/stranske/Trend_Model_Project/pull/6186#discussion_r4457616005)
  remains on the closed #6186; its finding (workflow `pytest==9.1.1` vs development
  `pytest==9.2.0`) was absent from #6189 at the inspected head `3083f697`.

**Maint 71 report.** `maint-71-merge-sync-prs.yml` run
[42596605795](https://github.com/stranske/Workflows/actions/runs/42596605795)
(2026-11-09T09:51:40Z) concluded `success`, but its log does not name the dev-tool
candidate, #6189 or #6186 (a search of the full run log for `6186` and `6189` finds no
report line). Its Trend_Model_Project line is
`stranske/Trend_Model_Project@c6b85ffe: Consumer-declared delivery checks: 1 of 2 passed; 1 never started, merge blocked: Health 45 Agents Guard / guard; 1 also required, gated as required`.

The post-issue scheduled run
[42762829524](https://github.com/stranske/Workflows/actions/runs/42762829524)
(2026-11-10T05:33:03Z, Workflows head `ee964d5139fed02fcba57844ce93fc84a29dbc3e`)
also omitted both numbers. Its Trend_Model_Project section processed workflow
delivery #6217 at `24e3bc2e94f6`, rather than the historical dev-tool candidates.

On 2026-11-10 the exact requested dispatch was attempted:

```bash
gh workflow run maint-71-merge-sync-prs.yml --repo stranske/Workflows --ref main
```

The Orchestrator `gh` guard refused it (exit 77): shared production jobs cannot
be started inside a dispatched agent; schedules and sync-core own those starts.
No new run was created, and no alternative dispatch path was used.

**Report repair (branch, not deployed to main).** The missing history is upstream of the
formatter: `listMaint71PullRequests` reads open PRs plus the latest closed stable
workflow heads, excluding closed dev-tool heads. Maint 71 now makes one bounded,
read-only GraphQL search (up to 100 recent dev-tool candidates per repository)
for unscoped/dev-tool reports. It records historical states separately from
merge actions, prints repository-qualified candidate lines in logs and the job
summary, and labels unavailable/truncated accounting explicitly. Historical rows
never enter merge selection, cleanup, handoffs or this run's merge counters.
A live read of that query returned 58 candidates, `hasNextPage=false`, including
#6189 merged and #6186 closed unmerged. This is API-read evidence, not a deployed
Maint 71 acceptance run.

**A2 remains pending:** after this source change ships, the native production
owner must obtain a new unscoped/dev-tool report and record its run id. The issue's
acceptance command must print both candidate numbers:

```bash
gh run view <id> --repo stranske/Workflows --log | grep -E '6189|6186'
```

**Sync-core observation (observed).** The first retained local sync-core round
containing Trend_Model_Project after the merge is `20261108T054334Z`, recorded
at `2026-11-08T05:43:42Z` with `apply=true`. Its target is #6189, disposition and
terminal state `delivered`, reason `merged 2026-11-08T05:33:47Z; 5 files, 0 mismatches`,
and `handoffs=[]`. The matching target receipt binds that round to delivered head
`ad09728581df4a27d421f272f9e307efaa581e63`.

Sources read on 2026-11-10 (no sync-core round was launched):

- `~/.codex/orchestrator/sync-core/rounds.jsonl`: the round/item above.
- `~/.codex/orchestrator/sync-core/targets/stranske_trend_model_project_6189.json`:
  `last_round=20261108T054334Z`, `head=ad09728581df4a27d421f272f9e307efaa581e63`,
  `disposition=delivered`, `terminal=delivered`.

The round created no handoff and did not recreate/bump #6186 or its finding.
GitHub readback found #6186 still closed, last updated 2026-11-05T05:34:59Z;
comment r4457616005 last updated 2026-11-03T16:36:18Z, with no post-merge replies.
Issue #4427 remains closed with no post-merge comments. The only newly created
`deps/sync-dev-versions-*` PR found after the merge was #6213, head
`b2666625709170f951508d4c79f026c631bcea89`, merged 2026-11-09T01:20:03Z.
This establishes the retained round's result, not a guarantee against future recurrence.

For the requested hosted inventory, the first Maint 82 campaign run after the
merge was [42451269313](https://github.com/stranske/Workflows/actions/runs/42451269313),
created 2026-11-08T05:33:56Z at Workflows head
`9acdde6d5f0731bf968a6766d83f2b47db8375a3`; its log names discovery of
Trend_Model_Project. Maint 82 campaign discovery is distinct from the local
sync-core classification above and does not substitute for it.

## Delivered-head pin and WASM check (2026-11-10)

An isolated archive at `/tmp/4629-consumer-exact` contains exact delivered
head `ad09728581df4a27d421f272f9e307efaa581e63`; the consumer checkout was not changed.
The selected repository interpreter is
`/Users/teacher/Library/CloudStorage/Dropbox/Learning/Code/Trend_Model_Project/.venv/bin/python`
(CPython 3.12.2, its existing virtual environment). From the archive:

```bash
grep -n 'pytest==' pyproject.toml .github/workflows/pages-wasm-demo.yml
# pyproject.toml:115:    "pytest==9.2.0",
# .github/workflows/pages-wasm-demo.yml:48:        run: python -m pip install "pytest==9.2.0" "pytest-xdist==3.8.0"
/Users/teacher/Library/CloudStorage/Dropbox/Learning/Code/Trend_Model_Project/.venv/bin/python -m pytest -q tests/wasm/test_build_wasm_site.py tests/wasm/test_demo_no_external_cdn.py
# 23 passed in 0.39s
```

The two requested files pass. This existing local interpreter is older than the
consumer's declared Python >=3.13, so this result does not establish full supported-runtime
CI compatibility or the installed environment's pytest version matching the declared pin.

## Maint 71 regression check (2026-11-10)

```bash
node --test .github/scripts/__tests__/maint71_devtool_final_binding.test.js .github/scripts/__tests__/maint71_merge_sync_prs.test.js
# 243 tests, 243 passed, 0 failed; 604.34 ms
```

Before the collector repair, the new end-to-end regression
`Maint 71 accounts for closed dev-tool candidates when no generated PR is open`
failed because the actual controller summary contained only `no_prs` and neither
candidate. After the repair it passes, checks log and summary dispositions,
and proves historical merges do not inflate this run's merge count. Additional
cases cover open, truncated, unavailable, malformed, untrusted and fork evidence,
and distinguish a dry-run proposed closure from an actual closed-unmerged PR.
No full local suite was run.

## Investigation summary

Trend_Model_Project#6186 is a Maint 52 dev-tool candidate (`deps/sync-dev-versions-*`),
not a Maint 68 template sync. Compiling `.github/sync-manifest.yml` confirms neither
`pyproject.toml` nor `.github/workflows/pages-wasm-demo.yml` is a Maint 68 copy target;
Maint 68 cannot repair the WASM install line. Development pins and the aligned workflow
install are propagated by Maint 52 per
[Autofix Tool Version Ownership](CONSUMER_REPO_MAINTENANCE.md#autofix-tool-version-ownership).

At the [original reported head](https://github.com/stranske/Trend_Model_Project/blob/73120b9a594e/.github/workflows/pages-wasm-demo.yml),
`pages-wasm-demo.yml` directly installed `pytest==9.1.1` while the development
dependency was already moving to `9.2.0`.

Key tests (all on `main` after #4446):

- `tests/scripts/test_sync_dev_dependencies.py` - Maint 52 apply aligns
  `pages-wasm-demo.yml` to the development pytest pin.
- `tests/test_dependency_version_alignment.py` - ownership boundary vs Maint 68;
  WASM install alignment regression.
- `tests/workflows/test_maint52_sync_dev_versions_pr_body.py` - workflow stages the
  WASM file.

Focused validation command for this closer repair:

```bash
python3 -m pytest -q tests/test_dependency_version_alignment.py \
  tests/scripts/test_sync_dev_dependencies.py \
  tests/workflows/test_maint52_sync_dev_versions_pr_body.py
```

## Maintainer verification (live)

- [x] Merge the Workflows source repair (#4446).
- [x] Regenerate the consumer dev-tool candidate through Maint 52 (do not hand-edit
  the generated branch).
- [x] Merge Trend_Model_Project#6189 (2026-11-08T05:33:47Z, merge commit `9937ec14`,
  delivered head `ad097285`); #6186 closed unmerged (2026-11-05T05:34:58Z).
- [ ] Obtain a Maint 71 report that names the dev-tool delivery (#6189) and obsolete
  #6186. Runs 42596605795 and 42762829524 name neither; dispatch refused by the production guard.
- [x] Identify the first sync-core round on Trend_Model_Project after
  2026-11-08T05:33:47Z: `20261108T054334Z` delivered #6189, no handoff or old-finding bump.
- [x] Re-run the pin grep and the two WASM test files at delivered head `ad097285`
  (or current Trend_Model_Project main), quoting interpreter path, pass count and pin lines.
- [ ] Optional Maint 68 preview (expect no WASM workflow replacement):

  ```bash
  gh workflow run maint-68-sync-consumer-repos.yml \
    --repo stranske/Workflows --ref main \
    -f phase=preview -f repos=stranske/Trend_Model_Project -f dry_run=true
  ```

## Round 4 stale-closure report regression (2026-11-10)

Inline review `4527153576` identified a remaining report omission: the controller's
actual stale-closure rows include `branch` and `status`, but omit `delivery_lane`.
Removing the invented lane/disposition fields from the existing formatter fixture
reproduced the failure: the summary omitted #6186. The formatter now uses its
existing branch-to-lane helper when an explicit lane is absent. The regression
requires `#6186 closed unmerged`, and still checks the dry-run `would close` label.
The exact two-file Node command was rerun after this repair: 243 passed, zero failed.
This affects reporting only; merge selection and dependency pins are unchanged.

## Round 4 CI readback (2026-11-10)

The reported failure run [42849929470](https://github.com/stranske/Workflows/actions/runs/42849929470)
on head `dd5ef628caf450d0003373753394de283bf860ad` concluded `cancelled`.
Both Resolve Context and Record autofix dispatch completion have no executed
steps; neither is evidence of a code failure. Later same-head run
[42849931115](https://github.com/stranske/Workflows/actions/runs/42849931115)
concluded `success`: Resolve Context succeeded, and autofix/completion were skipped.
No workflow change is justified by those cancellations.

The exact requested Maint 71 dispatch was retried in round 4 and again refused
by the production guard (exit 77). No new run was created. Latest inspected run
[42789507724](https://github.com/stranske/Workflows/actions/runs/42789507724)
concluded `success` but its full log contains neither #6189 nor #6186.
Blocking/drainable pair: production dispatch blocked in this seat; focused local
verification and this evidence update are drainable. The native scheduler or
sync-core owner must obtain the post-deployment report; no bypass was attempted.

The delivered-head test archive was freshly created with `git archive
ad09728581df4a27d421f272f9e307efaa581e63`, then the pin grep and exact two-file
WASM command above were rerun. Round 4 also re-read the first retained local
sync-core round, its target receipt, #6186 and r4457616005 timestamps, and the
post-merge dev-tool PR inventory; the observations above remain unchanged.
The local round's summary references Maint 71 run `42445636759`, created
2026-11-08T04:09:17Z; that earlier hosted run is not the post-merge local round id.

## Round 5 production report check (2026-11-10T16:45Z)

Outcome: **A2 unsatisfied; T1 pending**. Proof command:
`gh run view <new-run-id> --repo stranske/Workflows --log`, with explicit
candidate dispositions for Trend_Model_Project#6189 and #6186. Stop rule:
one dispatch and at most 15 minutes of monitoring; stop production attempts
at the first refusal or failed/omitting report.

The exact requested command was attempted once in this round:

```bash
gh workflow run maint-71-merge-sync-prs.yml --repo stranske/Workflows --ref main
```

It exited 77: the Orchestrator guard refuses shared production starts inside
a dispatched agent and assigns them to schedules and sync-core. No run was
created, and no alternate dispatch route was attempted. Blocking/drainable:
production dispatch is blocked in this seat; focused tests and recording this
evidence remain drainable. The scheduler/sync-core owner retains the production
continuation after deployment of the report repair.

Latest listed run [42789507724](https://github.com/stranske/Workflows/actions/runs/42789507724)
was created 2026-11-10T09:17:48Z, concluded `success`, and used Workflows head
`9dcc645ba2b51f6db655486cec7e06e1f7d5e5b4`. Its full log was read again.
The literal acceptance grep `grep -E '6189|6186'` matches fractional timestamp
digits, but no candidate disposition. Searching for `#6189`, `#6186`,
`/pull/6189`, `/pull/6186`, or `Trend_Model_Project` returns no matches.
Those timestamp matches do not satisfy A2.

The exact A1 two-file Node command was rerun on the unchanged implementation:
243 passed, zero failed, 613.10 ms. This round changes evidence only; no pins,
selectors or workflow behavior were changed.

## Round 6 production report check (2026-11-10T17:15Z)

Outcome: **A2 unsatisfied; T1 pending**. The proof remains a newly dispatched
Maint 71 run whose full log names both Trend_Model_Project#6189 and #6186.
Check command: `gh run view <new-run-id> --repo stranske/Workflows --log`.
Stop rule: one dispatch attempt and at most 15 minutes of monitoring; stop
production attempts at the first refusal or failed/omitting report.

The exact requested dispatch command above exited 77 again. The Orchestrator
guard reserves shared production starts for schedules and sync-core. No new run
was created and no bypass was attempted. Blocking/drainable pair: production
dispatch is blocked in this seat; focused validation and this evidence update
remain drainable. Production continuation stays with the scheduler/sync-core
owner after the report repair reaches main.

The latest listed run remains `42789507724` (completed successfully at source
head `9dcc645ba2b51f6db655486cec7e06e1f7d5e5b4`). Its full log was fetched again:
the literal acceptance regex matches five timestamp lines, while candidate-aware
searches for `#6189`, `#6186`, `/pull/6189`, `/pull/6186`, or
`Trend_Model_Project` match zero lines. A2 therefore remains pending.

The exact A1 two-file Node command passed again: **243 passed, zero failed**,
581.40 ms. This round changes evidence only. Cost: one refused dispatch, zero
production runs, one existing-run log read, and one focused local test run.

## Round 7 production report check (2026-11-10T17:32Z)

Outcome: **A2 unsatisfied; T1 pending**. Acceptance requires a newly dispatched
Maint 71 run whose log explicitly names Trend_Model_Project#6189 and #6186;
check command: `gh run view <new-run-id> --repo stranske/Workflows --log`.
Stop rule: one dispatch attempt and at most 15 minutes of observation, stopping
at the first refusal or failed/omitting report.

The exact requested dispatch exited 77. The Orchestrator `gh` guard states that
shared production starts are refused inside dispatched agents and belong to
schedules and sync-core. No run was created and no alternate route was attempted.
The refusal reached this round's stop rule. Blocking/drainable pair: production
dispatch is blocked in this seat; focused validation and recording evidence are
drainable. The native schedule/sync-core owner retains production continuation.

The latest listed run remains [42789507724](https://github.com/stranske/Workflows/actions/runs/42789507724),
completed successfully at `9dcc645ba2b51f6db655486cec7e06e1f7d5e5b4`.
Its full log was read again. The literal `6189|6186` regex matches five timestamp
lines; candidate-aware `#6189`, `#6186`, `/pull/6189`, and `/pull/6186` searches
match zero lines. Timestamp digits do not establish either candidate disposition.

The exact A1 two-file Node command passed: **243 passed, zero failed**, 655.51 ms.
This round changes documentation only. Cost: one refused dispatch, zero new
production runs, one existing-run log read and one focused local test run.
T1 and A2 remain unchecked; no dependency pins or report behavior changed.

## Round 8 production report check (2026-11-10T17:44Z)

Outcome: **A2 unsatisfied; T1 pending**. The acceptance outcome is a newly
dispatched Maint 71 report naming both Trend_Model_Project#6189 and #6186,
printed by `gh run view <new-run-id> --repo stranske/Workflows --log`.
Stop rule: one dispatch and at most 15 minutes of observation, stopping at the
first refusal or failed/omitting report.

The exact requested command was attempted once:

```bash
gh workflow run maint-71-merge-sync-prs.yml --repo stranske/Workflows --ref main
```

It exited 77. The Orchestrator guard reserves shared production starts for
schedules and sync-core and explicitly directs dispatched agents to leave a
required production run undone. No new run was created and no bypass was used.
The first broken step is production dispatch; the stop rule has been reached.
Blocking/drainable pair: production dispatch is blocked in this seat; focused
validation and this evidence update remain drainable. The scheduler/sync-core
owner retains production continuation after the source repair reaches main.

The latest listed run remains
[42789507724](https://github.com/stranske/Workflows/actions/runs/42789507724).
Its full log was read again: `6189|6186` matches five timestamp lines, while
`#6189|#6186|/pull/6189|/pull/6186|Trend_Model_Project` matches zero lines.
Those numeric matches do not satisfy A2. The exact A1 two-file Node command
passed again: **243 passed, zero failed**, 597.89 ms.

Cost: one refused dispatch, zero new production runs, one existing-run log read
and one focused test run. This round changes documentation only; T1 and A2
remain unchecked.

## Round 9 production report check (2026-11-10T17:59Z)

Outcome: **A2 unsatisfied; T1 pending**. The proof remains a newly dispatched
Maint 71 run whose log explicitly names Trend_Model_Project#6189 and #6186,
read with `gh run view <new-run-id> --repo stranske/Workflows --log`.
Stop rule: one dispatch and at most 15 minutes of observation, stopping at the
first refusal or failed/omitting report.

The exact requested dispatch command exited 77. The Orchestrator guard reserves
shared production starts for schedules and sync-core and directs dispatched
agents to leave a required production run undone. No new run was created and
no alternate route was attempted. The stop rule tripped at production dispatch.
Blocking/drainable pair: production dispatch is blocked in this seat; focused
validation and recording the result remain drainable. The scheduler/sync-core
owner retains the production continuation after the report repair reaches main.

The latest listed run remains
[42789507724](https://github.com/stranske/Workflows/actions/runs/42789507724),
successful at source head `9dcc645ba2b51f6db655486cec7e06e1f7d5e5b4`.
Its freshly fetched full log has five literal `6189|6186` timestamp matches and
zero matches for `#6189|#6186|/pull/6189|/pull/6186|Trend_Model_Project`.
Those timestamp matches do not satisfy A2. The exact A1 two-file Node command
passed: **243 passed, zero failed**, 585.25 ms.

Cost: one refused dispatch, zero new production runs, one run-list read, one
existing-run log read and one focused test run. This round changes documentation
only; T1 and A2 remain unchecked. Repeating this seat cannot establish production
acceptance while its dispatch is refused and the source repair is undeployed.

## Round 10 production report check (2026-11-10T18:17Z)

Outcome: **A2 unsatisfied; T1 pending**. The acceptance command remains
`gh run view <new-run-id> --repo stranske/Workflows --log`, with explicit
dispositions for Trend_Model_Project#6189 and #6186. Stop rule: one dispatch
and at most 15 minutes of observation, stopping on dispatch refusal.

The exact requested command,
`gh workflow run maint-71-merge-sync-prs.yml --repo stranske/Workflows --ref main`,
exited 77. The Orchestrator guard reserves shared production starts for schedules
and sync-core and explicitly directs this seat to leave the required run undone.
No new run was created. The stop rule tripped at production dispatch.
Blocking/drainable pair: production dispatch is blocked; existing-run readback,
focused validation and this evidence update remain drainable.

The latest listed run is still
[42789507724](https://github.com/stranske/Workflows/actions/runs/42789507724),
successful at `9dcc645ba2b51f6db655486cec7e06e1f7d5e5b4`.
Its freshly read full log has five literal `6189|6186` timestamp matches and
zero matches for `#6189|#6186|/pull/6189|/pull/6186|Trend_Model_Project`.
These numeric matches do not establish candidate dispositions or satisfy A2.
The exact A1 two-file Node command passed: **243 passed, zero failed**, 628.59 ms.

Cost: one refused dispatch, zero new production runs, one run-list read, one
existing-run log read and one focused test run. This round changes documentation
only. T1 and A2 remain unchecked; production continuation belongs to the
scheduler/sync-core owner after the report repair reaches main.

## Round 11 production report check (2026-11-10T18:30Z)

Outcome: **A2 unsatisfied; T1 pending**. The one-dispatch stop rule tripped:
the exact requested `gh workflow run maint-71-merge-sync-prs.yml --repo
stranske/Workflows --ref main` exited 77 at the Orchestrator production-job
guard. No run was created and no alternate dispatch route was attempted.
Blocking/drainable pair: production dispatch blocked; existing-run readback and
focused validation drainable.

Fresh run-list and full-log reads still identify
[42789507724](https://github.com/stranske/Workflows/actions/runs/42789507724)
as the latest run. Its five literal `6189|6186` matches are timestamp fragments;
there are zero matches for `#6189|#6186|/pull/6189|/pull/6186|Trend_Model_Project`.
They do not satisfy A2. The exact A1 two-file Node command passed again:
**243 passed, zero failed**, 621.82 ms.

Cost: one refused dispatch, zero production runs created, one run-list read,
one existing-run log read and one focused test run. This documentation-only
update preserves T1/A2 as pending. The scheduler/sync-core owner must obtain
the deployed report after the repair reaches main. Post-push review belongs
to the next scheduled closer pass, no earlier than seven minutes after push;
this round does not claim that review or current-head CI is complete.

## Task completion status (issue #4612, current task IDs)

- **T1: pending.** The exact dispatch was refused; existing run logs do not
  establish the requested newly dispatched report.
- **T2: locally verified.** The closed-candidate omission was reproduced before
  the collector repair (recorded above). The current two-file Node command passes
  all 243 tests, including per-candidate log/summary dispositions. Deployment
  observation is tracked separately under A2.
- **T3: observed with a hosting limitation.** First retained local sync-core round
  `20261108T054334Z` saw delivered head `ad09728581df4a27d421f272f9e307efaa581e63`,
  recorded zero mismatches and no handoff. No #6186/thread bump was found.
  Sync-core is local; the hosted Maint 82 campaign is distinct. Its run id and
  the local receipt are recorded above rather than inventing a hosted sync-core id.
- **T4: verified.** Fresh delivered-head archive: both pin lines read `pytest==9.2.0`
  and 23 WASM tests pass using the quoted repository interpreter.

## Acceptance criteria status (issue #4612, current criterion IDs)

- **A1: locally verified.** Exact two-file Node command: 243 passed, zero failed;
  covers the collector and report changes. Historical rows do not select merges.
- **A2: pending.** No qualifying deployed Maint 71 report names both candidates.
  A passing local regression is not production acceptance.
- **A3: verified.** This handoff records the local sync-core round id and result,
  distinguishes the hosted campaign run, and explicitly marks production report
  acceptance pending. Status IDs here match the current issue #4612 instructions.
- **A4 (scope-only reference): observed locally.** The retained post-merge round
  and exact delivered head are recorded above; this does not certify a hosted
  sync-core workflow run or future recurrence prevention.
