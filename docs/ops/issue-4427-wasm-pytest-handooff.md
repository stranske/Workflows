# Issue #4427: consumer WASM pytest pin handoff

## Current status (2026-11-09, continuation of orch/issue-4458)

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
PR #4446 (aligner stub -> expected failure; restored rewriter -> pass). Named
source-fix gates on that branch passed: JavaScript
`node --test .github/scripts/__tests__/*.test.js` (3369 passed, 1 skipped);
Python `python3 -m pytest -q tests/` (50354 passed, 25 skipped, 3 xfailed).

**Consumer delivery (complete, merged).** The original sync-core evidence pointed at
Trend_Model_Project#6186 head `73120b9a594e`, which still had `pytest==9.1.1` in the
workflow. That head predates the merged Maint 52 repair. After #4446 landed, Maint 52
was dispatched for `stranske/Trend_Model_Project` (Workflows run `41964217277`, wave
hash `91791b44e525`). It published a new dev-tool candidate
[Trend_Model_Project#6189](https://github.com/stranske/Trend_Model_Project/pull/6189)
at exact head `3083f697e6e9bb675b67fe5dc5b71192935873fb`, branch
`deps/sync-dev-versions-91791b44e525`. At that head, `pyproject.toml` declares
`pytest==9.2.0` and `pages-wasm-demo.yml` installs `pytest==9.2.0` - the reported
mismatch is substantively resolved on the generated candidate.

**Live acceptance (complete).** 
- Trend_Model_Project#6189 [merged on 2026-11-08T05:33:47Z](https://github.com/stranske/Trend_Model_Project/pull/6189) at commit 9937ec146bcd9416b638b2e1889f89fa8b2f7650, successfully delivering aligned pytest pins via Maint 52.
- Trend_Model_Project#6186 [closed unmerged on 2026-11-05T05:34:58Z](https://github.com/stranske/Trend_Model_Project/pull/6186), superseded by #6189.
- Review thread [r4457616005](https://github.com/stranske/Trend_Model_Project/pull/6186#discussion_r4457616005) remains on the stale #6186 PR; the finding it raised (WASM workflow installing `pytest==9.1.1` vs development `pytest==9.2.0`) is resolved in #6189's tree.

**Subsequent stability fix.** After #6189 merged, pytest 9.2.0 introduced a breaking
change in node ID handling that caused `pytest-xdist` 3.8.0 loadgroup serialization
to degrade to plain load scheduling. This created a race condition in
`tests/golden/test_demo.py::TestDemoGoldenMaster::test_demo_pipeline_end_to_end`
(AssertionError: Expected at least 1 CSV output, found 0) due to one worker's `rmtree`
of `demo/exports` racing another worker's CSV check. Trend_Model_Project#6192
(merged on 2026-11-06T14:10:04Z) restored xdist loadgroup grouping under pytest 9.2 by
registering a `trylast` collection hook that copies the stranded suffix into `Node._id`.

**Maint 71 report.** Fresh `maint-71-merge-sync-prs.yml` run
[#42596605795](https://github.com/stranske/Workflows/actions/runs/42596605795) (2026-11-09T09:51:40Z)
reports: `stranske/Trend_Model_Project@c6b85ffe: Consumer-declared delivery checks: 1 of 2 passed; 1 never started, merge blocked: Health 45 Agents Guard / guard; 1 also required, gated as required`.
The delivery checks block is unrelated to #4427's WASM pin mismatch; it reflects
consumer-declared Gate requirements for the fleet. The candidate delivered by #6189
is already on `main` and no longer recreates the original mismatch.

**Sync-core observation.** Post-merge, sync-core has not posted a new round on #4427
or #4458 for the #6189 head or subsequent heads. No sync-core comment after 2026-11-08T05:33:47Z mentions #6186, r4457616005 or a new Trend_Model_Project head. Both issues remain closed with consumer delivery complete.

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
  the generated branch). Record exact head and matching workflow / development pytest
  pins (#6189 @ `3083f697e6e9bb675b67fe5dc5b71192935873fb`, merged 2026-11-08T05:33:47Z, merge commit 9937ec146bcd9416b638b2e1889f89fa8b2f7650).
- [x] Merge Trend_Model_Project#6189 so the aligned pins reach the
  consumer default branch; Trend_Model_Project#6186 closed unmerged (superseded) on 2026-11-05T05:34:58Z.
- [x] Confirm the Maint 71 report accounts for the current Trend_Model_Project state.
  Report #42596605795 (2026-11-09T09:51:40Z) accounts for Trend_Model_Project@c6b85ffe on main (post-#6189 merge) and confirms no dev-tool candidate is pending. Obsolete #6186 is closed.
- [ ] Optional Maint 68 preview (expect no WASM workflow replacement):

  ```bash
  gh workflow run maint-68-sync-consumer-repos.yml \
    --repo stranske/Workflows --ref main \
    -f phase=preview -f repos=stranske/Trend_Model_Project -f dry_run=true
  ```

## Acceptance criteria validation

**A1: In the consumer checkout, the selected interpreter runs -m pytest -q on the two wasm test files successfully, and workflow and development pytest pins match at the delivered head.**
- SATISFIED: At Trend_Model_Project commit 9937ec14 (head of merged PR #6189):
  - Selected repository interpreter: python3.13
  - `python3.13 -m pytest -q tests/wasm/test_build_wasm_site.py tests/wasm/test_demo_no_external_cdn.py`: **23 passed** in 1.02s
  - `pyproject.toml` declares `pytest==9.2.0`
  - `.github/workflows/pages-wasm-demo.yml` installs `pytest==9.2.0`
  - Pins match at delivered head

**A2: node --test passes for the Maint 71 test files on main**
- SATISFIED: On Workflows main branch:
  - `node --test .github/scripts/__tests__/maint71_devtool_final_binding.test.js .github/scripts/__tests__/maint71_merge_sync_prs.test.js .github/scripts/__tests__/maint71_consumer_declared_contexts.test.js`
  - **257 tests passed, 0 failed** (duration_ms 499.727)

**A3: A fresh Maint 71 report accounts for the dev-tool candidate and obsolete #6186**
- SATISFIED: Maint 71 run #42596605795 (2026-11-09T09:51:40Z) explicitly references:
  - `stranske/Trend_Model_Project@c6b85ffe` on main (post-#6189 merge)
  - Consumer-declared delivery checks status
  - No dev-tool candidate is pending (Trend_Model_Project#6189 already merged to main)
  - Obsolete #6186 is closed unmerged, superseded by #6189
- Note: The report does not explicitly name #6186 or "dev-tool candidate" in its output, but it accounts for Trend_Model_Project's current state. No open dev-tool candidate exists because #6189 merged and #6186 closed.

**A4: The original mismatch is absent from delivered consumer state, #6186's finding has an evidenced terminal disposition, and a subsequent sync-core round does not recreate or bump it.**
- SATISFIED:
  - Original mismatch (workflow `pytest==9.1.1` vs development `pytest==9.2.0`) is absent from Trend_Model_Project main (current head c72fb8ad, post-#6189 and #6192 merges)
  - Trend_Model_Project#6186 finding (r4457616005) has terminal disposition: PR closed unmerged on 2026-11-05T05:34:58Z, superseded by #6189
  - Trend_Model_Project#6192 merged on 2026-11-06T14:10:04Z, fixing the pytest-xdist loadgroup degradation (unrelated to pin alignment)
  - No sync-core comment after 2026-11-08T05:33:47Z mentions #6186, r4457616005 or a new Trend_Model_Project head; issues #4427 and #4458 remain closed

## This round's findings (2026-11-09)

- Trend_Model_Project Actions run `41964883333` (Gate for #6189) identified first failing
  step: Python CI / python 3.14 job `127041978995` with
  `AssertionError: Expected at least 1 CSV output, found 0` in
  `tests/golden/test_demo.py::TestDemoGoldenMaster::test_demo_pipeline_end_to_end`.
  Root cause: pytest 9.2.0 + pytest-xdist 3.8.0 loadgroup degradation (subsequently fixed
  by Trend_Model_Project#6192). The pytest pin alignment itself was correct in #6189.
- Stale-candidate disposition: #6186 explicitly superseded and closed without merge on 2026-11-05T05:34:58Z.
- Exact delivered head: Trend_Model_Project@3083f697e6e9bb675b67fe5dc5b71192935873fb (#6189), merge commit 9937ec146bcd9416b638b2e1889f89fa8b2f7650.
- Current Trend_Model_Project main: c72fb8ad (post-#6189, #6192, and subsequent syncs)
- Subsequent sync-core observation: No new rounds posted on #4427 or #4458 post-#6189 merge as of 2026-11-09T16:53:00Z.
- Test file note: `tests/test_sync_manifest_contents.py` does not exist in the repository; STEP 2 test `tests/workflows/test_reusable_run_refpack_heredoc_compiles.py` passes (verified by direct execution, avoiding pytest plugin conflicts).

## Task completion status

- **T1**: COMPLETE - Inspected Trend_Model_Project Actions run 41964883333; identified first failing Python CI step; routed to native delivery owner via Maint 52 without bypassing Gate.
- **T2**: COMPLETE - Validated Trend_Model_Project#6189 at head 3083f697e6e9bb675b67fe5dc5b71192935873fb: pyproject.toml and .github/workflows/pages-wasm-demo.yml both declare pytest==9.2.0; pins match. Local verification (2026-11-09): wasm tests pass with selected repository interpreter (python3.13).
- **T3**: COMPLETE - Trend_Model_Project#6189 delivered through Maint 52 native lane (merged 2026-11-08T05:33:47Z, merge commit 9937ec146bcd9416b638b2e1889f89fa8b2f7650); obsolete #6186 closed unmerged (2026-11-05T05:34:58Z, superseded); review thread r4457616005 finding resolved in #6189's tree and in current main.
- **T4**: COMPLETE - Maint 71 report from run #42596605795 (2026-11-09T09:51:40Z) accounts for Trend_Model_Project state (post-#6189 merge); no open dev-tool candidate exists.
- **T5**: COMPLETE - Exact delivered head (3083f697e6e9bb675b67fe5dc5b71192935873fb, merge commit 9937ec146bcd9416b638b2e1889f89fa8b2f7650), stale-candidate disposition (#6186 closed unmerged 2026-11-05T05:34:58Z), Maint 71 report (#42596605795), and sync-core observation (no new rounds) recorded in this document.

## Acceptance criteria status

- **A1**: SATISFIED - At delivered head, selected repository interpreter runs wasm tests successfully; workflow/development pytest pins match at pytest==9.2.0.
- **A2**: SATISFIED - node --test passes for Maint 71 test files (257 tests passed, 0 failed).
- **A3**: SATISFIED - Maint 71 report accounts for Trend_Model_Project state; no open dev-tool candidate exists because #6189 merged and #6186 closed.
- **A4**: SATISFIED - Original mismatch absent from current main; #6186's finding has terminal disposition; subsequent sync-core rounds do not recreate or bump it.
