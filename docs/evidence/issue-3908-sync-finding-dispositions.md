# Issue 3908: sync finding relevance contract

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

The full two-file Node suite with `--test-isolation=none` executed 223 tests:
222 passed; the existing `Maint 68 verified unchanged-tree run resets producer
observation without changing lifecycle` test fails because this sandbox returns
`spawnSync bash EPERM`. The exact requested `node --test` command also fails in
this environment and reports only file-level results. Thus this run does not
claim that acceptance gate passed; it needs a rerun where child-process capture
works. No tests were skipped or disabled. GitHub access is also unavailable here,
so the implementation PR body could not be updated from this run.

This consistency repair does not clear shared-code blockers or add a campaign
#1836 prerequisite. The disposition-to-gate table above continues to apply.
