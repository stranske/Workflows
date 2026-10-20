# Issue 3908: sync finding relevance contract

## Explicit completeness follow-up

An active-debt packet without `evidenceComplete` previously passed pre-seal
while canary validation rejected it. Active-debt evaluation now requires the
boolean `true`; missing, false, null, numeric and string values block. Legacy
zero-debt reads still require no exemption. Counts and unresolved findings remain
visible, and the disposition-to-gate table below continues to apply.

`active finding exemptions require explicit complete evidence at pre-seal and canary`
failed before the fix with `ERR_ASSERTION` for the missing flag. It now passes,
along with `promotion holds active finding snapshots without explicit completeness`.
The exact required two-file Node command exits 0; adding
`--test-isolation=none --test-reporter=tap` executes **232 named tests, all passing
with zero failures or skips**.

Both required deliberate-break proofs were repeated on this implementation:
`sync finding unknown fails closed and mixed findings retain every blocker`
and `stale-head final sync finding gate rejects an unrelated record after pre-seal`
each failed by assertion with exit 1 under its specified mutation. Each passed
with exit 0 after SHA-256-verified exact-byte restoration. Neither mutation is
shipped. This correction neither clears current shared-code blockers nor adds
a campaign #1836 prerequisite.

The promotion receiver also passes: `python -m pytest
tests/scripts/test_select_consumer_sync_phase.py -q -m 'not slow' -o addopts=`
(22 passed). `git diff --check` passes. PR #4144 is open and ready for review.
Staging the source/test changes failed because `.git/index.lock` cannot be
created on the read-only filesystem, so this follow-up remains uncommitted.
Updating the PR body with the named proofs and disposition table was rejected:
`MCP tool call requires approval, but approval policy is never`. The prepared
body is retained at `/tmp/sync-pr-4144-body.md`; the remote body is unchanged.

Implemented one source-owned evaluator and consumed it at Maint 71 pre-seal,
final merge, canary validation/recovery, and Maint 68's promotion receiver. An
authenticated owner classification is a causal assessment, not originating
reviewer acceptance. Raw active findings and exact identities remain visible.

| Finding/evidence | Pre-seal | Final merge relevance | Canary |
| --- | --- | --- | --- |
| Shared-source defect | Block | Block | Block |
| Sync-caused incompatibility in unmanaged path | Block | Block | Block |
| Unrelated, exact binding, trusted author, live assigned local issue | Pass relevance | Pass relevance | Pass relevance |
| Unknown, absent or malformed evidence | Block | Block | Block |
| Unrelated plus any shared/sync-caused/unknown finding | Block | Block | Block |
| Stale head/source/plan/generation, edited finding, expired record | Block | Block after live reread | Block |
| Lost/unassigned/deleted/unreadable local handoff | Block | Block | Block |

Required checks, approvals, delivery integrity, security and repository
conversation policy remain independently enforced. No thread is auto-resolved,
no bypass is added, no consumer repository is modified, and no campaign is
opened or expanded. This does not clear the pre-existing shared-code findings.

## Executed validation

- `node --test .github/scripts/__tests__/sync_pr_merge_contract.test.js .github/scripts/__tests__/maint71_merge_sync_prs.test.js`:
  221 tests passed, zero failures/skips. `classifyReviewBlockedDisposition`
  now surfaces `raw_active_count`, per-disposition thread IDs, and
  blocking/nonblocking/unknown aggregates on every blocked return.
- `node --test .github/scripts/__tests__/*.test.js`: 2,554 passed, zero failures,
  one existing skipped test (2,555 total).
- `python -m pytest tests/scripts/test_select_consumer_sync_phase.py -q`:
  18 passed, including the actual Node contract receiver, changed-head/lost-owner
  rejection and missing-Node fail-closed behavior.
- `python -m mypy scripts/select_consumer_sync_phase.py`: pass.
- Ruff and Black (Python 3.12 target) on the two touched Python files: pass.

The final executed counts after any subsequent native change must be read from
that exact revision's CI. These are local implementation proofs, not observed
hosted delivery, merge, promotion or original-source acceptance.

## Actual deliberate-break proofs

1. In `evaluateSyncFindingDispositions`, temporarily changed the aggregate
   blocking filter to include only `shared-source` and `sync-caused`, thereby
   accepting `unknown` records. Ran:

   ```sh
   node --test --test-name-pattern='sync finding unknown fails closed' .github/scripts/__tests__/sync_pr_merge_contract.test.js
   ```

   The named regression exited **1** with an assertion failure. Restored the
   exact file bytes; the same command exited **0**.

2. In the actual final-boundary helper `confirmExactHeadSyncFindingGate`,
   temporarily returned unconditional acceptance after collecting an unrelated
   record instead of consuming the validated, current-head evaluation. Ran:

   ```sh
   node --test --test-name-pattern='stale-head final sync finding gate' .github/scripts/__tests__/maint71_merge_sync_prs.test.js
   ```

   The named stale-head regression exited **1** with an assertion failure.
   Restored the exact file bytes; the same command exited **0**.

Neither mutation is shipped. SHA-256 restoration checks passed for both files.
The complete focused and Node suites were run on the restored implementation.

## Promotion-payload review repair

The complete live finding and handoff snapshots remain in the executor artifact.
Promotion transports only evaluator fields: each review body becomes its SHA-256
content digest with immutable comment identity/author/update metadata; handoff
issue bodies, long titles and unrelated API metadata are omitted. The same
fingerprint and binding validation consume the compact packet. Owner protocol
records remain intact; a packet over 16,000 UTF-8 bytes is explicitly incomplete.
The complete dispatch input object has a separate 60,000-byte pre-network gate.

A regression uses a large Unicode discussion and large handoff body/title/API
objects: valid compact evidence remains below 4,000 bytes and still passes the
shared validator. Replacing the actual promotion-builder compaction with raw
snapshots makes that regression fail (exit 1); exact restoration passes (exit 0).
Oversized owner records and aggregate inputs are held before any API call. All
three deliberate-break proofs were repeated on the final implementation.

## Zero-count evidence consistency follow-up

Canary validation previously skipped its attached finding packet when the raw
count was zero. Maint 68's receiver had the same shortcut, and the promotion
builder dropped explicit null packets. All three boundaries now preserve and
validate attached evidence even at zero. Active findings, null/malformed packets
and incomplete snapshots block; complete empty snapshots and legacy zero-debt
rows without a packet pass. The original finding remains unresolved.

The two named Node regressions failed before the fix and pass after it:

- `canary zero count cannot mask active or incomplete disposition evidence`
- `promotion rejects a zero count that contradicts its active finding packet`

The receiver regression
`test_promotion_rejects_zero_count_with_attached_invalid_finding_evidence`
failed for all four fixtures before its fix. The complete receiver suite now
passes: `python -m pytest tests/scripts/test_select_consumer_sync_phase.py -q
-m 'not slow' -o addopts=` (22 passed). Ruff and mypy pass for the changed surface.
The required repository-wide `black --check --line-length 100 --exclude
'(\.workflows-lib|node_modules)' .` passes (820 files), using a writable
`BLACK_CACHE_DIR` under `/tmp` and `BLACK_NUM_WORKERS=1` for this sandbox.

Both required mutation proofs above were repeated with
`--test-isolation=none`: each named test failed by assertion with exit 1 under
its mutation and passed with exit 0 after byte-for-byte restoration. Neither
mutation is included. The 12 focused relevance/disposition tests also pass.

Before the subprocess repair below, the full two-file Node suite with
`--test-isolation=none` executed 223 tests:
222 passed; the existing `Maint 68 verified unchanged-tree run resets producer
observation without changing lifecycle` test fails because this sandbox returns
`spawnSync bash EPERM`. The exact requested `node --test` command also fails in
this environment and reports only file-level results. Thus this run does not
claim that acceptance gate passed; it needs a rerun where child-process capture
works. No tests were skipped or disabled. GitHub access is also unavailable here,
so the implementation PR body could not be updated from this run.

This consistency repair does not clear shared-code blockers or add a campaign
#1836 prerequisite. The disposition-to-gate table above continues to apply.

## Subprocess capture repair and acceptance reconciliation

The existing unchanged-tree lifecycle test now awaits asynchronous `execFile`
instead of using `execFileSync`. It still executes the extracted Maint 68 Bash
fragment for both `FORCE=false` and `FORCE=true`, propagates subprocess failures,
and asserts the same producer observation, lifecycle and signed-regeneration
behavior. No workflow or production gate changed.

Validation on the repaired test:

- The exact required two-file `node --test` command exits **0**. This sandbox's
  default reporter counts two passing file-level tests.
- Adding `--experimental-test-isolation=none --test-reporter=tap` to that command
  exposes the individual assertions: **223 tests passed, zero failed or skipped**.
- `sync finding unknown fails closed and mixed findings retain every blocker`:
  unknown-as-nonblocking mutation exits **1** with `ERR_ASSERTION`; exact-byte
  restoration exits **0** (one executed test).
- `stale-head final sync finding gate rejects an unrelated record after pre-seal`:
  unconditional unrelated acceptance at the final boundary exits **1** with
  `ERR_ASSERTION`; exact-byte restoration exits **0** (one executed test).

Neither mutation is shipped. All seven implementation tasks remain verified;
the previously failing command acceptance gate now passes locally. Updating
PR #4144's body was attempted during reconciliation, but the GitHub connector
requires approval while this run's approval policy is `never`. Its existing
checked tasks therefore remain unchanged remotely. Hosted CI/review and
post-merge acceptance are still separate from these local proofs.

## Pre-seal replay rejection follow-up

Reconciliation of the recent commits confirmed all task checkboxes were already
checked, but a new regression exposed an incomplete provenance boundary:
`classifyGeneratedPr` evaluated a packet against its own binding. An internally
valid old-head unrelated packet could therefore classify a changed delivery as
`current` before sealing. It now derives the expected binding from the selected
PR and delivery record, matching the final collector and canary validator.

`pre-seal rejects an internally valid unrelated packet replayed onto another delivery`
failed before the repair with `head_sha: reject replay before sealing`
(`current` instead of `review-blocked`). It now passes for changed head, PR,
repository, source, plan and generation, while the unchanged controls pass.
`a changed delivery head requires renewed unrelated evidence at every review boundary`
also verifies that all three boundaries block old-head evidence and accept a
renewed trusted classification without resolving the original finding.

Validation after restoration of both required deliberate mutations:

- The exact required two-file `node --test` command exits **0** (two file-level
  passes in this sandbox). With `--test-isolation=none --test-reporter=tap`,
  **225 named tests pass, zero failures or skips**.
- `python -m pytest tests/scripts/test_select_consumer_sync_phase.py -q
  -m 'not slow' -o addopts=`: **22 passed**.
- The named `sync finding unknown fails closed and mixed findings retain every blocker`
  regression exits **1**, `ERR_ASSERTION`, under the unknown-as-nonblocking
  mutation, and **0** after exact-byte restoration.
- The named `stale-head final sync finding gate rejects an unrelated record after pre-seal`
  regression exits **1**, `ERR_ASSERTION`, under unconditional unrelated
  acceptance at the final finding gate, and **0** after exact-byte restoration.
- `git diff --check`: pass. Neither deliberate mutation is shipped.

PR #4144 was verified open and ready for review. Its body reconciliation was
attempted, but the GitHub write tool returned: `MCP tool call requires approval,
but approval policy is never`. The remote body remains unchanged; this section
records the current local evidence. The disposition-to-gate table above still
applies. This correction does not clear shared-code blockers or add a campaign
#1836 prerequisite.

## Mixed-finding orchestration follow-up

Reconciliation found all 16 live PR checkboxes already checked. The existing
mixed-finding tests exercised the shared evaluator, while the orchestration
agreement test exercised each disposition separately. Three new named tests in
`maint71_merge_sync_prs.test.js` now exercise an unrelated finding together with
each blocking disposition through pre-seal, final merge and compact canary
promotion evidence:

- `mixed unrelated and shared-source findings block every review boundary`
- `mixed unrelated and sync-caused findings block every review boundary`
- `mixed unrelated and unknown findings block every review boundary`

Each retains two unresolved findings, the raw count, the exact blocking/unknown
identities and the validated local handoff. The sync-caused case uses an unmanaged
consumer path. Promotion fails specifically for active review debt; the complete
fixture has no missing required metadata. Compact evidence preserves the same
aggregates and handoff references as the final evaluation.

The exact required two-file `node --test` command passes. With
`--test-isolation=none --test-reporter=tap`, **228 named tests pass, zero failures
or skips**. Both required deliberate-break proofs were repeated: the named
unknown-fail-closed and stale-head final-merge tests each fail with
`ERR_ASSERTION` (exit 1) under the specified mutation and pass (exit 0) after
byte-for-byte restoration. Neither mutation is included. `git diff --check`
passes. Only JavaScript tests and this evidence record changed.

PR #4144 remains open and ready for review. Updating its body with the current
test count and disposition-to-gate table was rejected because the GitHub tool
requires approval while this run's approval policy is `never`. The existing
checked tasks remain unchanged remotely. This coverage does not clear current
shared-code blockers or create an additional campaign #1836 prerequisite.

One overlapping two-file suite invocation failed the existing `seal recovery
seal_drained preserves real check blockers` test while both processes shared
`artifacts/sync-canary-evidence.json`. A sequential rerun passes all 228 named
tests; these suites must not run concurrently in the same working directory.
The local commit attempt failed because `.git/index.lock` cannot be created on
the read-only filesystem. The changes remain uncommitted in the working tree.
## Canary snapshot provenance follow-up

The previous canary validator replaced an attached packet's binding with the
row's identity before evaluating it. A complete empty snapshot from another
delivery could therefore pass at zero review debt. The validator now requires
a complete row binding and an exact packet match for repository, PR, head SHA,
source commit, plan and generation before evaluating any attached snapshot.
Legacy zero-debt rows without a packet retain their existing behavior.

Two new regressions failed with `ERR_ASSERTION` before the repair and pass after it:

- `canary packet provenance must match its row even with zero review debt`
  covers full and compact packets, zero and nonzero debt, all six binding fields,
  missing bindings, and matching but malformed identities.
- `promotion rejects a finding snapshot replayed across deliveries with zero review debt`
  covers the actual promotion builder and preservation of the original packet
  binding and raw count, with legacy zero-debt controls.

Validation: the exact required two-file `node --test` command exits 0 (two
file-level passes in this sandbox). Adding `--test-isolation=none
--test-reporter=tap` executes **230 named tests, all passing with no skips**.
`python -m pytest tests/scripts/test_select_consumer_sync_phase.py -q
-m 'not slow' -o addopts=` passes **22 tests**.

Both required deliberate-break gates were repeated. The named
`sync finding unknown fails closed and mixed findings retain every blocker`
and `stale-head final sync finding gate rejects an unrelated record after pre-seal`
tests each exit 1 with `ERR_ASSERTION` under the specified mutation and exit 0
after SHA-256-verified byte restoration. Neither mutation is shipped.

PR #4144 was verified open and ready, with all 16 existing checkboxes checked.
The reconciliation update was rejected because the GitHub tool requires approval
and this run's approval policy is `never`; its remote body remains unchanged.
The disposition table above still applies. This fix does not clear shared-code
blockers or add a campaign #1836 prerequisite.
