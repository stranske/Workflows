# Documentation

This folder contains the source-of-truth documentation for this repository.

## Start Here

| Document | Description |
|----------|-------------|
| [Architecture](ARCHITECTURE.md) | System boundaries, ownership and delivery routes |
| [Workflow catalog](ci/WORKFLOWS.md) | Filenames, Actions names and purposes in Workflows and consumer templates |
| [Workflow dependency map](ci/WORKFLOW_SYSTEM.md#topology-at-a-glance) | Events, callers, handoffs and outputs by task |
| [GLOSSARY.md](GLOSSARY.md) | Plain-language definitions of the system's key terms |
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | Two-page operator cheat-sheet (pause/resume, keepalive, labels) |
| [USAGE.md](USAGE.md) | Quick start and common setup patterns |
| [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) | Full integration guide for consumers |
| [ci-workflow.md](ci-workflow.md) | CI workflow wiring and local validation |
| [STRUCTURE.md](STRUCTURE.md) | How the repository is organized |
| [AGENTS_POLICY.md](AGENTS_POLICY.md) | Agent automation policies |

## Structure

Every first- and second-level directory that holds tracked files (so every `docs/`
subdirectory) is listed, one line each, in the [repository map](STRUCTURE.md#directory-index). Contributors: see
[CONTRIBUTING.md](CONTRIBUTING.md) and the [templates](templates/).

## Documentation Guidelines

### Workflow Documentation

Give each deployed workflow an entry in the [workflow catalog](ci/WORKFLOWS.md). Apply the [WFv1 naming scheme](WORKFLOW_GUIDE.md#wfv1-naming-scheme). When a workflow calls, dispatches or waits for another, update the [dependency map](ci/WORKFLOW_SYSTEM.md#topology-at-a-glance) with the trigger, condition and observable result. Add a separate task guide only when operators need setup, examples or troubleshooting beyond the catalog entry.

### Guides

How-to guides in `guides/` should:

- Address a specific task or goal
- Provide step-by-step instructions
- Include working examples
- Link to related documentation

### Examples

Follow the [workflow example contribution checklist](CONTRIBUTING.md#workflow-examples) for runnable configurations and expected results.

## Adding Documentation

1. Use the appropriate template from [templates/](templates/)
2. Keep examples runnable and aligned with the current workflow interfaces
3. Use the current first-party consumer standard (`@main`) in consumer-facing examples unless you are explicitly documenting a pinned-SHA or alternate-ref strategy
4. Cross-link related docs, and add a new first- or second-level directory to the [repository map](STRUCTURE.md#directory-index) (deeper directories are not listed)

## See Also

- Main README: [../README.md](../README.md)
- Templates and checklists: [templates/](templates/)
- Monthly workflow audit: [ci/WORKFLOW_AUDIT_PROCEDURE.md](ci/WORKFLOW_AUDIT_PROCEDURE.md)
- Archived plans and audit snapshots: [archive/ARCHIVE_PLANS.md](archive/ARCHIVE_PLANS.md)
- [Workflows cleanup tracker](reports/workflows-cleanup-tracker.md) records verified changes and the remaining live checks.
