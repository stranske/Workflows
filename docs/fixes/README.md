# Fixes Documentation Index

This folder consolidates fix summaries and supporting materials.

## Current Entries

- [sparse-checkout-audit-2026-02-03.md](sparse-checkout-audit-2026-02-03.md) — Sparse-checkout dependency audit and fix summary
- [sparse-checkout-audit-2026-02-03.csv](sparse-checkout-audit-2026-02-03.csv) — Spreadsheet of affected workflows and status

## January 2026 integration-test incidents

The integration consumer exposed three distinct problems. Early runs failed on Black and Ruff formatting. Maint 70 provided a manual formatting path and Maint 71 added automated repair. A later dependency conflict required regenerating the lockfile after a Ruff pin changed. Runs 60 and 61 exposed a failure parsing the run ID and a validation script that had drifted from its template. [Formatting repair](https://github.com/stranske/Workflows/pull/594) · [Dependency repair](https://github.com/stranske/Workflows/pull/672) · [Template repair](https://github.com/stranske/Workflows/pull/841)

For a current incident, inspect the [integration sync source](../../.github/workflows/maint-69-sync-integration-repo.yml) and the [workflow catalog](../WORKFLOW_GUIDE.md). The [manual formatter](../../.github/workflows/maint-70-fix-integration-formatting.yml), [automated fixer](../../.github/workflows/maint-71-auto-fix-integration.yml) and [local formatting script](../../scripts/fix-integration-tests-formatting.sh) show the supported entry points. To run the local script from Workflows, pass the path to the Workflows-Integration-Tests checkout:

```sh
bash scripts/fix-integration-tests-formatting.sh /path/to/Workflows-Integration-Tests
```

The original patch and the pre-cleanup reports preserve the contemporary commands, pins and test plan. [Original patch](../integration-test-failure-fix.patch) · [Root reports](https://github.com/stranske/Workflows/tree/68dfccae06410a7ccc0cc428756a5d890770e1a9) · [Documentation records](https://github.com/stranske/Workflows/tree/68dfccae06410a7ccc0cc428756a5d890770e1a9/docs) · [Run 60 and 61 records](https://github.com/stranske/Workflows/tree/68dfccae06410a7ccc0cc428756a5d890770e1a9/docs/fixes)

## November 2026 agent verification receipts

[PR #4470](https://github.com/stranske/Workflows/pull/4470) records how the [sentence-delivery test](../../tests/scripts/test_report_sentence_delivery.py) distinguishes a reported sentence in a PR comment from absent or unavailable evidence. [PR #4709](https://github.com/stranske/Workflows/pull/4709) records the deliberate break and restoration of the [queued-check ordering regression](../../tests/test_check_checks_reported.py).

| Original file at its recorded revision | Git blob ID | SHA-256 of the recovered bytes |
|---|---|---|
| [CONTINUATION_SUMMARY.md](https://github.com/stranske/Workflows/blob/42ca713e15cb7a0b290ab4ccb473c73740827a2f/CONTINUATION_SUMMARY.md) | `a0f0f53d07a627a748a572bff07edb43fef68da3` | `520713e88a5437aa17f2b804d583544f063317d59d5da7de578089c97aa171aa` |
| [EXACT_SENTENCE_RECORD.txt](https://github.com/stranske/Workflows/blob/42ca713e15cb7a0b290ab4ccb473c73740827a2f/EXACT_SENTENCE_RECORD.txt) | `2d806c787a9fabfc815611b1df32c10273a0e92f` | `4b67416d25b0394835e71c22932df3676d980fe573a5377ea8dfec38349c66e3` |
| [cursor-output-4709.md](https://github.com/stranske/Workflows/blob/51f9943bf3030134f20fe91a400ca2684d9cab5d/cursor-output-4709.md) | `f9d8f51bfa389806a7ed015803960b7ca4cb1044` | `ac2967efcaca1f7223a7d4ab1886cfd00346619401609d419f0b822687d4aab8` |

Use the commit and filename in each link to recover the bytes with `git show <commit>:<filename>`. Piping that output to `git hash-object --stdin` prints the Git blob ID.
