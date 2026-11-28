# Workflow Sync Process

The maintained operator procedure is the [consumer repository maintenance guide](ops/CONSUMER_REPO_MAINTENANCE.md).
The manifest selects sources from both the Workflows root and the consumer template;
Maint 68 reads each compiled entry's `resolved_source`. See [what gets synced](ops/CONSUMER_REPO_MAINTENANCE.md#what-gets-synced).

## Purpose

Validate shared changes in Workflows and deliver the reviewed payload to consumers.

## Before Any Sync

### 0. Verify Template Sync (CRITICAL)

For manifest-declared exact template mirrors, run `python scripts/consumer_sync/validate_template_sync.py`.
If it reports drift, run `./scripts/consumer_sync/sync_templates.sh`, re-run the validator and
review the resulting changes. The publisher and validator use the same compiled
source list; Health 72 also checks it.

### 1. Validate in Workflows Repo

Run the tests and production checks appropriate to the changed source. The
[delivery scope and production checks](ops/CONSUMER_REPO_MAINTENANCE.md#delivery-scope-and-production-checks)
define the current procedure.

### 2. Check for Existing Sync Issues

Use the [sync and dependency campaign contract](ops/SYNC_DEPENDENCY_CAMPAIGN.md)
to inspect existing delivery state.

### 3. Review Bot Comments on Latest Sync PRs

Follow that contract to inspect and resolve the current review findings.

## Fixing Issues Found

Repair shared sources in Workflows and follow the maintained consumer delivery
procedure for the affected payload.

### If Validation Fails in Workflows

Repair the shared source and repeat the affected checks.

### If Bot Comments Found

Assess active findings against the exact delivery head.

## Stable Delivery PRs

Maint 68 prepares stable candidate and delivery PRs; Maint 71 owns their review,
reconciliation and merge. Use the [generated delivery ownership procedure](ops/CONSUMER_REPO_MAINTENANCE.md#generated-delivery-ownership)
for current exact-head gates and review handling.

### Reconcile the stable lanes

Follow the maintained procedure rather than using a command copied from an older
snapshot. The [original guide](https://github.com/stranske/Workflows/blob/0c0334c6e92588c158f1c9362f1409062477de09/docs/SYNC_WORKFLOW.md)
remains available for historical context.

## Summary Checklist

Use the [manual sync trigger and delivery guide](ops/CONSUMER_REPO_MAINTENANCE.md#manual-sync-trigger)
for the current sequence and acceptance evidence.
