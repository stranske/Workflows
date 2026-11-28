# Workflows architecture

Workflows owns the GitHub Actions definitions that test a change, continue an agent's work on a pull request, verify the result and distribute shared automation. Orchestrator owns the opener, closer and sync lane code. A lane can act on GitHub issues, PRs, checks and verification receipts without being called by a Workflows YAML file.

| When you change… | Edit here | How the change reaches its user |
| --- | --- | --- |
| A shared CI check or agent runner | The called workflow in [the Workflows roster](ci/WORKFLOWS.md), and its shared scripts or composite actions | A caller's job selects it with `uses:`. A first-party caller on `@main` picks up a merged change on its next run. |
| Which events start work in Workflows | The top-level workflow in [`.github/workflows/`](../.github/workflows/) | GitHub evaluates its `on:` events and job conditions. A `workflow_run.workflows` filter selects the upstream **display name**. |
| Which events start work in a consumer | The source and delivery mode named in the [sync manifest](../.github/sync-manifest.yml) | A managed wrapper changes on the receiver when the sync PR lands. Create-only Gate policy and repository-owned CI can differ by receiver. |
| Issue admission, PR promotion or a held lane | The [lane contract](ops/LOCAL_LANES.md#lanes-overview) identifies the owner and its controls | The lane reads or writes durable issue and PR state. A green Gate alone does not promote a PR. |

## Follow a task

- **Test a PR.** Open Gate's required `summary` on the current head. Trace its job dependencies to find the check that failed or skipped. [Gate job map](ci/WORKFLOWS.md#gate-job-map)
- **Continue an unfinished task.** A completed Gate can wake the Keepalive evaluator. Workflows uses its own loop and consumers use Gate Followups. Labels, head, outstanding work and holds determine whether a runner gets a turn. The sweep can revisit an eligible PR when there is no new Gate event. [Keepalive implementation](keepalive/GoalsAndPlumbing.md)
- **Verify a merge.** The closer or an operator requests verification on the merged PR. The verifier wrapper calls the reusable verifier, publishes its verdict and provides evidence for the closer or a follow-up issue. [Verification contract](../README.md#verification-pipeline)
- **Deliver new shared files.** Maint 68 prepares the consumer diff, Maint 71 handles eligible sync PRs, and Maint 82 coordinates the campaign. The receiving head is where a copied wrapper takes effect. [Distribution procedure](ops/SYNC_DEPENDENCY_CAMPAIGN.md)

The [workflow dependency map](ci/WORKFLOW_SYSTEM.md#topology-at-a-glance) traces the handoffs in each cluster. Use the [workflow catalog](ci/WORKFLOWS.md) to look up an individual file, the [repository map](STRUCTURE.md#directory-index) to place new code or evidence, and the [WFv1 naming scheme](WORKFLOW_GUIDE.md#wfv1-naming-scheme) before adding or renaming a workflow.
