# CLAUDE.md - Consumer Repository Context

> Read this before changing workflows, prompts, or synced automation files.

## This Is A Consumer Repo

Most workflow logic for this repository lives in `stranske/Workflows`. The consumer repo should only carry repo-specific configuration unless it has an explicitly documented exception.

## Source Of Truth

For infrastructure work, follow this order:

1. `stranske/Workflows` root docs: `README.md`, `docs/WORKFLOW_GUIDE.md`, `docs/ci/WORKFLOWS.md`
2. `stranske/Workflows/docs/INTEGRATION_GUIDE.md` and `docs/ops/CONSUMER_REPO_MAINTENANCE.md`
3. The consumer sync source in `stranske/Workflows/templates/consumer-repo/`
4. This repo's local repo-specific files

If a file is synced from Workflows, fix it in Workflows first.

## Current Consumer Defaults

- First-party consumers currently reference reusable workflows with `@main`. Match that unless you are intentionally pinning to an exact commit SHA for a controlled reason.
- `ci.yml` and `autofix-versions.env` are repo-specific.
- `pr-00-gate.yml` is a create-only standard file. Keep it aligned with the standard gate unless this repo has a documented reason to diverge.
- Synced workflows, prompts, scripts, and consumer docs are managed through `.github/sync-manifest.yml` in Workflows.

## Commonly Managed Files

Usually edit locally only when the file is repo-specific:

| File | Default owner | Notes |
|------|---------------|-------|
| `ci.yml` | Consumer repo | Repo-specific CI wiring |
| `autofix-versions.env` | Consumer repo | Repo-specific dependency pins |
| `pr-00-gate.yml` | Consumer repo, but should match Workflows standard by default | Create-only standard file |
| `agents-*.yml` | Workflows | Fix in Workflows, not here |
| `autofix.yml` | Workflows | Fix in Workflows, not here |
| `.github/codex/` prompts | Workflows | Fix in Workflows, not here |
| synced scripts/docs | Workflows | Fix in Workflows, not here |

## Current Workflow Surfaces

The current consumer default automation surface is centered on:

- `agents-issue-intake.yml`
- `agents-80-pr-event-hub.yml`
- `agents-81-gate-followups.yml`
- `agents-verifier.yml`
- `autofix.yml`
- `ci.yml`
- `pr-00-gate.yml`

Legacy compatibility workflows may still exist during migrations. Do not assume an older filename is canonical without checking the Workflows docs first.

## Cross-Repo Policy

Before editing local workflow infrastructure, ask:

**Does this work belong in `stranske/Workflows` instead?**

The answer is usually yes if the change affects any of these:

- reusable workflows
- agent prompts or routing
- keepalive/autofix/verifier behavior
- synced workflow files
- synced scripts or docs

If yes:

1. Make the source-of-truth change in `stranske/Workflows`
2. Update the sync manifest if a consumer-facing file changed
3. Sync or manually align this repo afterward

## Optional GitNexus Context

- GitNexus may be available as a local MCP/indexing layer for cross-repo search and impact checks.
- Use it opportunistically for workflow/template drift, blast-radius checks, and Workflows-vs-consumer ownership questions when indexes are fresh.
- Treat `.gitnexus/` as local derived cache. Do not commit it, require it in CI, or make correctness depend on it.
- If GitNexus is unavailable or stale, continue with normal `rg`, git, and repository tests.

## Useful References

- `stranske/Workflows/README.md`
- `stranske/Workflows/docs/WORKFLOW_GUIDE.md`
- `stranske/Workflows/docs/ci/WORKFLOWS.md`
- `stranske/Workflows/docs/INTEGRATION_GUIDE.md`
- `stranske/Workflows/docs/ops/CONSUMER_REPO_MAINTENANCE.md`
- `stranske/Workflows/docs/keepalive/Agents.md`
- `stranske/Travel-Plan-Permission` as a reference consumer

## Claude-Specific Note

Keep this file materially aligned with `AGENTS.md`. Differences between the two should only be agent-specific execution notes, not different repository rules.
