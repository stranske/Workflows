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

Code fix: `buildMarkdownSummary` in `sync_pr_merge_contract.js` now includes per-candidate
disposition lines for dev-tool-sync deliveries. A subsequent Maint 71 run dispatched after this
fix will name the dev-tool candidates explicitly (e.g., `dev-tool: #6189 merged, #6186 closed unmerged`).

Pending: A new Maint 71 run to verify the fix. A3 is NOT YET satisfied.

**Sync-core observation.** pending: no post-merge sync-core round has been identified
for Trend_Model_Project after 2026-11-08T05:33:47Z. A4 is not satisfied.

Issue #4427 is closed. Issue #4458 is open; the remaining A3/A4 observations and the
re-verification at `ad09728` are follow-up work under #4458.

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
  #6186. Run 42596605795 succeeded but names neither.
- [ ] Identify the first sync-core round on Trend_Model_Project after
  2026-11-08T05:33:47Z and record whether it recreated or bumped #6186 or r4457616005.
- [ ] Re-run the pin grep and the two WASM test files at delivered head `ad097285`
  (or current Trend_Model_Project main), quoting interpreter path, pass count and pin lines.
- [ ] Optional Maint 68 preview (expect no WASM workflow replacement):

  ```bash
  gh workflow run maint-68-sync-consumer-repos.yml \
    --repo stranske/Workflows --ref main \
    -f phase=preview -f repos=stranske/Trend_Model_Project -f dry_run=true
  ```

## Task completion status

- **T1**: Evidenced - Gate run `41964883333` for #6189 inspected; first failing step was
  Python CI / python 3.14 job `127041978995` (golden demo CSV race), fixed natively by
  Trend_Model_Project#6192 without bypassing Gate.
- **T2**: Evidenced at the previously inspected head `3083f697` only: `pyproject.toml` and
  `pages-wasm-demo.yml` both declared `pytest==9.2.0`. Not re-verified at delivered head
  `ad097285`.
- **T3**: Evidenced - #6189 merged via the Maint 52 native lane
  (2026-11-08T05:33:47Z, merge commit `9937ec14`); #6186 closed unmerged
  (2026-11-05T05:34:58Z).
- **T4**: Implemented - `buildMarkdownSummary` in `sync_pr_merge_contract.js` updated to
  include per-candidate disposition lines for dev-tool-sync deliveries. Test added to
  `maint71_devtool_final_binding.test.js` to verify the fix. Verification pending a
  new Maint 71 run.
- **T5**: Partially implemented - Code fix for Maint 71 report completed and tested;
  sync-core observation and delivered head re-verification still pending.

## Acceptance criteria status

- **A1**: Not re-verified at `ad09728` - pins matched at the inspected head `3083f697`;
  the WASM test run and pin grep at the delivered head have not been recorded with a
  quoted command and output.
- **A2**: Not re-verified at `ad09728` - no Maint 71 selection change was made on this
  branch; no test output is recorded here.
- **A3**: Implemented - Code fix in place; `node --test .github/scripts/__tests__/maint71_devtool_final_binding.test.js .github/scripts/__tests__/maint71_merge_sync_prs.test.js`
  passes with new test asserting dev-tool PR numbers appear in summary. A3 satisfaction
  pending a Maint 71 run dispatched after this change.
- **A4**: pending: no post-merge sync-core round identified.
