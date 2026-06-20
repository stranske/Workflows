# Exported Orchestrator Skill Context for Remote Codex Lanes

Remote Codex opener and closer lanes can opt in to a curated **exported Orchestrator skill pack**. This gives the agent Orchestrator policy and reference material in the prompt without mounting the local Orchestrator Brain, feedback database, worktrees, or credentials.

## What this is

- **Exported context** checked out from a GitHub repo into `.reference/` during `reusable-codex-run.yml`
- A prompt section titled **Orchestrator Skill Context** assembled from `.reference/ORCHESTRATOR_SKILL.md`
- Compatible with existing `.github/reference_packs.json` behavior

## What this is not

Remote Actions must **not** read:

- `/Users/teacher/.codex` or other local-only paths
- the local Orchestrator SQLite feedback database
- local Orchestrator worktrees or dispatcher tooling
- local credentials

Local Orchestrator remains the authority for routing, delegation, monitoring, and learning. Remote Codex runs may use the exported instructions only.

## Opt-in configuration

Add `.github/orchestrator_skill.json` to a consumer repo or PR branch.

### Reference a named reference pack

```json
{
  "enabled": true,
  "pack": "orchestrator"
}
```

Requires a matching pack in `.github/reference_packs.json`:

```json
{
  "orchestrator": {
    "repo": "stranske/Workflows",
    "ref": "main",
    "paths": ["docs/exports/orchestrator-skill/SKILL.md"]
  }
}
```

### Inline exported checkout

```json
{
  "enabled": true,
  "repo": "stranske/Workflows",
  "ref": "main",
  "paths": ["docs/exports/orchestrator-skill/SKILL.md"]
}
```

Set `"enabled": false` to disable without deleting the file.

## Workflow overrides

`reusable-codex-run.yml` accepts optional inputs:

| Input | Purpose |
| --- | --- |
| `orchestrator_skill_pack` | Override the reference-pack name |
| `orchestrator_skill_enabled` | Force enable/disable (`true` / `false`); empty uses repo config |

These inputs are forwarded by:

- `agents-keepalive-loop.yml` (closer lane / PR keepalive Codex runs)
- `agents-71-codex-belt-dispatcher.yml` and `agents-72-codex-belt-worker.yml` (opener lane API surface; repo config on the automation branch remains primary)

Repos with no Orchestrator config and no overrides are unchanged.

## Implementation surfaces

| Surface | Role |
| --- | --- |
| `scripts/orchestrator_skill.py` | Validates `.github/orchestrator_skill.json` |
| `.github/actions/agent-reference-packs` | Materializes reference packs and Orchestrator skill exports |
| `scripts/runner_lib/core.py` | Adds the Orchestrator Skill Context section during prompt assembly |
| `.github/workflows/reusable-codex-run.yml` | Codex runner entry point for opener/closer prompt assembly |

## Curated export source

Workflows ships a CI-safe export at `docs/exports/orchestrator-skill/SKILL.md`. Consumer repos should pin a ref/path to that file or to their own sanitized export repo.
