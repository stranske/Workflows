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
`sha256.json` covers the compressed captures and receipts, including the
five original focused and full consoles recovered below.

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
head, exact command and exit. The rebased console is in the [original transcript
recovery](#recover-the-focused-and-full-console-transcripts).
The earlier2028/2029 full-scope counts above are historical pre-rebase receipts,
not final-tree counts. No tested implementation bytes changed when adding this
receipt. Final staged/base diff checks pass.

### Recover the focused and full console transcripts

The original and current focused transcripts and the three full JavaScript
transcripts are preserved at their publishing revision. The other receipts and
both original hash manifests remain alongside this guide.

- [3770-focused.log.gz](https://github.com/stranske/Workflows/blob/00f43f81e51c4f8b9a057ac51f7e3c2d870d7769/docs/evidence/issue-3770/title-metadata-conflict/3770-focused.log.gz)
- [3770-current-focused.log.gz](https://github.com/stranske/Workflows/blob/00f43f81e51c4f8b9a057ac51f7e3c2d870d7769/docs/evidence/issue-3770/title-metadata-conflict/3770-current-focused.log.gz)
- [3770-full-js.log.gz](https://github.com/stranske/Workflows/blob/00f43f81e51c4f8b9a057ac51f7e3c2d870d7769/docs/evidence/issue-3770/title-metadata-conflict/3770-full-js.log.gz)
- [3770-current-full-js.log.gz](https://github.com/stranske/Workflows/blob/00f43f81e51c4f8b9a057ac51f7e3c2d870d7769/docs/evidence/issue-3770/title-metadata-conflict/3770-current-full-js.log.gz)
- [3770-rebased-full-js.log.gz](https://github.com/stranske/Workflows/blob/00f43f81e51c4f8b9a057ac51f7e3c2d870d7769/docs/evidence/issue-3770/title-metadata-conflict/3770-rebased-full-js.log.gz)

Run from a Workflows checkout. The command prints the verified temporary directory.

```bash
(
  set -e
  revision=00f43f81e51c4f8b9a057ac51f7e3c2d870d7769
  directory=docs/evidence/issue-3770/title-metadata-conflict
  if ! git cat-file -e "$revision^{commit}" 2>/dev/null; then
    git fetch --no-tags --depth=1 origin "$revision"
  fi
  recovered=$(mktemp -d "${TMPDIR:-/tmp}/title-metadata-console.XXXXXX")
  for name in 3770-focused.log.gz 3770-current-focused.log.gz 3770-full-js.log.gz 3770-current-full-js.log.gz 3770-rebased-full-js.log.gz; do
    git show "$revision:$directory/$name" > "$recovered/$name"
  done
  (
    cd "$recovered"
    shasum -a 256 -c <<'CHECKSUMS'
f9f6d090f23c8ec923cebaab183a21725be0f275fbe027776fefc2a4a603080f  3770-focused.log.gz
9bc0b2bd5706946eae45c2e6628ac7044c383c8f0e84bf836aebcfac19b00f3e  3770-current-focused.log.gz
12d3ecd89e35bf8b3cc59c61d8e31f668a195ab18175760e1c604f3ad4b912dd  3770-full-js.log.gz
7783935400e29c82a0b570120b1801b3e7c2eb42e13cd8c3d57a8ad6fb36526a  3770-current-full-js.log.gz
e2e36b6fc07da0c61b47d880578ccedcd3ab497993e89901206fef6cc87f7cd4  3770-rebased-full-js.log.gz
CHECKSUMS
  )
  printf '%s\n' "$recovered"
)
```
