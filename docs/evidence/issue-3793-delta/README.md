# Changed-tree attempt-presence recovery (source #3793)

The merged #3792 v1 inventory avoided rescans only while the attempt subtree was unchanged. Its retained 1,001-index fixture performed another 1,002 historical blob reads after one older writer added an index (2,003 cumulative). This follow-up preserves migration and freshness fences while introducing a v2 per-entry filename/blob-SHA/PR manifest and one conditional checkpoint pointer.

Validation used Node v24.3.0 and simulated durable GitHub storage; no production API load or authority writes occurred. Independent Node child processes invoke production reporter defaults, sharing only the parent server's durable state. Bootstrap reads 1,001 blobs; each of three successive older-writer additions reads exactly one blob; a two-entry batch reads exactly two. Positive presence with missing ledger still rejects. Replacements revalidate one changed blob, removals recompute membership without reading historical blobs. Warm calls remain bounded to at most18 in the production-default fixture (prior bound15 gains checkpoint/manifest validation); total metadata and manifest bytes remain O(N).

The 113-test focused run covers source and template, complete-tree checks, legacy receipt reconciliation, independent processes, malformed mappings, same-positive-set mapping conflict, missing expected checkpoint, positive/negative concurrency fences, stale checkpoint CAS loss, partial delta and lost publication/checkpoint responses. These are focused results, not the repository's entire suite or deployed acceptance.

Exact command:

```sh
node --test .github/scripts/__tests__/keepalive-authority-state.test.js .github/scripts/__tests__/keepalive-attempt-presence.test.js .github/scripts/__tests__/keepalive-presence-delta.test.js .github/scripts/__tests__/keepalive-reporter-applicability.test.js
```

Actual source mutation disabled the immutable filename/blob-SHA reuse branch on both source and template. The separate-process regression failed twice at `1002 !== 1`, rather than at setup/import. Exact bytes were restored in a finally block; the full113 focused tests then passed. `mutation.json`, `mutant-red.txt` and `restored-green.txt` retain hashes, exit states and full console output.

Template sync/completeness and diff whitespace passed. No new rollout, fleet protection, original-provider PASS, source issue closure or expected-check waiver is claimed. Source#3793 remains open until this follow-up's exact-head CI/review gates, guarded squash merge, actual verify:compare and report disposition.
