# Historical agent merge queue guide

The former orchestrator auto-merge scan described here is retired. Its
[`automerge` label, automation-account, and scan-summary instructions](https://github.com/stranske/Workflows/blob/c1f1d482c47f609a11230bfb00fd187bc6bff3c0/docs/ci/MERGE_QUEUE.md)
are a historical record, not the current merge procedure.

For agent pull requests, follow the [local closer lane](../ops/LOCAL_LANES.md#lanes-overview),
which owns review, guarded merge, and post-merge verification. For consumer
sync pull requests, follow [consumer repository maintenance](../ops/CONSUMER_REPO_MAINTENANCE.md).
Consult the repository's current branch protection and required checks for the
specific pull request.
