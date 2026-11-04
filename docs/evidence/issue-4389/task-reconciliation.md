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

The main checkout's Git metadata is read-only: staging fails when Git tries to
create `.git/index.lock`. The changes are therefore committed in the isolated
local checkout `/tmp/pr4441-review-checkout`, with a portable commit patch at
`/tmp/pr4441-task-authority.patch`. The main checkout retains the file edits but
its branch cannot advance under this run's filesystem permissions.
