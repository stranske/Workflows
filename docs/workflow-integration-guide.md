# Workflow Integration Guide

For a consumer pull request, start with the [Gate template](../templates/consumer-repo/.github/workflows/pr-00-gate.yml).
The separate [CI template](../templates/consumer-repo/.github/workflows/ci.yml)
provides push CI for the merge commit. The [consumer verifier](../templates/consumer-repo/.github/workflows/agents-verifier.yml)
selects that workflow by filename and calls the shared verifier at `@main`.
See the [system dependency map](ci/WORKFLOW_SYSTEM.md#topology-at-a-glance)
for the rest of the event and ownership chain.

The [verifier dependency and cache reference](WORKFLOW_GUIDE.md#workflow-integration-guide)
points to the current install steps in the reusable and the separate follow-up
workflow. Follow-up work starts with an explicit label or an eligible dispatch
and reads the retained [verification report](WORKFLOW_GUIDE.md#current-verifier-report-for-follow-ups).

## Pending dependency proposal

[Verify to New PR pinned dependencies](WORKFLOW_GUIDE.md#pending-dependency-proposal)

## Deterministic verdict extraction

[Current verdict command and outputs](WORKFLOW_GUIDE.md#deterministic-verdict-extraction)

## Historical snippets

[February workflow examples](WORKFLOW_GUIDE.md#historical-snippets)
