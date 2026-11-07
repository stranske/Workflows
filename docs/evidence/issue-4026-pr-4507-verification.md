# Issue 4026 / PR 4507 verification

Check date: 2026-11-07 (UTC).
Verified source head: `7766db254174773278f673321c40e2fb3f78378f`.

Operational outcome: one successful post-merge Maint 68 promote within 24 hours
of merge. Readback command:

```sh
gh run list -R stranske/Workflows --workflow maint-68-sync-consumer-repos.yml --limit 100 --json databaseId,displayTitle,conclusion,createdAt
```

This remains unproven until a real run is compared with the PR's `mergedAt`.
The first post-merge Maint 71 run must also supply real canary counts. Local
mock summaries and pre-merge workflow runs do not satisfy either criterion.
Workflow scheduling remains controller-owned.

## Local verification

Each attempt was bounded to two minutes; allow one exact-failure correction
and rerun, then stop at the first unresolved failure. No correction was needed.

1. `node --test .github/scripts/__tests__/maint71_merge_sync_prs.test.js`
   printed `tests 207`, `pass 207`, `fail 0`, exit 0 (608.660416 ms).
2. Temporarily replaced only the `checks_failed` return in `canaryNeedsRefresh`
   with `null`, then ran:

   ```sh
   node --test --test-name-pattern='one checks_failed canary' .github/scripts/__tests__/maint71_merge_sync_prs.test.js
   ```

   Exit 1, `tests 1`, `pass 0`, `fail 1` (106.475 ms). Named failure:

   ```text
   one checks_failed canary among green siblings dispatches once and waits for its writer
   AssertionError [ERR_ASSERTION]: missing refresh dispatch: checks_failed
   0 !== 1
   ```

3. Restored the entire source file byte-for-byte from the pre-mutation bytes
   (`RESTORED_BYTE_IDENTICAL=True`), then reran the full targeted command from
   step 1: `tests 207`, `pass 207`, `fail 0`, exit 0 (563.405958 ms).

The mutation is excluded from commits. The retained implementation was unchanged.

## Delivery readback before evidence push

At 2026-11-07T06:31:31Z the existing exact-head Gate run `42330294402`
was still in progress. Its `github scripts tests` job `128275239006`
started the Node test step at 02:40:54Z and had not advanced. Other reported
non-skipped checks passed. Review threads were empty (complete first page).
The remote-only merge guard refused before issuing a merge command because
merge state was blocked. A cancellation request was submitted for this stalled
CI run; no merge gate or review floor was bypassed.

Post-push CI, review, guarded merge and operational acceptance require fresh
readback. This receipt establishes local regression evidence only.

## Sibling recovery continuation

Reviewed commits through `8dd78c0e`. Upstream synced-file review routing and
per-run canary counts are implemented. The remaining dispatch gap selected only
one recovery key per plan, allowing its consumed receipt to hide a sibling's
new blocker. The refresh pass now examines each blocked sibling's recovery key
and stops after the first dispatch across all plans. Plan binding, unreadable-tip
holds, active-writer guards and consumed recovery receipts remain enforced.

Four new regression cases cover `behind`, `checks_failed`, `review_blocked` and
`stale`. Before the fix, all four failed with state-specific missing-sibling
dispatch assertions. After the fix, each case verifies one additional dispatch,
no dispatch while its writer is queued, and no repeated dispatch after success.

Validation on the retained source:

```sh
node --test --test-isolation=none --test-reporter=tap .github/scripts/__tests__/maint71_merge_sync_prs.test.js
```

Exit 0; 216 tests, 216 pass, 0 fail. Explicit test isolation is required in this
runner to expose the individual tests; the plain command reports one file wrapper.
Temporarily returning `null` only for `checks_failed` and running the same command
with `--test-name-pattern='one checks_failed canary'` exited 1: 1 test, 0 pass,
1 fail, naming `one checks_failed canary among green siblings dispatches once and
waits for its writer` with `missing refresh dispatch: checks_failed` (`0 !== 1`).
The source was restored byte-for-byte, then the full suite again passed all 216
tests. The mutation is excluded from the commit.

The GitHub PR-body update was denied because its tool requires approval and the
run's approval policy is `never`. The reconciled replacement body is prepared at
`/tmp/issue-4026-pr-body.md` in the run workspace. It checks the verified local
implementation and acceptance items while leaving both operational criteria open.
No post-merge Maint 71 counts or qualifying Maint 68 promotion are established by
these local tests.

The checkout's `.git` directory is read-only, so staging and committing in the
original checkout are blocked. The change is committed in a writable temporary
clone and exported to `/tmp/issue-4026-sibling-recovery.patch` for handoff.
