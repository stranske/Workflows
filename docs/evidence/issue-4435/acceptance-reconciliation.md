# Issue 4435 acceptance reconciliation

PR: https://github.com/stranske/Workflows/pull/4439

Reviewed on 2026-11-04: implementation commit `5b2b85a6` and regression-test
commits `62d2475f` and `73c4cd3a`. Those commits changed five distinct files;
the prompt's 33-file reconciliation warning does not match the PR metadata.

## Verified acceptance

- [x] Both required named tests are present and pass in
  `.github/scripts/__tests__/scoped-canary-refresh.test.js`:
  `full-scope candidate refresh dispatches with the campaign source and plan id`
  and `delivery_contract_blocked with refresh-candidate-from-exact-plan is an eligible refresh request`.
- [x] Both required commands pass:
  `node --test .github/scripts/__tests__/scoped-canary-refresh.test.js` and
  `node --test .github/scripts/__tests__/maint71_merge_sync_prs.test.js`.
  Additional runs with `--test-isolation=none` verify the individual cases:
  scoped refresh 70 passed; Maint 71 173 passed; merge contract 103 passed.
- [x] Deliberate break and restoration: temporarily reinstated the bare
  full-scope `dispatchCanaryRefresh` call before the campaign-bound path.
  The first required named test failed with current-main `ffff…` instead of
  campaign source `aaaa…`. Restored the source in a `finally` block and reran
  both suites successfully. No deliberate break remains in the working tree.
- [ ] Post-merge/live: observe a dispatch receipt with `refresh_dispatched >= 1`
  and all three canaries passing immutable identity into review/seal. PR #4439
  was open, unmerged, and ready for review when inspected; local mocks cannot
  establish this acceptance criterion. No production dispatch was issued.

The workflow-caller regression now invokes the real eligibility and refresh
adapters with an identity-blocked candidate, rather than a no-op dispatcher.
It verifies the campaign source/plan sent to Maint 68 and the report path and
serialized `refresh_dispatched`, `held_plans`, and `drainable` values after
dispatch. Native API observations and dispatches are inert test adapters.

## Protected workflow follow-up

`.github/workflows/maint-71-merge-sync-prs.yml` uploads
`sync-pr-merge-and-canary-evidence` in the step starting at line 675, before
`Refresh stale candidate bases` starts at line 688. The refresh step writes the
updated report at line 729. No subsequent step uploads that report again.
Consequently the retained merge-report artifact cannot expose accounting added
by this refresh step, even though the local report is updated correctly.

An approved `agent-high-privilege` run must move the report upload after the
refresh step while preserving the upload-success prerequisite for promotion,
or add a separate final report artifact after refresh. Preserve existing
canary evidence, campaign authorization, and promotion checks. This standard
run did not edit workflow files.

## Remote tracking limitation

The GitHub connector rejected the PR-body reconciliation, `needs-human` label,
and blocker-comment writes with:
`MCP tool call requires approval, but approval policy is never`.
Those remote updates were not applied. The checked items above are verified
local evidence to reconcile into the PR body; live acceptance remains open.
Capacity mode: `local-only` for mutations; connector reads remain available.
