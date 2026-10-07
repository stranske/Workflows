# Post-merge verify:compare receipt (release PR #3769)

Orphan Steward owns exactly one repaired-input `verify:compare` for merged
release PR #3769 after the producer repair lands on `main`. This directory
holds the dual-run receipt: the original NON_PASS baseline stays frozen, and
the steward follow-up records newly observed verdicts plus source coverage.

## Frozen baseline (do not relabel)

| Field | Value |
|-------|-------|
| Run | [37400729553](https://github.com/stranske/Workflows/actions/runs/37400729553) |
| PR | [#3769](https://github.com/stranske/Workflows/pull/3769) |
| Provider verdicts | CONCERNS / CONCERNS |
| Corpus decision | NON_PASS |
| Source discovery | required `unavailable` — “Known source issue #3768 was not retrieved…” |
| Comparison artifact | `comparison-results-37400729553` (7 files) |
| Terminal artifact | `verifier-terminal-disposition-37400729553` |
| Metrics artifact | `agents-verifier-metrics` |

## Steward follow-up (recorded)

| Field | Value |
|-------|-------|
| Run | [37567257334](https://github.com/stranske/Workflows/actions/runs/37567257334) |
| Dispatch | `gh workflow run agents-verifier.yml -f pr_number=3769 -f mode=compare` |
| Provider verdicts | CONCERNS / PASS |
| Corpus decision | NON_PASS |
| Source discovery | `required=false`, status `included` (no #3768 required-source contract) |
| Comparison artifact | `comparison-results-37567257334` (7/7 files present) |
| Terminal artifact | `verifier-terminal-disposition-37567257334` (`needs-human`, concerns) |
| Metrics artifact | `agents-verifier-metrics` |

Receipt JSON: `receipt.json` (also `baseline-receipt.json` for the pre-follow-up freeze).
Fixture copies for tests: `tests/fixtures/verifier_compare_receipt/run-37567257334/`.

Independent source #3757 topology and complete artifact-count evidence remain
required and are not satisfied by this receipt alone. The original baseline is
not relabeled.

## Steward dispatch (after merge)

```sh
gh workflow run agents-verifier.yml \
  --repo stranske/Workflows \
  -f pr_number=3769 \
  -f mode=compare
```

Then build the dual-run receipt:

```sh
gh run download 37567257334 -R stranske/Workflows \
  -n comparison-results-37567257334 -D /tmp/followup/comparison
gh run download 37567257334 -R stranske/Workflows \
  -n verifier-terminal-disposition-37567257334 -D /tmp/followup/terminal

python tools/verifier_compare_run_receipt.py \
  --baseline-comparison-dir tests/fixtures/verifier_compare_receipt/run-37400729553 \
  --baseline-terminal tests/fixtures/verifier_compare_receipt/run-37400729553-terminal \
  --followup-run-id 37567257334 \
  --followup-comparison-dir /tmp/followup/comparison \
  --followup-terminal /tmp/followup/terminal \
  --output docs/evidence/issue-3770/post-merge-compare/receipt.json
```

## Validation

```sh
pytest tests/tools/test_verifier_compare_run_receipt.py -m "not slow"
```
