# Issue #4427: consumer WASM pytest pin handoff

The reported mismatch cannot be fixed through Workflows' `pyproject.toml`.
At the [reported consumer head](https://github.com/stranske/Trend_Model_Project/blob/73120b9a594e/.github/workflows/pages-wasm-demo.yml),
`pages-wasm-demo.yml` directly installs `pytest==9.1.1`. Workflows already declares
`pytest==9.2.0` in `pyproject.toml`, `requirements.lock`, and the canonical
`PYTEST_VERSION` pin. Downgrading these declarations would reverse the requested
dependency update and would not repair the workflow.

There is no WASM workflow source or consumer template in Workflows. Compiling
`.github/sync-manifest.yml` confirms that neither `pyproject.toml` nor
`.github/workflows/pages-wasm-demo.yml` is a Maint 68 target. Development pins are
propagated by Maint 52, as documented under
[Autofix Tool Version Ownership](CONSUMER_REPO_MAINTENANCE.md#autofix-tool-version-ownership).
Maint 68 regeneration cannot update the consumer-owned WASM workflow.

`tests/test_dependency_version_alignment.py` exercises the real dependency sync
helper with a stale consumer development pin and compares its output against the
source development dependency. It also compiles the actual Maint 68 plan to check
the ownership boundary. These tests protect source/dependency alignment; they do
not claim to fix or validate the consumer's workflow. Temporarily changing the
source development pin to `9.1.1` makes the new alignment test fail with
`assert '==9.1.1' == '==9.2.0'`; restoring it makes the test pass.

## Local verification

- [x] Trace the reported pin to the consumer workflow and verify the Workflows
  source/dependency producer and Maint 68 ownership boundary.
- [x] Run the dependency alignment, dependency sync, and manifest compiler tests:
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_dependency_version_alignment.py tests/scripts/test_sync_dev_dependencies.py tests/scripts/test_sync_manifest_compiler.py -m 'not slow'`
  — 110 passed. Plugin autoload is disabled only for this focused diagnostic run;
  the unmodified full gate result remains failing.
- [x] Demonstrate source-pin break and restoration: one expected assertion failure
  with `9.1.1`, followed by one pass with the original `9.2.0` restored.
- [x] Run Black and Ruff on the changed Python test; both pass.
- [ ] Complete both full source gates. `python3 -m pytest -q tests/ -m 'not slow'`
  fails before collection because the installed LangSmith package uses deprecated
  `asyncio.iscoroutinefunction` on Python 3.14. Excluding only its pytest plugin
  still produces two collection errors from that dependency. The JavaScript
  command was interrupted after several minutes without further output; no
  completed suite result is available. The full Black check first hit the sandbox's
  multiprocessing restriction; its single-worker retry also remains unverified.
- [ ] Commit the source tests and handoff. Staging these exact files fails with
  `.git/index.lock: Read-only file system`; no commit was created.
- [ ] Record the finding in the remote PR description and apply `needs-human`.
  External writes require approval that this session cannot obtain.

## Maintainer verification

- [ ] Authorize a separate change to Trend_Model_Project's protected
  `.github/workflows/pages-wasm-demo.yml` on a consumer-owned branch. Align its
  focused pytest install with the development dependency. Do not patch generated
  PR #6186 or its sync branch.
- [ ] Run the consumer's WASM contract tests with the aligned dependency.
- [ ] If a Maint 68 preview is needed, dispatch from the Workflows Actions UI, or run:

  ```bash
  gh workflow run maint-68-sync-consumer-repos.yml \
    --repo stranske/Workflows --ref main \
    -f phase=preview -f repos=stranske/Trend_Model_Project -f dry_run=true
  ```

  Inspect the resulting plan and sync result artifacts. Expect no WASM workflow
  replacement; this preview alone cannot establish that the mismatch is resolved.
  A later write delivery must follow the configured canary/promotion process in
  [Manual Sync Trigger](CONSUMER_REPO_MAINTENANCE.md#manual-sync-trigger).
- [ ] After the consumer workflow repair is merged and any delivery is regenerated,
  inspect its exact-head workflow and development pins together. Confirm both use
  the same pytest version and that the contract tests pass.
- [ ] Confirm the next Maint 71 report for Trend_Model_Project#6186 no longer
  includes review thread `r4457616005`, and sync-core stops reporting that finding.
  This remains a live maintainer check, not a local test result.

The run uses `agent-standard`; the supplied security boundary forbids workflow
edits without explicit `agent-high-privilege` approval. Requests to add the
`needs-human` label and a blocker comment to Workflows PR #4446 were denied by the
session's external-write approval policy. This file preserves the required
handoff for a maintainer; the label and remote comment still need to be applied.
