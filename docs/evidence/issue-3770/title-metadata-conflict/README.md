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
each side. Console captures are losslessly gzip-compressed to preserve their
original bytes without trailing-whitespace diffs. `decoded-captures.json` retains
decoded names, lengths and SHA256; use `gzip -dc <capture.log.gz>` to read them.
These are executed production mutations, not a test-only mock.
`sha256.json` covers every retained compressed capture and receipt.

This bounded source repair does not complete the broader source3770 release
comparison follow-through. Original NON_PASS outcomes are retained. Keepalive
owns current-head CI/review; closer owns complete expected topology, unchanged
head, full review-thread evidence and seven-minute floor before merge/compare.
Orphan Steward then owns the repaired-input release3769/3787 comparisons, and
Maint71 owns generated consumer delivery qualification. No deployed claim.

## Review follow-through: negated titles

Review4202339183 identified `Does not fix #123` as a new false conflict. The
closing-reference parser now excludes immediate negative governors on the same
line, with bounded adverbs and contraction controls. A later affirmative closing
target still conflicts; a previous line's negation and positive `not only`
construction do not mask affirmative intent. Real root/template verifier builders
retain the known metadata contract for the negated title.

Current-head commands/exits are in `3770-current-validation.json`:183 focused
PASS;2,029 full JavaScript PASS,1 existing skip; template sync/strict completeness/
drift PASS. `3770-current-mutations.json` independently replays both defects on
both copies: four real incumbent-source REDexit1/candidate-restoredGREENexit0
controls with current source hashes. Current console captures use the same
lossless compression/manifests as the historical initial182/2028 receipts above.

## Concurrent-main synchronization

Before the review-fix push, main advanced to
`b4c5c6bb9` (merged3797). Rebased onto that main, preserved all current mutated
production-source hashes, then re-ran the complete JavaScript suite:2,057PASS,
1existingSkip,0failures. `3770-rebased-validation.json` records full base/tested
head, exact command and exit; raw console is `3770-rebased-full-js.log.gz`.
The earlier2028/2029 full-scope counts above are historical pre-rebase receipts,
not final-tree counts. No tested implementation bytes changed when adding this
receipt. Final staged/base diff checks pass.
