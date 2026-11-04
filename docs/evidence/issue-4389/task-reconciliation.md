# PR #4441 task reconciliation

Reviewed source commit `3fcbb096` and keepalive commits through `87b3ed33`.
Those changes already implement PR-owned completion state and receipts for the
initial task precheck and the earlier final snapshot. The subsequent commits
primarily extend the guarded-merge regression tests.

## Verified progress

- [x] Document PR task authority in `docs/keepalive/GoalsAndPlumbing.md`.
- [x] Implement PR-only task counting while retaining source snapshot validation.
- [ ] Publish every unchecked-task refusal as a warning and owned PR receipt.
- [x] Cover complete PR tasks with unchecked source tasks in the unit suite.
- [ ] Pass the complete Node suite and the mutation/restoration acceptance check.
- [x] Pass the workflow consolidation suite.
- [ ] Observe the required log line on a deployed consumer PR.

The mutation regression now exercises the shipped merge scan, rather than only
the task helper. Counting the raw issue boxes makes its merge-success assertion
fail, emits the refusal warning and receipt, and prevents the runtime guard and
merge request. Restoring PR-only counting reaches the runtime guard and merges
the expected head without publishing a new refusal. This is local mocked API
evidence; it does not establish consumer deployment.

Validation in this run:

- `node .github/scripts/__tests__/guarded-merge-tasks.test.js`: 35 passed.
- `node --test --test-isolation=none .github/scripts/__tests__/guarded-merge-tasks.test.js`:
  35 passed, including mutation and restoration.
- `node --test .github/scripts/__tests__/guarded-merge-tasks.test.js`: passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/workflows/test_workflow_agents_consolidation.py -q -m 'not slow'`:
  79 passed. Without the environment setting, an installed LangSmith plugin
  fails at startup on a Python 3.14 deprecation warning; no repository test is
  skipped by disabling automatic third-party plugin loading.
- The exact `node --test .github/scripts/__tests__/` command fails with
  `MODULE_NOT_FOUND` under Node 24 because the directory has no entry module.
- The explicit test-file glob also encounters an unrelated failure in
  `generated-delivery-seal-action.test.js`: its action-boundary test expects
  `delivery_not_sealed:staging` but receives empty output. The failure reproduces
  with that file alone and was present before this run's test change.
- A bounded full-suite attempt using
  `timeout 90s node --test --test-timeout=30000 .github/scripts/__tests__/*.test.js`
  exits 124 with pending test promises. The full-suite acceptance remains
  unverified; no existing test was removed or disabled.

## Protected follow-up

In `templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml`,
`finalMergeGuardFailure` returns the final merge-boundary task refusal without
calling `reportTaskRefusal`. An unchecked reviewer task introduced only at that
snapshot blocks merging but produces no warning or PR receipt.

Before returning that failure, publish the same reason through
`reportTaskRefusal(prNumber, expectedHead, reason)`. Extend the existing
merge-boundary regression to assert the warning, owned receipt upsert, and absence
of a merge request. This run is `agent-standard`; the supplied security boundary
requires explicit `agent-high-privilege` approval before changing workflow files.
No workflow files were changed in this run.

The GitHub connector rejected the attempted PR-body reconciliation, `needs-human`
label, and blocker comment because approval is required and this run's approval
policy is `never`. Consequently, the live PR checkboxes remain unchanged. Apply
the verified checklist correction above and publish this protected follow-up
when GitHub writes are available. Keep the source issue open until the live
consumer acceptance is observed.

## Follow-up regression verification

The merge-scan harness now supports separate initial, final and merge-boundary
PR bodies. New cases verify that reopening a managed task or adding a reviewer
task only at the last boundary prevents the merge API request after the runtime
guard has passed. These cases assert the refusal summary and empty merged output;
the missing warning/receipt at that boundary remains the protected follow-up above.

Two further cases exercise failed updates to an existing owned refusal receipt at
the initial precheck and final snapshot. Both warnings remain visible, the attempted
update names the current head and reason, the previous receipt is preserved, and
no duplicate comment or merge request is made.

Validation for this follow-up:

- `node .github/scripts/__tests__/guarded-merge-tasks.test.js`: 39 passed.
- `node --test --test-isolation=none .github/scripts/__tests__/guarded-merge-tasks.test.js`:
  39 passed, with no skipped or TODO cases.
- `node --test .github/scripts/__tests__/guarded-merge-tasks.test.js`: passed.
- In a temporary test copy, the loaded workflow source was deliberately mutated to
  add raw issue checkbox counts to `uncheckedTaskFailure`: 21 failures, including
  the completed-PR regression. Restoring the source produced 39 passes. No workflow
  file was edited during this experiment.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/workflows/test_workflow_agents_consolidation.py -q -m 'not slow'`:
  79 passed in 1.95 seconds.
- `node --test .github/scripts/__tests__/` still fails with `MODULE_NOT_FOUND`.
- `timeout 45s node --test --test-timeout=15000 .github/scripts/__tests__/*.test.js`
  reported failures in the unchanged `agents-verifier-context.test.js` and
  `generated-delivery-seal-action.test.js`, then timed out (exit 124). Full-suite
  acceptance remains unchecked.
- `git diff --check`: passed.

PR #4441 was verified open and ready for review. The connector again rejected the
requested `needs-human` label and blocker comment because approval is required
and the run's approval policy is `never`. No workflow file or PR checkbox was changed;
consumer deployment remains unverified.

The main checkout's Git metadata is read-only: staging fails when Git tries to
create `.git/index.lock`. This follow-up is committed in the isolated local checkout
`/tmp/pr4441-refusal-tests-checkout`, with a portable commit patch at
`/tmp/pr4441-refusal-tests.patch`. The main checkout retains the file edits but its
branch cannot advance under this run's filesystem permissions.

## Source snapshot refusal regressions

Reviewed the source and keepalive commits through `97538302` and confirmed the
checklist above: the final merge-boundary warning/receipt remains missing, while
the workflow consolidation acceptance has verified passing evidence. No additional
task is complete. The live PR remains open and ready for review.

Four new merge-scan cases cover a source issue read failure or missing version at
the initial scan and final snapshot. Even with all PR tasks complete, each case
requires the specific refusal warning and current-head update of the writer's
existing receipt. A reviewer's receipt is preserved, no duplicate is created,
the summary retains the failure, and no merge or source-label cleanup is attempted.
The final-snapshot cases also establish that the runtime guard passed before
the source failure was observed.

Validation:

- `node --test --test-isolation=none .github/scripts/__tests__/guarded-merge-tasks.test.js`:
  43 passed, zero skipped or TODO cases.
- In a temporary test copy, changing the in-memory workflow source to count raw
  issue boxes produced 23 failures, including the completed-PR regression and
  both new final-snapshot cases. Restoring the original test produced 43 passes.
  No workflow file was edited.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/workflows/test_workflow_agents_consolidation.py -q -m 'not slow'`:
  79 passed in 1.99 seconds. The unmodified environment still fails during
  LangSmith plugin import on a Python 3.14 deprecation warning.
- The exact Node directory command still fails with `MODULE_NOT_FOUND`.
- A direct Node subprocess capture probe returns an `EPERM` spawn error and empty
  output. Process-isolated test-file summaries do not establish that individual
  tests ran in this sandbox. Full-suite acceptance remains unverified.
- `timeout 45s node --test --test-isolation=none --test-timeout=15000 .github/scripts/__tests__/*.test.js`:
  exit 124, with failures in existing verifier subprocess tests before timeout.
- JavaScript syntax validation and `git diff --check`: passed.
- GitHub rejected the requested checkbox reconciliation, `needs-human` label and
  blocker comment because writes require approval and approval policy is `never`.
  The remote checklist could not be corrected; the verified workflow consolidation
  acceptance remains recorded here.

The protected follow-up above is still required, as is deployed consumer evidence.
The main checkout's Git metadata remains read-only. This run retains its commit in
`/tmp/pr4441-source-refusal-checkout` and a portable commit patch in
`/tmp/pr4441-source-refusal.patch`; its working-file edits remain in the main checkout.

## Task-authority acceptance follow-up

Reviewed commits through `39b008d6`. The final merge-boundary publication gap still
requires an approved workflow edit; no additional checkbox can be completed.
The deliberate-break regression now restores raw-issue counting in
`uncheckedTaskFailure` using its supplied source snapshot, rather than changing
checkbox parsing globally. Two additional cases require source body and version
stability at the merge boundary even when PR tasks are complete.

Validation:

- `node --test --test-isolation=none .github/scripts/__tests__/guarded-merge-tasks.test.js`:
  45 passed, zero skipped or TODO cases.
- A temporary read interceptor restored raw-issue counting in the loaded workflow
  source: the named completed-PR regression failed with the unchecked-task refusal.
  Without the interceptor, the same named test passed. No workflow file was edited.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/workflows/test_workflow_agents_consolidation.py -q -m 'not slow'`:
  79 passed. Automatic plugin loading still fails on the installed LangSmith
  Python 3.14 deprecation warning.
- The exact Node directory command fails with `MODULE_NOT_FOUND`. The full-suite
  glob with process isolation disabled reported failures in existing verifier
  subprocess/archive tests and was interrupted (exit 130); it did not pass.
- `node --check` and `git diff --check`: passed.

GitHub rejected the verified workflow-suite checkbox correction, `needs-human`
label and blocker comment because approval is required and approval policy is
`never`. PR #4441 remains open and ready for review. Staging in the main checkout
also fails because `.git/index.lock` is read-only. The test and evidence changes
are preserved as a commit in `/tmp/pr4441-task-acceptance-checkout` and as
`/tmp/pr4441-task-acceptance.patch`; the working-file edits remain here.
