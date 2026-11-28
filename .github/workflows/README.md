# Workflows in this directory

GitHub loads the workflow YAML here for the Workflows repository. The [workflow catalog](../../docs/ci/WORKFLOWS.md) lists each file and what it does. The [workflow dependency map](../../docs/ci/WORKFLOW_SYSTEM.md#topology-at-a-glance) shows which jobs call a reusable workflow, which workflows listen for completion, and which lanes share issue or PR state.

| Task | Start here |
| --- | --- |
| Add or rename a workflow | Follow [WFv1 naming](../../docs/WORKFLOW_GUIDE.md#wfv1-naming-scheme) and the [contributor checklist](../../docs/CONTRIBUTING.md#workflows). |
| Diagnose a failed PR check | Open the required `summary` on that head and follow the [Gate job map](../../docs/ci/WORKFLOWS.md#gate-job-map). |
| Find out why an agent stopped | Check the [Keepalive implementation](../../docs/keepalive/GoalsAndPlumbing.md) and [troubleshooting guide](../../docs/keepalive/KEEPALIVE_TROUBLESHOOTING.md). |
| Change a consumer entry point | Locate its source and delivery mode in the [sync manifest](../sync-manifest.yml) and follow the [consumer route](../../docs/STRUCTURE.md#change-a-file-distributed-to-consumers). |
| Trace a retired filename | Use the [archive ledger](../../docs/archive/ARCHIVE_WORKFLOWS.md) and [workflow decisions](../../docs/reports/workflow-decisions.md). |
