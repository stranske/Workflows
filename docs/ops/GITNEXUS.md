# GitNexus Local Code Intelligence

GitNexus is an optional local code-intelligence layer for the active Code
workspace. It is not a CI dependency, runtime dependency, or source of truth.
GitHub and the checked-out source tree remain authoritative.

## Scope

The canonical GitNexus fleet is:

- `Workflows`
- `Template`
- `Manager-Database`
- `Travel-Plan-Permission`
- `trip-planner`
- `Inv-Man-Intake`
- `Pension-Data`
- `Counter_Risk`
- `Trend_Model_Project`
- `Portable-Alpha-Extension-Model`
- `Collab-Admin`

`Workflows-steward` must be ignored by GitNexus for indexing, but it is **not**
throwaway scratch: it is a linked git worktree of the canonical `Workflows`
clone that holds the repo-review/steward outputs and is structurally
load-bearing for the opener lane. To keep it from holding the canonical clone's
`main` hostage, its canonical arrangement is a **detached `HEAD` at
`origin/main`** (a detached HEAD takes no branch lock). See
[`LOCAL_LANES.md`](LOCAL_LANES.md) for the full steward/lane-state contract. Do
not add short-lived issue, PR, or review clones to the registry.

## Local Cache Policy

GitNexus writes repo-local `.gitnexus/` indexes, may generate
`.claude/skills/gitnexus/`, and keeps global registry state under
`~/.gitnexus/`. Treat all of these as derived local cache.

- Do not commit `.gitnexus/`.
- Do not commit `.claude/skills/gitnexus/`.
- Prefer global git excludes for GitNexus cache paths so local-only setup does
  not dirty every repo worktree.
- Do not add repo-specific `.gitignore` entries solely for GitNexus unless that
  repo intentionally wants to track them.
- Do not require GitNexus for CI or remote workflows.
- Do not make correctness depend on GitNexus output.
- Use normal `rg`, git, and repository tests as the fallback path.

## MCP Setup

Install the pinned CLI once:

```bash
docs/ops/bin/gitnexus_fleet.sh install
docs/ops/bin/gitnexus_fleet.sh check-version
docs/ops/bin/gitnexus_fleet.sh ensure-global-ignore
```

Use one global MCP server for Codex:

```toml
[mcp_servers.gitnexus]
command = "gitnexus"
args = ["mcp"]
```

The helper prints the current snippet:

```bash
docs/ops/bin/gitnexus_fleet.sh mcp-config
```

## Index Freshness

Refresh indexes after source changes that can make graph data stale:

- after `git pull`, merge, rebase, or branch switch
- before large cross-repo automation runs
- before impact analysis on workflow/template changes
- after a Codex automation lands significant code changes

Baseline indexing intentionally leaves embeddings off and skips
GitNexus-managed `AGENTS.md` / `CLAUDE.md` rewrites:

```bash
docs/ops/bin/gitnexus_fleet.sh ensure-global-ignore
docs/ops/bin/gitnexus_fleet.sh index all
docs/ops/bin/gitnexus_fleet.sh group-create
docs/ops/bin/gitnexus_fleet.sh group-add
docs/ops/bin/gitnexus_fleet.sh group-sync
```

Use `docs/ops/bin/gitnexus_fleet.sh status all` or
`docs/ops/bin/gitnexus_fleet.sh group-status` before relying on GitNexus
context.

## Tool Freshness

The GitNexus tool version is intentionally separate from repository dependency
updates. Update `GITNEXUS_VERSION` in `docs/ops/bin/gitnexus_fleet.sh`, then
run the pinned global install, only after a manual smoke test on a single repo
succeeds.

Recommended upgrade flow:

1. Run the current pinned version against `Template`.
2. Test the candidate version with `GITNEXUS_VERSION=<version> docs/ops/bin/gitnexus_fleet.sh install`.
3. Confirm `check-version`, `index Template`, `status Template`, and group commands still work.
4. Update the pin and this document in the same Workflows change.

## Agent And Automation Use

Agents and local Codex automations may use GitNexus opportunistically when the
MCP server is available and indexes are fresh. Good uses include:

- cross-repo workflow/template drift checks
- impact analysis before reusable workflow changes
- locating shared agent, keepalive, verifier, and autofix behavior
- checking whether a change belongs in `Workflows` or a consumer repo

If GitNexus is unavailable or stale, continue with normal repo exploration.
