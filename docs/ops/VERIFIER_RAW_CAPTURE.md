# Verifier raw capture and bounded presentation

The expanded compare collector retains downloaded archives and decoded UTF-8
members separately from the report's bounded text. Artifact rendering remains
128,000 characters per archive and 4 MiB overall. Raw extraction uses the existing
64 MiB cumulative limit, independently of those presentation limits; archive,
entry, pagination and download bounds remain unchanged. Every occurrence consumes
extraction bytes, including byte-identical duplicates.

`VERIFIER_EVIDENCE_CAPTURE_DIR=verifier-evidence` is enabled by the source reusable
workflow for expanded recovery. Digest-addressed archives and member sidecars are
retained in `verifier-input-capture-RUN_ID` for seven days. The collector rejects
unsupported, ambiguous, malformed UTF-8/NUL, interrupted and over-budget inputs.
The loader verifies archive hash/length, member identity/order, ZIP CRC, sidecar
bytes/hash/length, UTF-8 and cumulative limits before recovering a presentation
omission. The snapshot byte inventory and semantic raw-input binding include
every retained member occurrence; a hash or a listing alone cannot recover it.
Missing or altered sidecars keep capture incomplete before provider invocation.

The first-party verifier input transport is distinct from its comparison result.
Automatic evidence discovery records that transport's identity but does not
recursively ingest its own input ZIPs. This applies only to the exact
`verifier-input-capture-RUN_ID` name from the authenticated first-party verifier
workflow path. Explicit references to that transport name or artifact ID retain
the normal inspection path; arbitrary workflow artifacts are not excluded.

Raw recovery is enabled only for expanded semantic compare. Expanded evaluate
and other legacy prompts keep a non-PASS floor when retained members were not
rendered into their actual prompt; validating sidecars cannot waive that floor.

Complete capture does not establish native capacity, provider acceptance or issue
completion. Every byte still belongs to the conservative all-input residual
unless a fixed, reviewed source rule binds the immutable capture and demonstrates
semantic closure. Native token-count preflight, the eight-package/sixteen-cell
and 1,200-second bounds, signed actual result matrix and non-PASS failures remain
in force. No native PASS is inferred from successful local capture tests.

## Original failure replay

Orchestrator #631 production run 38897681034 failed capture before either provider.
Its authentic coverage archive contains five members totaling 5,267,797 bytes;
the prior comparison archive has seven members totaling 264,116 bytes. The original
collector clipped both. The repaired collector retains and independently verifies
all 12 raw members (5,531,913 bytes) while leaving presentation honestly bounded.
All nine originally incomplete archives were then replayed: 39 members totaling
36,711,522 bytes retained and independently verified inside the unchanged 64 MiB
extraction ceiling. That replay establishes capture, not source #612 verification.

Validation: `node --test .github/scripts/__tests__/agents-verifier-context.test.js`
and `python3 -m pytest -q tests/tools/test_verifier_artifact_capture.py
tests/tools/test_verifier_capture_obligation_manifest.py
tests/scripts/test_pr_verifier_semantic_integration.py`. Raw-member tampering,
missing files, omitted occurrences, duplicate archives, corrupted archives and
cumulative overflow must fail before provider generation.


## Reviewed historical manual-run bindings

A manual verifier run's Actions `head_sha` identifies its wrapper, which can
legitimately differ from the verified implementation head. This does not permit
arbitrary mismatched-run evidence. Two historical first-party runs for
`stranske/Orchestrator#631` have source-reviewed immutable bindings in
`agents_verifier_context.js`. They require the exact repository IDs, PR/head and
merge, completed successful run/attempt 1, main wrapper path/SHA, reusable
producer SHA, artifact ID/name, authenticated API digest, downloaded ZIP hash,
and artifact workflow-run metadata. Missing or altered proof leaves capture
unavailable. All requested artifacts still pass ordinary pagination, download,
extraction and cumulative bounds; no failed historical result is upgraded.

| Run | Wrapper SHA | Actual executed Workflows SHA | Comparison artifact | SHA256 |
| --- | --- | --- | --- | --- |
| 38897681034 | a071ff06be16b969b50971678de75cb89d2978ab | 43096bff240b6fc5c89bb229f992a49a663fece4 | 12044188828 | 01740159fcb0216e4fb0309d082d5a48d488178e2e4c8c83288bcccabc459471 |
| 38979663956 | 143ce07ceacae5f4d973219f1267045133825aa7 | e015a93aaa27bc613a979a0e10329a7d9f84b0ed | 12080865906 | 931ae69b2cdfc8d2ce23e0cec92943dbefc26720b58a0ceb719d36b82bd3675b |

Both authentic manifests bind repository `stranske/Orchestrator`, PR631, merge
`a898f3b7227c61b73d1abe521e141e99173f85a5` and the exact source run. Their
context, diff-summary and full-patch hashes match their original archive members.
Authenticated Actions logs show the actual helper checkout SHAs above, rather
than inferring them from the mutable default branch or reusable YAML alone.
The original implementation head is
`aba5c4503a31f71e337e35e65d928124510bba22`.

The original collector rejects run38897681034 before retrieving its archive.
An independent replay with its authentic ZIP assertion-fails on that source;
the corrected collector captures all seven members (597,970 raw bytes), and
captures all seven members / 982,258 bytes of run38979663956. The committed
negative controls reject changed target, run, attempt, repository, producer,
artifact or digest. Neither original run invoked a provider: their incomplete
verification remains UNKNOWN, including the diagnostic bytes in the archives.
This narrow compatibility binding is not a general manual-run admission rule.
A future general receipt contract must independently establish immutable
producer and target identity; a workflow name, main branch or self-asserted
manifest alone is insufficient.
