### Keepalive: OFF
<!-- meta:issue:662 -->

### Source Issue #662: Follow-up: Reject prohibited publication content inside compressed DOCX artifacts

Base: main
Head: codex/issue-662

Source: https://github.com/stranske/Ready/issues/662

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
Source issue #620 was implemented by merged PR #634, but the post-merge verifier did not pass (CONCERNS). closer-core's disposition: The literal required pytest command is documented as failing, so at least one acceptance criterion is clearly unmet..

<!-- Updated WORKFLOW_OUTPUTS.md context:start -->
## Context for Agent

### Related Issues/PRs
- [stranske/Ready#620](https://github.com/stranske/Ready/issues/620)
- [#620](https://github.com/stranske/Ready/issues/620)
- [#634](https://github.com/stranske/Ready/issues/634)
<!-- Updated WORKFLOW_OUTPUTS.md context:end -->

#### Tasks
- [x] `pytest tests/test_publication_safety.py tests/test_prepare_publication.py` passes, including a compressed DOCX whose raw bytes match no rule but whose text does, and a split-run marker, both exiting 1.

#### Acceptance criteria
- [x] `pytest tests/test_publication_safety.py tests/test_prepare_publication.py` passes, including a compressed DOCX whose raw bytes match no rule but whose text does, and a split-run marker, both exiting 1.

<!-- auto-status-summary:end -->

<details>

<summary>Full Issue Text</summary>



<!-- closer-core/v1 followup-of=stranske/Ready#620@634 -->
## Why
Source issue #620 was implemented by merged PR #634, but the post-merge verifier did not pass (CONCERNS). closer-core's disposition: The literal required pytest command is documented as failing, so at least one acceptance criterion is clearly unmet..

## Scope
- `pytest tests/test_publication_safety.py tests/test_prepare_publication.py` passes, including a compressed DOCX whose raw bytes match no rule but whose text does, and a split-run marker, both exiting 1.

## Non-Goals
- Do not redo work that PR #634 already delivered.

## Tasks
- [x] `pytest tests/test_publication_safety.py tests/test_prepare_publication.py` passes, including a compressed DOCX whose raw bytes match no rule but whose text does, and a split-run marker, both exiting 1.

## Acceptance Criteria
- [x] `pytest tests/test_publication_safety.py tests/test_prepare_publication.py` passes, including a compressed DOCX whose raw bytes match no rule but whose text does, and a split-run marker, both exiting 1.

## Implementation Notes
Verifier report (excerpt):

```
 the code may have landed in earlier commits or on another path.; The PR's own evidence says the literal command `pytest tests/test_publication_safety.py tests/test_prepare_publication.py` exits 1 because inherited `--cov=src` coverage measures the unrelated scaffold at 0%. The first acceptance criterion is nonetheless checked in the PR body. `keepalive-reconciliation.md` says that checkbox needs reopening, and the PR body says no standalone coverage PASS is claimed. This is an acknowledged, unresolved mismatch with the literal criterion.; The regenerated DOCX files (Workflows, 00-PERSONAL-REUSE-NOTE, Fine-Art-Archive) are not in this diff. The receipt says they were pushed directly to the engine mirror, bypassing the expected Gate context. The criterion that the repo-wide guard exits 0 after regeneration rests on receipts (`620-mirror-guard.txt`, `620-publication-receipt.json`) that cannot be checked against the diff.; The deliberate-break transcripts (`docx-decoder-break.txt`, `character-reference-red-green.txt`) show RED with the decoder disconnected and GREEN after restoration, so that deliverable is present. They cannot be tied to the actual guard code from this diff.; Some PR comments and workflow artifacts were truncated or unavailable, so the review could not fully inspect them.; Verifier input coverage incomplete; PASS withheld: files not reviewed: tests/test_publication_safety.py, README.md; The supplied diff does not include tests/test_publication_safety.py or README.md. The committed RED/GREEN transcripts show those tests running, but this review could not read them or the README:64 update directly.; The nested-paragraph decoder loop rescans the tree once per namespace (4 passes). This is a minor performance cost, bounded by the 8 MiB per-member cap.; Reported counts are the maximum across the raw, member and visible layers, not unique-secret counts. This is documented in docs/evidence/issue-620/recovery.md and is acceptable for a mechanical guard.; The supplied diff contains only tests/test_publication_safety.py. The DOCX reader in scripts/check_publication_safety.py is not shown, so the bounded reader, the fail-closed handling, the rule-name-only reporting and the DTD/entity rejection could not be checked directly. The tests reference scanner.WORD_NS, DOCX_MAX_MEMBERS, DOCX_MAX_MEMBER_BYTES and DOCX_MAX_TOTAL_BYTES, which suggests the implementation exists, and CI succeeded on the merge commit.; The README.md update and the tests/test_prepare_publication.py regression (DOCX bytes unchanged, guard.scan returns 1) are not visible in the supplied diff.; The deliberate-break deliverable (a captured failing run with the decoder disconnected, then a passing run after restoration) is only asserted in the PR body, which points to docs/evidence/issue-620/. That evidence file is not in the supplied diff. PR comments and workflow artifacts were truncated or unavailable, and the only retrieved artifacts were coverage runs that do not carry this evidence. I cannot confirm the transcript exists, and I cannot call it absent.; Regeneration of the three DOCX exports and the zero-hit repo-wide guard run are claimed in the PR body but cannot be verified from the supplied diff. The PR says these landed through the engine mirror, outside this PR.; The PR body notes the literal two-file pytest command inherits unrelated coverage failures from the src scaffold. The acceptance criterion's literal command is therefore only satisfied with --no-cov.
```



</details>

—
PR created automatically to engage Codex.

<!-- pr-preamble:start -->
<!-- meta:issue:662 -->
> **Source:** Issue #662

Closes #662

<!-- pr-preamble:end -->
