# Issue 4435 acceptance reconciliation

PR: https://github.com/stranske/Workflows/pull/4439

Reviewed on 2026-11-04: implementation commit `5b2b85a6` and regression-test
commits `62d2475f`, `73c4cd3a`, `96cc711d`, `a265493d`, and `f37a92b3`. Current PR metadata
reports six changed files; the prompt's 34-file reconciliation warning does
not match that inventory.

## Verified acceptance

- [x] Both required named tests are present and pass in
  `.github/scripts/__tests__/scoped-canary-refresh.test.js`:
  `full-scope candidate refresh dispatches with the campaign source and plan id`
  and `delivery_contract_blocked with refresh-candidate-from-exact-plan is an eligible refresh request`.
- [x] Both required commands pass:
  `node --test .github/scripts/__tests__/scoped-canary-refresh.test.js` and
  `node --test .github/scripts/__tests__/maint71_merge_sync_prs.test.js`.
  Additional runs with `--test-isolation=none` verify the individual cases:
  scoped refresh 77 passed; Maint 71 173 passed; merge contract 103 passed.
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

Five additional refusal cases exercise the full-scope identity-blocked path
with an eligible report and a closed, draft, changed-head, untrusted-author, or
unsigned native candidate. Each verifies the named refusal, zero dispatches,
and unchanged pre-existing refresh accounting. The deliberate bare-dispatch
mutation was repeated and failed the required named test; the implementation
was restored byte-for-byte before the passing gate runs.

Two additional regressions verify that successful unkeyed full-scope history
for either the campaign source or newer main cannot suppress exact-plan
recovery, even when the rendered payload matches. A subsequent successful
receipt carrying the dispatched recovery key prevents another dispatch and
leaves `refresh_dispatched`, `held_plans`, and `drainable` unchanged.

The current round repeated the deliberate break and byte-for-byte restoration.
Both required gate commands passed; individual-case runs confirmed the counts
above. Local transcripts are `/tmp/issue-4435-deliberate-break.tap`,
`/tmp/issue-4435-scoped-cases.tap`, `/tmp/issue-4435-scoped-gate.tap`,
`/tmp/issue-4435-maint71-gate.tap`, `/tmp/issue-4435-maint71-cases.tap`, and
`/tmp/issue-4435-contract-cases.tap`.

## Protected workflow follow-up

`.github/workflows/maint-71-merge-sync-prs.yml` uploads
`sync-pr-merge-and-canary-evidence` in the step starting at line 675, before
`Refresh stale candidate bases` starts at line 688. The refresh step writes the
updated report at line 729. No subsequent step uploads that report again.
Consequently the retained merge-report artifact cannot expose accounting added
by this refresh step, even though the local report is updated correctly.

The script now publishes a `candidate refresh receipt:` notice and step-summary
line after a successful dispatch, with campaign source, plan ID, and the updated
`refresh_dispatched`, `held_plans`, and `drainable` counts. This provides live
dispatch evidence despite the earlier artifact upload. It does not establish
that refreshed canaries pass identity checks; post-merge acceptance stays open.
The three-canary regressions verify the exact receipt in both output channels
and its absence when a writer is active or dispatch fails. The successful-path
test failed before adding the receipt and passed afterward.

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

The prior round's five refusal tests and evidence update were committed by
automation in `a265493d`. This round again attempted the PR-body reconciliation,
`needs-human` label, and workflow-blocker comment; all three mutations were
rejected by the same approval restriction. PR #4439 remains open, unmerged,
and ready for review (`draft=false`). Post-merge observation remains blocked
on merge and the protected workflow artifact follow-up above.

The current round again could not apply the PR-body reconciliation, label, or
comment: each connector write returned the approval restriction above. The
intended PR body checks only the named-test, runnable-gate, and deliberate-break
criteria; both live criteria remain unchecked. PR #4439 was again confirmed
open, unmerged, and ready for review (`draft=false`).

Current validation: the required gate commands pass; individual-case runs pass
77 scoped-refresh, 173 Maint 71, and 103 merge-contract tests. The deliberate
bare-dispatch mutation failed the required named test with newer main `ffff…`
instead of campaign `aaaa…`, followed by byte-for-byte restoration and passing
gates. Transcripts: `/tmp/4439-receipt-red.tap`,
`/tmp/4439-deliberate-break.tap`, `/tmp/4439-scoped-green.tap`,
`/tmp/4439-maint-green.tap`, and `/tmp/4439-contract-green.tap`.

The requested commit is blocked by the filesystem: `git add` for the four
changed source, test, contract-doc, and evidence files failed with
`Unable to create '.git/index.lock': Read-only file system`. These changes
remain in the working tree for the automation commit step. No protected
workflow file was edited.
