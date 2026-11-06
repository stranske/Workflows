# Issue #4427: consumer WASM pytest pin handoff

## Current status (2026-11-05, post PR #4446 on `main`)

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
PR #4446 (aligner stub → expected failure; restored rewriter → pass). Named
source-fix gates on that branch passed: JavaScript
`node --test .github/scripts/__tests__/*.test.js` (3369 passed, 1 skipped);
Python `python3 -m pytest -q tests/` (50354 passed, 25 skipped, 3 xfailed).

**Consumer delivery (regenerated candidate; live acceptance pending).** The original
sync-core evidence pointed at Trend_Model_Project#6186 head `73120b9a594e`, which
still had `pytest==9.1.1` in the workflow. That head predates the merged Maint 52
repair. After #4446 landed, Maint 52 was dispatched for
`stranske/Trend_Model_Project` (Workflows run `41964217277`, wave hash
`91791b44e525`). It published a new dev-tool candidate
[Trend_Model_Project#6189](https://github.com/stranske/Trend_Model_Project/pull/6189)
at exact head `3083f697e6e9bb675b67fe5dc5b71192935873fb`, branch
`deps/sync-dev-versions-91791b44e525`. At that head, `pyproject.toml` declares
`pytest==9.2.0` and `pages-wasm-demo.yml` installs `pytest==9.2.0` — the reported
mismatch is substantively resolved on the generated candidate. No separate manual
edit of the consumer workflow is required; delivery is through Maint 52 only.

**Live acceptance (still open).** Review thread
[r4457616005](https://github.com/stranske/Trend_Model_Project/pull/6186#discussion_r4457616005)
remains on the superseded open PR #6186 (`73120b9a594e`, unresolved). Maint 71 must
report the current dev-tool candidate, #6189 must merge (or supersede #6186 with the
aligned tree), and sync-core must stop bumping #4427 on head changes. Issue #4427
was closed when #4446 merged; sync-core had not posted a new round on #4427 after the
#6189 head as of this handoff update.

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

- `tests/scripts/test_sync_dev_dependencies.py` — Maint 52 apply aligns
  `pages-wasm-demo.yml` to the development pytest pin.
- `tests/test_dependency_version_alignment.py` — ownership boundary vs Maint 68;
  WASM install alignment regression.
- `tests/workflows/test_maint52_sync_dev_versions_pr_body.py` — workflow stages the
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
  pins (#6189 @ `3083f697e6e9bb675b67fe5dc5b71192935873fb`).
- [ ] Merge or supersede Trend_Model_Project#6189 so the aligned pins reach the
  consumer default branch; retire stale #6186 if still open.
- [ ] Confirm the next successful `maint-71-merge-sync-prs.yml` report for the
  current dev-tool candidate no longer treats review thread `r4457616005` as blocking,
  and sync-core stops reporting this finding on new heads.
- [ ] Optional Maint 68 preview (expect no WASM workflow replacement):

  ```bash
  gh workflow run maint-68-sync-consumer-repos.yml \
    --repo stranske/Workflows --ref main \
    -f phase=preview -f repos=stranske/Trend_Model_Project -f dry_run=true
  ```

## Historical notes (prior agent sessions, not current blockers)

Earlier handoff drafts recorded sandbox failures that do not apply on the merged
branch: read-only `.git`, incomplete JavaScript gate timeouts, and Python collection
failures from LangSmith on Python 3.14 before #4446's gate fixes (`e8371dd0`,
`baf570de`). Those items are historical; PR #4446 records the passing full gates.

Prior text incorrectly stated the WASM mismatch was unfixed in Workflows and required
a separate consumer-owned workflow patch. That path is superseded by the Maint 52
workflow pin rewriter and regenerated candidate #6189.
