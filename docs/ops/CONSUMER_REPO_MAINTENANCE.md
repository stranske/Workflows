# Consumer Repository Maintenance Guide

This document outlines the process for maintaining workflow system consistency across consumer repositories and debugging issues that may affect multiple repos.

---

## Registered Consumer Repos

Consumer repositories are synced by the workflow
`.github/workflows/maint-68-sync-consumer-repos.yml`.

The list of registered repos lives in that workflow (env var
`REGISTERED_CONSUMER_REPOS`). Avoid duplicating the list here; it changes over time and
the workflow is the source of truth.

### Drift coverage states

Scheduled Health 68 runs are triggered only after a successful Maint 71 janitor; push and
manual runs are intentionally immediate. It classifies each
consumer as `converged`, `covered`, `blocked`, `untracked_drift`, or `stale`. An open
sync PR covers drift only when its `sync/workflows-<template-hash>` branch matches the
current compiled plan and it is within the 36-hour coverage lease. Fully covered drift
exits zero and does not append a durable-tracker comment; stale (including expired
coverage), blocked (including global/lookup failures), and untracked states remain
actionable failures.

### Adding a New Consumer Repo

1. Add the repo to `REGISTERED_CONSUMER_REPOS` in `maint-68-sync-consumer-repos.yml`.
2. Ensure bot collaborator access (see [Bot Access](#bot-collaborator-access))
3. Run the sync workflow manually to verify.

### Repos with Custom Configurations

Some repos cannot use the template `pr-00-gate.yml` because:
- **Manager-Database**: Uses `docker compose`, `pre-commit`, custom test setup
- **Trend_Model_Project**: Keeps the historical `Agents.md` filename, so syncing
  `AGENTS.md` would create a case-only path collision on case-insensitive
  filesystems
- **trip-planner**: Installs `.github/scripts` dependencies from
  `.github/scripts/package-lock.json` with `npm ci` and has an explicit hygiene
  check that forbids tracked `node_modules/` anywhere in the repo.
- **Fine-Art-Archive**: Keeps a fleet-preset Renovate exception for
  `jsonschema<4.23.0` because newer non-major releases currently violate the
  repo's supported dependency range and fail Gate.

For these repos:
- The Gate workflow (`pr-00-gate.yml`) is maintained locally and excluded from sync.
- `Trend_Model_Project` skips the synced `AGENTS.md` file and keeps its local
  `Agents.md`.
- `trip-planner` skips the synced `.github/scripts/package.json` and vendored
  `.github/scripts/node_modules/` entries so its lockfile-based dependency
  policy remains intact.
- `Fine-Art-Archive` still receives the managed `.github/renovate.json`; its
  dependency exception is centralized in `renovate-presets/fleet.json` with a
  repository-scoped package rule, not patched directly in the consumer repo.
- Other files listed in the sync manifest continue to sync normally.

Maint 68 implements these exceptions through each entry's typed manifest
`skip_repos` rules. There is no separate hard-coded custom-Gate list in the
sync script.

### Fleet Renovate intake policy

All registered consumers extend `renovate-presets/fleet.json`. Routine dependency
work is limited to Monday 01:00–05:00 America/Chicago, two commits per hour, and
three concurrent branches/PRs. Routine releases wait three days and for non-pending
update-branch checks; vulnerability alerts bypass each routine delay. Trusted GitHub Actions
digest, pin, minor, and patch updates are grouped for green automerge, while majors
stay visible in the Dependency Dashboard until explicitly approved. Lock-file
maintenance is grouped into the same weekly maintenance window.

---

## Bug Triage Process

When a bug is identified in workflow templates:

### Step 1: Classify the Bug

| Category | Scope | Example |
|----------|-------|---------|
| **Template bug** | All repos using template | Logical expression `|| 'true'` always true |
| **Reusable workflow bug** | All repos calling the workflow | Missing output parameter |
| **Consumer-specific** | Single repo | Wrong CI workflow name in verifier |

### Step 2: Assess Impact

```bash
# Check which repos have the affected file
for repo in Template Travel-Plan-Permission trip-planner Manager-Database; do
  echo "=== $repo ==="
  curl -s -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/stranske/$repo/contents/.github/workflows/FILENAME" | \
    jq -r '.content' | base64 -d | grep -E "PATTERN" | head -5
done
```

### Step 3: Fix Strategy

| Bug Type | Fix Location | Propagation |
|----------|-------------|-------------|
| Template bug | `templates/consumer-repo/` | Auto-sync to registered repos |
| Reusable workflow | `.github/workflows/reusable-*.yml` | Immediate (all callers) |
| Consumer-specific | Consumer repo directly | Manual PR |

### Step 4: Create Fix Tracking Issue

For bugs affecting multiple repos, create a tracking issue with:
- [ ] Bug description and root cause
- [ ] List of affected repos
- [ ] Fix commits/PRs for each location
- [ ] Verification steps

> Not to be confused with the **durable tracker** for consumer-sync drift
> ([#2210](https://github.com/stranske/Workflows/issues/2210)), which the
> `Health 68 Consumer Sync Drift` workflow re-uses across cycles and refreshes
> when drift is detected. A clean run does not close the tracker. See
> [`DURABLE_TRACKING_ISSUES.md`](DURABLE_TRACKING_ISSUES.md).

---

## Common Bug Patterns

### Logical Expression Bugs

**Pattern**: `${{ inputs.flag && 'true' || 'true' }}`  
**Problem**: Always evaluates to 'true', input cannot disable feature  
**Fix**: `${{ inputs.flag && 'true' || 'false' }}`

**Affected files** (historically):
- `agents-orchestrator.yml`: `enable_watchdog`, `enable_keepalive`
- `agents-issue-intake.yml`: `post_agent_comment`

### Missing Event Handlers

**Pattern**: Workflow has trigger but no corresponding job  
**Example**: `workflow_run` trigger without handler job  
**Detection**: Search for trigger in `on:` block, verify matching job exists

### Hardcoded Values

**Pattern**: Repository-specific values in templates  
**Examples**:
- `allowed_keepalive_logins: 'stranske'`
- `ci_workflows: '["ci.yml"]'`
- Bot account names in comments

**Fix**: Use variables or empty defaults with clear documentation

### Workflow input typing mismatches

**Pattern**: passing a string into a reusable workflow input declared as `number`.

**Fix**: pass an actual number expression (often via `fromJSON(...)`) so the workflow
template validator and runtime typing agree.

### Action Version Inconsistencies

**Pattern**: Mixed versions of same action across workflows  
**Example**: `actions/github-script@v7` in some files, `@v8` in others  
**Fix**: Standardize on single version, update all files together

---

## Bot Collaborator Access

The `stranske-automation-bot` account needs push access to consumer repos for:
- Autofix commits
- Agent-created PRs

### Checking Access

```bash
curl -s -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/stranske/REPO/collaborators/stranske-automation-bot/permission" | \
  jq '{permission}'
```

### Granting Access

```bash
curl -s -X PUT \
  -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/stranske/REPO/collaborators/stranske-automation-bot" \
  -d '{"permission": "push"}'
```

**Note**: The bot must accept the invitation. Check pending invitations at:
`https://github.com/notifications`

---

## Sync Workflow Details

### What Gets Synced

Maint 68 is manifest-driven:

- **What** gets synced is declared in `.github/sync-manifest.yml`.
- **Where** files come from is either `templates/consumer-repo/` (most items) or
  repository-level directories like `.github/scripts/` (for shared scripts).
- **Which repos** receive updates are listed in `REGISTERED_CONSUMER_REPOS`.

#### Manifest Schema and Compiler

`.github/sync-manifest.yml` is parsed by a **typed, deterministic compiler**
(`scripts/sync_manifest_compiler.py`) before any consumer mutation can happen.
The compiler resolves source ownership once, validates every entry, and raises
one aggregated `ManifestCompileError` before sync fan-out so invalid entries
never reach the sync or drift-check loops. It emits the deterministic
`workflows.consumer-sync-plan/v1` JSON consumed by sync, drift, validation, and
template hashing. Its machine-readable schema is
[`consumer-sync-plan-v1.schema.json`](../contracts/schemas/consumer-sync-plan-v1.schema.json).

Validated fields for each sync entry:

| Field | Type | Notes |
|-------|------|-------|
| `source` | safe relative path, required | Resolved once using section ownership policy |
| `target` | safe relative path, optional | Defaults to `source`; effective targets must be unique |
| `description` | str, required | Included in the plan for operator summaries |
| `sync_mode` | `"create_only"` or absent | `None` = always overwrite |
| `skip_repos` | list of str or `{repo, reason}` dicts | Repo-specific exclusions |
| `overwrite_repos` | list of str | Repos that ignore `create_only` |
| `is_directory` | bool, optional | Defaults to `False` |
| `template_sync` | `"exact"` or absent | Controls template validator |
| `delivery` | `"copy"` or absent | Runtime-fetched files belong under `runtime_fetched`, not a copy section |

Removal targets are typed separately and cannot collide with a copy target.
`excluded:` and `runtime_fetched:` remain metadata-only sections.

Each normalized copy record adds `resolved_source`, `content_sha256`, and a
stable `effect_fingerprint`; the plan adds `manifest_sha256` and `plan_id`.
Directory content hashes are computed from a sorted relative-path/content
inventory, so identical inputs produce byte-identical JSON.

`health-69-consumer-sync-shadow-evidence.yml` publishes that plan with a
`workflows.consumer-sync-shadow-handoff/v1` envelope for the existing local
Orchestrator capability `capability:reference-sync-hygiene-test-gate`. The
handoff is explicitly `shadow`, `write_authority=false`, and
`promotion_allowed=false`; classification, counterexamples, expiry, rollback,
and promotion blockers remain owned by Orchestrator's
`consumer_sync_shadow.py` dashboard.

#### Canary-Gated Fan-out

Maint 68 separates a sync plan into `preview`, `canary`, and `promote` phases.
An ordinary scheduled, release, or manual no-filter run defaults to `canary`:
it can open sync PRs only for the 2-3 representative repositories declared in
`config/consumer_sync_canaries.json`. The selection artifact records the exact
compiled `plan_id`, desired hash, and prospective affected paths for every
registered repository before any consumer write.

Do not wait for consumer CI in that workflow. Run Maint 71 later to publish
`sync-canary-evidence.json`, then invoke Maint 68 with `phase=promote` and that
artifact's JSON as `canary_evidence_json`. Promotion rejects absent, stale or
mixed-plan evidence, failed required checks, and active non-outdated review
threads. A successful promotion targets all registered non-canary repositories
once every configured canary has current, green, review-clear evidence for the
same plan.
Use `preview` to produce the plan/evidence artifact without a write matrix.
Emergency direct promotion remains an explicit audited operator action and is
limited to a security or production-break fix.

To validate the manifest locally:

```bash
python scripts/sync_manifest_compiler.py \
  --manifest .github/sync-manifest.yml \
  --output-json /tmp/consumer-sync-plan.json
```

This is also run automatically as the first step of both `maint-68-sync-consumer-repos.yml`
(before any PR creation) and `health-70-validate-sync-manifest.yml` (on every PR
that touches the manifest).

Custom Gate repos are a special-case skip: their `pr-00-gate.yml` stays local.

The `Template` repository is the canonical source for new consumer repos, so it
must not preserve stale copies of files that are `create_only` for real
consumers. Manifest entries can set `overwrite_repos: [stranske/Template]` to
keep those files aligned in Template while still preserving customizations in
production consumers.

### Reusable Workflow Versioning

First-party consumer repos currently call reusable workflows via `@main`.
That is the active standard reflected in the consumer templates and integration
guide. For repos that need extra stability, pin to a specific commit SHA instead
of following the first-party default.

If a reusable workflow fix must ship immediately, trigger:
- `Maint 68 Sync Consumer Repos` only if template files changed

### Sync PR Branch Cleanup

`maint-71-merge-sync-prs.yml` owns routine cleanup for `sync/workflows-*`
branches. In addition to closing stale duplicate sync PRs and merging the active
passing sync PR, it deletes same-repo sync branches that are connected to closed
or merged sync PRs and no longer have an open PR. Use the `cleanup_branches`
manual input to disable that cleanup only for diagnostics.

### Autofix Tool Version Ownership

Workflows owns shared autofix/dev-tool pins in
`.github/workflows/autofix-versions.env`. Treat that file as the source of truth
for `ruff`, `black`, `mypy`, `pytest`, `coverage`, `isort`, and `docformatter`.
The matching `pyproject.toml`, consumer template, integration template, and
direct `requirements.lock` pins must move in the same Workflows PR. Maint 52
also updates direct tool pins in a consumer's `requirements-dev.lock` when that
additional generated lockfile exists.

Consumer repos receive those pins through `maint-52-sync-dev-versions.yml`, not
the general `maint-68-sync-consumer-repos.yml` template sync. Keep
`.github/workflows/autofix-versions.env` out of `.github/sync-manifest.yml` so a
workflow-template sync PR cannot update the env file without the matching
`pyproject.toml`, `requirements.lock`, and supported `requirements-dev.lock`
changes.

Dependabot should not be merged when it only bumps one of those shared tool pins
in `pyproject.toml`; route that change through the Workflows source pin update
path instead. Runtime dependency bumps remain normal Dependabot work.

Consumer alignment must not wait for unrelated PyPI freshness. The
`maint-52-sync-dev-versions.yml` workflow reports whether newer PyPI versions
exist, but continues syncing the canonical pins from Workflows. The
`maint-auto-update-pypi-versions.yml` workflow owns opening source bump PRs for
freshness updates.

### Monorepo Package Dependencies (`app-baseline-kit`)

Shared packages that live in this repo under `packages/` (currently
`app-baseline-kit`, which ships the `baseline_kit` import) are consumed by
other repos via an **unpinned** git URL in `pyproject.toml`:

```toml
"app-baseline-kit @ git+https://github.com/stranske/Workflows.git#subdirectory=packages/app-baseline-kit"
```

That URL resolves to **Workflows `main` HEAD** at install time, which is the
intended `@main` consumer default. The hazard is the compiled lockfile: by
default `uv pip compile` freezes that dependency to whatever commit `main`
pointed at when the lock was generated, e.g.

```
app-baseline-kit @ git+https://github.com/stranske/Workflows.git@<sha>#subdirectory=packages/app-baseline-kit
```

CI installs the lock **and** the editable project together
(`uv pip install -r requirements.lock -e .[app,dev]`), so the same package is
declared twice — pinned (lock) and unpinned (project). They agree only while
`main` stays at `<sha>`. The next Workflows `main` advance makes the unpinned
URL resolve to a different commit, and uv aborts the install:

```
Requirements contain conflicting URLs for package `app-baseline-kit`
```

This silently breaks every downstream consumer's CI on an unrelated Workflows
merge (it broke trip-planner CI after the `py.typed` PR #2204). Refreshing the
lock fixes it only until the next advance, so it is not a stable answer.

**Convention: exclude monorepo `@main` packages from the lock.** In each
consuming repo's `pyproject.toml`, add:

```toml
[tool.uv.pip]
no-emit-package = ["app-baseline-kit"]
```

Then regenerate the lock with the repo's documented `uv pip compile` command.
The dependency drops out of `requirements.lock` (every other, versioned package
stays pinned), the editable project install resolves it from `@main`, and there
is no frozen SHA to keep refreshed — the conflict class is gone permanently. uv
reads `[tool.uv.pip]` from `pyproject.toml`, so the lock regen, the
`dependency-refresh.yml` automation, and the lockfile-freshness check all honor
it consistently with no extra wiring.

If the repo has a dependency-alignment test (`tests/test_dependency_version_alignment.py`,
which asserts every `pyproject.toml` dependency is pinned in `requirements.lock`),
make it read the same `no-emit-package` list and subtract those names from the
expected set — otherwise it fails on the now-absent package. Drive it from the
config, not a hardcoded name, so the two never drift:

```python
no_emit = {
    n.split(" @ ")[0].split("[")[0].strip().lower()
    for n in pyproject.get("tool", {}).get("uv", {}).get("pip", {}).get("no-emit-package", [])
}
declared -= no_emit
```

Applied to `trip-planner` and `Counter_Risk`; apply the same `pyproject.toml`,
lock-regen, and alignment-test changes whenever a new repo adopts
`app-baseline-kit` (or any future `packages/` member referenced by an unpinned
`@main` URL). These are per-repo `pyproject.toml`/`requirements.lock`/test
changes, not synced template files.

### Manual Sync Trigger

```bash
gh workflow run "Maint 68 Sync Consumer Repos" \
  --repo stranske/Workflows \
  -f repos="stranske/Travel-Plan-Permission" \
  -f dry_run=true
```

### Drift Detection

Workflows runs **Health 68 Consumer Sync Drift Check** to detect divergence between
templates/manifest entries and the registered consumer repos. It runs daily and
after template/manifest/script changes.

- Files marked with `sync_mode: create_only` are excluded, except for repos
  listed in the entry's `overwrite_repos` override.
- The uploaded `consumer-sync-drift-report` artifact uses
  `workflows-consumer-sync-drift/v1` and includes safe
  `token_diagnostics` (`workflows-drift-token-selection/v1`) so permission or
  rate-limit failures are distinguishable from real file drift.
- **Workflows-Integration-Tests** is **not** a consumer repo and is validated by
  [Health 67 Integration Sync Check](../../.github/workflows/health-67-integration-sync-check.yml).

---

## Verification Checklist

After fixing a template bug:

- [ ] Fix applied to `templates/consumer-repo/`
- [ ] Fix applied to reusable workflow (if applicable)
- [ ] Sync workflow triggered or PR created for registered repos
- [ ] Unregistered repos identified and PRs created
- [ ] Bot review comments addressed in PRs
- [ ] CI passing in all affected repos

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-27 | Initial document based on trip-planner/Manager-Database setup learnings |

## Generated delivery ownership

For dependency and consumer-sync delivery, the campaign issue is durable and
each generated PR is a leased attempt. Maint 71 alone decides merge or close
disposition for `sync/workflows-*` and `deps/sync-dev-versions-*`; operators
and local watchers must consume its recorded owner/next-command handoff rather
than reimplementing that policy. See
[`SYNC_DEPENDENCY_CAMPAIGN.md`](SYNC_DEPENDENCY_CAMPAIGN.md).
