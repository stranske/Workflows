# Fixes Documentation Index

This folder consolidates fix summaries and supporting materials.

## Current Entries

- [sparse-checkout-audit-2026-02-03.md](sparse-checkout-audit-2026-02-03.md) — Sparse-checkout dependency audit and fix summary
- [sparse-checkout-audit-2026-02-03.csv](sparse-checkout-audit-2026-02-03.csv) — Spreadsheet of affected workflows and status

## January 2026 integration-test incidents

The integration consumer exposed three distinct problems. Early runs failed on Black and Ruff formatting. Maint 70 provided a manual formatting path and Maint 71 added automated repair. A later dependency conflict required regenerating the lockfile after a Ruff pin changed. Runs 60 and 61 exposed a failure parsing the run ID and a validation script that had drifted from its template. [Formatting repair](https://github.com/stranske/Workflows/pull/594) · [Dependency repair](https://github.com/stranske/Workflows/pull/672) · [Template repair](https://github.com/stranske/Workflows/pull/841)

For a current incident, inspect the [integration sync source](../../.github/workflows/maint-69-sync-integration-repo.yml) and the [workflow catalog](../WORKFLOW_GUIDE.md). The [manual formatter](../../.github/workflows/maint-70-fix-integration-formatting.yml), [automated fixer](../../.github/workflows/maint-71-auto-fix-integration.yml) and [local formatting script](../../scripts/fix-integration-tests-formatting.sh) show the supported entry points. The original patch and the pre-cleanup reports preserve the contemporary commands, pins and test plan. [Original patch](../integration-test-failure-fix.patch) · [Root reports](https://github.com/stranske/Workflows/tree/68dfccae06410a7ccc0cc428756a5d890770e1a9) · [Documentation records](https://github.com/stranske/Workflows/tree/68dfccae06410a7ccc0cc428756a5d890770e1a9/docs) · [Run 60 and 61 records](https://github.com/stranske/Workflows/tree/68dfccae06410a7ccc0cc428756a5d890770e1a9/docs/fixes)
