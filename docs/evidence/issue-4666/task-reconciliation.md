# Issue 4666 verification

Verified on 2026-11-12 against the checked-out PR branch `orch/issue-4666`.
The classifier and recorded incident fixture were already implemented at the
start of this round. This round expands the JavaScript regression tests.

- [x] Classify Sync failures confined to `Create sync PR`, with every earlier
  step successful, as infrastructure; retain consumer classification otherwise.
- [x] Verify PR-creation, earlier-step, and second-consecutive-infrastructure
  regressions in `maint71_merge_sync_prs.test.js`.
- [x] The named PR-creation regression reports infrastructure and permits an
  immediate retry. It now also exercises the same explicit source-delta plan.
- [x] Replay freshly fetched jobs for run 43114630584 with the recorded source
  and candidates: diagnostics report infrastructure and the decision returns
  `eligible: true`. Prepare and all three Sync job step summaries match the
  committed fixture. The failed job's log confirms the reported GraphQL rate
  limit during PR creation.
- [x] The named earlier-step regression reports consumer and withholds retry.
  Additional cases verify missing steps, unsuccessful earlier steps, and a
  second failure after PR creation preserve this hold.
- [x] The existing second-consecutive-infrastructure regression passes,
  including added cases for two PR-creation failures and mixed Prepare and
  PR-creation failures in either order.
- [x] Temporarily restoring `if (syncStarted) return 'consumer';` ahead of the
  exception makes the named PR-creation regression fail with actual `consumer`
  and expected `infrastructure`. The deliberate break was reverted, and the
  classifier has no diff against the starting commit.

Validation after reverting the deliberate break:

```sh
node --test --test-isolation=none --test-reporter=tap .github/scripts/__tests__/maint71_merge_sync_prs.test.js
git diff --check
```

Results: 244 tests passed, zero failures, zero skipped; no whitespace errors.
No Python or workflow files were changed.

Live evidence:

- [Incident run](https://github.com/stranske/Workflows/actions/runs/43114630584)
- [Failed Sync job](https://github.com/stranske/Workflows/actions/runs/43114630584/job/130839840005)

## Handoff limitation

The requested commit could not be created: `git add` failed because `.git` is
read-only and Git could not create `.git/index.lock`. The GitHub PR-body update
was also blocked because the tool requires approval and the environment's
approval policy is `never`. The remote checkboxes remain unchanged. PR 4667
was confirmed open and ready for review (`draft: false`). The source test
changes and this verification record remain in the working tree for the
authorized automation to commit and reconcile.
