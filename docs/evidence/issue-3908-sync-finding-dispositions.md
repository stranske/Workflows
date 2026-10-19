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
  220 tests passed, zero failures/skips.
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
