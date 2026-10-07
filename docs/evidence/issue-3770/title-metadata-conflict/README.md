# Explicit closing-title / metadata conflicts

Base: `72611afbe75b34b9145b8469dddb15c35ac3cfef`.

The public resolver previously selected issue456 for title `Fixes #123` plus
`<!-- meta:issue:456 -->`. The early single-marker return bypassed the existing
explicit-title conflict check. Reject only differing explicit closing-title
targets, setting the existing ambiguous/closing state; choose neither source.
A local-request declaration and stale issue branch cannot conceal this conflict.

The real verifier builder, exercised in root and template, keeps required
acceptance discovery unavailable even if closing discovery already returned the
stale metadata issue. Matching title/metadata targets and metadata with no closing
title continue fetching the known source; synchronized body closing references
remain subordinate to the single metadata binding. Existing historical release
3769/3787, genuine closing, ambiguity and malformed-source controls are retained.

Validation commands and process exits are in `3770-validation.json`:

- `node --test .github/scripts/__tests__/source-context.test.js .github/scripts/__tests__/agents-verifier-context.test.js`:182 passed.
- `node --test .github/scripts/__tests__/*.test.js`:2,028 passed,1 existing skipped,0 failed.
- `bash scripts/sync_templates.sh`, strict template completeness and template drift:exit0.
- Both source/context template comparisons and `git diff --check`:exit0.

`3770-mutations.json` contains the exact selected-test command and source hashes.
For each of root and template, replace only that resolver with the incumbent base
bytes: the conflict assertions fail (exit1). Restore the exact candidate bytes:
the same command passes (exit0). Raw console logs are retained independently for
each side. These are executed production mutations, not a test-only mock.
`sha256.json` covers every retained capture.

This bounded source repair does not complete the broader source3770 release
comparison follow-through. Original NON_PASS outcomes are retained. Keepalive
owns current-head CI/review; closer owns complete expected topology, unchanged
head, full review-thread evidence and seven-minute floor before merge/compare.
Orphan Steward then owns the repaired-input release3769/3787 comparisons, and
Maint71 owns generated consumer delivery qualification. No deployed claim.
