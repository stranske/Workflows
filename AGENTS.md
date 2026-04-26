# AGENTS.md - Workflows Repository Context

> Read this before changing workflows, templates, or consumer sync behavior.

## Repository Role

This repository is the source of truth for:

- Reusable workflows in `.github/workflows/reusable-*.yml`
- First-party orchestration workflows used to operate and test the system
- Consumer repo templates in `templates/consumer-repo/`
- Shared scripts and composite actions used by those workflows

## Read These Docs First

Start with the current docs instead of inferring behavior from old comments:

1. `README.md` - repository purpose, architecture, and current consumer model
2. `docs/WORKFLOW_GUIDE.md` - full workflow inventory and purpose
3. `docs/ci/WORKFLOWS.md` - workflow topology and active automation layout
4. `docs/INTEGRATION_GUIDE.md` - consumer integration and versioning policy
5. `docs/ops/CONSUMER_REPO_MAINTENANCE.md` - sync mechanics and consumer exceptions
6. `docs/keepalive/Agents.md` and `docs/keepalive/GoalsAndPlumbing.md` - keepalive contract

## Current Consumer Defaults

- First-party consumers and the consumer templates currently reference reusable workflows with `@main`.
- Do not introduce new `@v1` guidance unless the versioning policy changes across the templates, README, integration guide, and consumer docs together.
- Consumer-managed files are defined by `.github/sync-manifest.yml`. If a consumer-facing file is not declared there, it is not centrally managed.
- `ci.yml` and `autofix-versions.env` remain repo-specific in consumer repos.
- `pr-00-gate.yml` is distributed as a create-only starting point. Consumers should stay aligned to the standard gate unless they have an explicitly documented exception.

## Editing Rules

- Changes to reusable workflows affect consumers immediately.
- Changes to consumer-facing workflows, prompts, scripts, or docs must be made in the Workflows source, not patched ad hoc in a consumer repo.
- Update `templates/consumer-repo/` and `.github/sync-manifest.yml` together when a consumer-facing file is added, removed, renamed, or re-scoped.
- If you find consumer drift that is not intentional, fix Workflows first and then align the consumer.
- If a consumer exception is necessary, document it in `docs/ops/CONSUMER_REPO_MAINTENANCE.md`.

## Keepalive And Agent Surfaces

- Keepalive, autofix, verifier, and auto-pilot are multi-agent surfaces. Do not hard-code provider-specific behavior where routing should come from registry/config.
- Read `docs/keepalive/Agents.md` before touching keepalive logic.
- Read `docs/guides/ADD_NEW_AGENT.md` before adding or changing agent support.
- The current consumer default entry points are `agents-issue-intake.yml`, `agents-80-pr-event-hub.yml`, `agents-81-gate-followups.yml`, `agents-verifier.yml`, `autofix.yml`, `ci.yml`, and `pr-00-gate.yml`.

## Optional GitNexus Context

- GitNexus is an optional local MCP/indexing layer for cross-repo search and impact checks. Read `docs/ops/GITNEXUS.md` before changing its setup.
- Use GitNexus opportunistically for workflow/template drift, reusable workflow blast-radius checks, and Workflows-vs-consumer ownership questions when the MCP server is available and indexes are fresh.
- Treat `.gitnexus/` and `~/.gitnexus/` as local derived cache. Do not commit indexes or make CI, remote workflows, or correctness depend on GitNexus output.
- `Template` is part of the canonical GitNexus fleet because new repos are cloned from it. `Workflows-steward` is temporary automation state and must be ignored.
- If GitNexus is unavailable or stale, continue with normal `rg`, git, and test-based repository exploration.

## Workflow PR Checklist

1. Decide whether the change belongs in a reusable workflow, a consumer template, or a consumer repo.
2. Update the docs that define the changed contract.
3. If consumers are affected, update the template files and the sync manifest in the same PR.
4. Run the relevant validation for the changed surface.
5. If consumer templates changed, trigger sync and use the merge workflow for resulting sync PRs.

## Agent-Specific Note

This file is the agent-generic contract. Keep it materially aligned with `CLAUDE.md`; differences between the two should only be agent-specific execution notes, not different repository rules.
