# Bounded pagination validation

This change advances the first unchecked task. It preserves the complete explicit
reference union and existing exact-head/merge provenance checks. Full pages without
count/Link metadata now require bounded continuation. Count presence must stay
stable across pages, every listed record must have a positive safe integer ID,
and oversized or repeated records cannot establish completeness. Earlier findings
remain retained when a later page fails.

Source and consumer-template collectors are byte-identical. Existing manifest
coverage and contract documentation were updated. Page/record limits and expanded
profile exports remain unchanged; no workflow files were edited.

## Executed checks

- `bash evidence/issue-3820/pagination-red-green.sh`: PASS. Overlays the final four
  pagination tests on collectors from `fe0f9f35c197675a7bc4f2c836ce14e042590528`
  in an isolated temporary tree. The prior collector fails two behavioral tests
  (full-page continuation and count/identity validation); all 11 selected final
  tests pass, covering both source and template implementations, sparse late pages,
  exhaustion, reference completeness/union, wrong-head evidence and sibling gaps.
  Output is retained in `pagination-red-green.txt`.
- `python -m pytest tests/workflows/test_verifier_evidence_profile.py
  tests/scripts/test_pr_verifier_sync_manifest.py
  tests/scripts/test_validate_template_sync.py
  tests/test_workflow_guide_verifier_sections.py -m 'not slow' -q -o addopts=`:
  94 passed.
- `python scripts/validate_template_sync.py`: all template files in sync.
- `bash -n evidence/issue-3820/pagination-red-green.sh`,
  `shellcheck evidence/issue-3820/pagination-red-green.sh`, and `git diff --check`:
  passed.
- Full existing context suite was attempted before and after the change. The
  ordinary Node test runner cannot spawn its child here (`EPERM`). Running with
  `node --test --test-isolation=none
  .github/scripts/__tests__/agents-verifier-context.test.js` executes the suite:
  final result is 135 passed, six failed. The same six tests fail on the unchanged
  baseline (131 passed): one real archive test and five real Git patch tests cannot
  spawn `zip`/`git` (`spawnSync ... EPERM`). No tests were disabled or changed to
  suppress those failures.

## Remaining acceptance

This offline proof does not reproduce the authenticated #3802 capture or establish
live completeness/provider acceptance. Existing finite record/page ceilings still
leave oversized captures unavailable. Manifest wiring, prompt recovery, complete
changed-code/evidence capacity verification and remaining end-to-end acceptance
remain open. No PR task checkboxes were changed. Consumer sync was not dispatched
because this task prohibits mutation of generated PRs.

The runner mounts the original `.git` read-only, so normal staging/commit fails
at `index.lock`. The verified files are committed using a separate local bare
repository at `/tmp/workflows-pagination-commit.git` and the original working tree;
its index starts from the original HEAD. A single-commit bundle is retained at
`/tmp/verifier-pagination-commit.bundle`. The original branch remains unchanged.
