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
