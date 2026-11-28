# Automation system implementation notes

**Historical implementation proposal.** The [earlier guide](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/automation-system-implementation.md)
is historical. Its workflow skeletons and credential examples do not describe
all current runner and delivery paths.

For current behavior start with the [workflow system guide](ci/WORKFLOW_SYSTEM.md),
[Keepalive Goals & Plumbing](keepalive/GoalsAndPlumbing.md), and
[consumer repository maintenance](ops/CONSUMER_REPO_MAINTENANCE.md). The
[Codex token refresh guide](ops/CODEX_TOKEN_REFRESH.md) describes the current
`CODEX_AUTH_JSON` CI credential route. Check each workflow's actual inputs and
permissions when configuring a consumer.
