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
the ownership boundary. `align_quoted_tool_pins` in `scripts/sync_dev_dependencies.py`
rewrites the reported quoted install line locally. `--workflow-runs` exposes that
rewriter for one explicit file; Maint 52 does not pass the flag, so consumer-owned
workflows stay untouched. The regression test reads that rendered pytest pin and
requires it to equal the development dependency in `pyproject.toml`. These tests protect source/dependency alignment and the rendered
install line; they do not edit the consumer workflow. Temporarily making the
aligner return the original `pytest==9.1.1` line makes
`test_reported_wasm_install_aligns_to_development_pytest_pin` fail; restoring the
rewriter makes it pass. Temporarily changing the source development pin to `9.1.1`
makes the older alignment test fail with `assert '==9.1.1' == '==9.2.0'`; restoring
it makes that test pass.

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

## Follow-up reconciliation

Reviewing the three PR commits confirms that only the task ledger, the tests,
and this handoff changed; no pytest source pin was changed. Reading the reported
consumer workflow at `73120b9a594e` again confirms the direct `pytest==9.1.1`
install. The investigation and manual dispatch documentation are complete;
the source fix, WASM regression, regenerated candidate and live acceptance
remain incomplete.

The dependency regression now exercises the actual sync command's entry point.
It checks that a stale consumer project and lockfile are rejected without being
modified, applies the canonical pins, compares both outputs against the source
development dependency, and verifies a clean check and an idempotent second apply.
The focused command above still passes all 110 tests. Ruff passes. Deliberately
changing only the source development pin to `9.1.1` produces one expected failure;
restoring `9.2.0` produces one pass. This proves source/dependency regression
sensitivity, not detection or repair of the consumer's independent workflow pin.

Automatic approval review rejected the PR-body reconciliation, `needs-human`
label, and blocker comment: each returned `MCP tool call requires approval, but
approval policy is never`. No remote checkbox update succeeded. A maintainer
should check only the investigation, finding-recording (after adding the finding
to the PR description), and standalone manual-dispatch documentation tasks.
Combined documentation-and-candidate-resolution tasks must stay unchecked.

The full Python gate still exits before collection on LangSmith's deprecated
`asyncio.iscoroutinefunction` call under Python 3.14. The exact repository-wide
Black command exits with `PermissionError: [Errno 1] Operation not permitted`
when its multiprocessing forkserver binds a socket. The changed test formats
successfully, but the full formatting gate is not satisfied, so this run must
not commit Python changes. The sandbox also declares `.git` read-only.
PR #4446 was rechecked as open and ready for review (`isDraft=false`).
The JavaScript gate was bounded with `timeout 180s` and exited 124; it did not
complete successfully. Both full source-gate acceptance checkboxes remain open.
The proposed PR-body reconciliation is saved at
`/tmp/issue-4427-reconciled-pr-body.md` for manual application.

## Source-lock regression follow-up

The existing lockfile test checked dependency presence, so a stale pytest version
in `requirements.lock` could still pass. The new
`test_source_pytest_lock_matches_development_pin` compares the actual lock pin
against the development requirement in `pyproject.toml` without hard-coding the
expected version. Both source declarations remain at `9.2.0`.

- [x] Run the focused alignment, dependency-sync and manifest-compiler command
  above: **111 passed** with plugin autoload disabled. Ruff also passes.
- [x] Temporarily change only the lock's pytest pin to `9.1.1`: the new test
  fails with `assert '==9.2.0' == '==9.1.1'`. Restore the original lock bytes:
  **1 passed**. This verifies the source-lock guard, not the consumer WASM fix.
- [ ] Complete the full Python gate: it still exits before collection on the
  LangSmith deprecation described above. Warning enforcement is unchanged.
- [ ] Complete the full JavaScript gate: the command bounded by `timeout 180s`
  exited **124**, with pending-promise cancellation diagnostics; it did not pass.
- [ ] Complete repository-wide Black: the requested check with
  `BLACK_NUM_WORKERS=1` was interrupted after remaining unresponsive; an explicit
  `--workers 1` retry timed out after 45 seconds, reporting 618 unchanged files.
  The changed test passes its own Black check, but the full formatting gate
  remains unverified. No Python commit is permitted while that gate is incomplete.
- [ ] Commit the changes: this session also reports `.git` as read-only.
- [ ] Publish the investigation and blocker remotely: PR-description, comment
  and `needs-human` label writes were each rejected with
  `MCP tool call requires approval, but approval policy is never`.

The consumer files were re-read at `73120b9a594e`: the workflow directly installs
`pytest==9.1.1` and the development dependency is `pytest==9.2.0`. The original
WASM regression and source-fix tasks remain blocked by the protected consumer
workflow boundary. The added test does not make those tasks complete.
PR #4446 was rechecked as open and ready for review (`isDraft=false`).
