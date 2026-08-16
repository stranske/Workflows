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
sync PR covers drift only when it matches the current compiled plan and is within the
36-hour coverage lease. Configured canaries use the stable `sync/workflows-candidate`
branch; promoted non-canaries use the stable `sync/workflows-delivery` branch. Fully covered drift
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
- A custom Gate must include an independent `generated-delivery-seal` job that
  invokes
  the commit-pinned
  `stranske/Workflows/.github/actions/generated-delivery-seal` action, and its
  aggregate `Gate / gate` must require that job. Invoking the exact-synced
  `.github/actions/path-classifier` is not sufficient because a sync PR can
  modify that local action. The Workflows-owned action evaluates the event's
  exact head and delivery marker outside the mutable consumer checkout and
  fails closed until Maint 71 seals that head.
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

### Sparse checkout state leaking into a later checkout

**Pattern**: A job checks out one local action with `sparse-checkout`, then runs a
second `actions/checkout` into the same workspace and expects the complete
repository to be present.

**Problem**: The later checkout can retain the first checkout's sparse worktree
configuration. A subsequent local action then fails before useful work begins
with `Can't find 'action.yml'`, even though the action is present on the
repository's default branch.

**Fix**: Put the preliminary sparse checkout in a dedicated `path:` and invoke
the local action from that path. Reserve the workspace root for the later full
checkout. The auto-label workflows use `eligibility-source/` for this reason.

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
| `requires` | list of manifest targets, optional | Transitive co-delivery dependencies for source-delta plans; targets must exist and cycles are rejected |

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
`promotion_allowed=false`. The uploaded Workflows runtime report is limited to
local evidence-ingestion state (including an explicit rejected-ingestion state);
it is not the consumer-sync policy classifier. Authoritative classification,
counterexamples, expiry, rollback, and promotion blockers remain owned by
Orchestrator's `consumer_sync_shadow.py` dashboard.

The same workflow also records typed completion evidence through
`scripts/orchestrator_runtime/completion_event_adapter.py`. The uploaded bundle
includes `completion-evidence.json` (`workflows.runner-completion-evidence/v1`)
plus mutable runtime state files `capabilities-state.json` and
`evidence-ledger.json`. Accepted evidence attaches only to capabilities present
in `config/orchestrator_runtime/capabilities.json`; duplicate replays return
`status=duplicate` without mutating ledger or capability state.

#### Canary-Gated Fan-out

Maint 68 separates a sync plan into `preview`, `canary`, and `promote` phases.
An ordinary scheduled or manual no-filter run defaults to `canary` (release
publication deliberately does not start a second sync cycle):
it can open sync PRs only for the three representative repositories declared in
`config/consumer_sync_canaries.json`. Those canaries span runtime/build shapes
and the fleet's automated-review profiles; at least one must exercise the Codex
review profile before promotion. The selection artifact records the exact
compiled `plan_id`, desired hash, and prospective affected paths for every
registered repository before any consumer write.

Maint 68 supports two immutable plan scopes. `full` compiles every manifest
entry and is the scheduled drift-reconciliation default. `source-delta`
compiles the same typed manifest, then selects only entries whose resolved
source changed in an exact Workflows commit range. This lets a dependency-only
source repair reach consumers without absorbing unrelated, unpromoted workflow
drift. Directory entries match changed descendants. Dependencies are declared
by a selected entry's typed `requires` field and expanded transitively. The
path-classifier action therefore carries its lease-contract bootstrap dependency, so a
consumer whose base predates that contract can still evaluate its initial
staged delivery safely. Manifest changes fail closed and require `full`;
historical removal declarations are never replayed by a source delta. The
uploaded `sync-plan-scope.json` records both plan IDs, the exact base/head,
changed paths, selected targets, dependency targets, and ignored paths.
If no manifest-managed source matches the range, Maint 68 records the empty
scope and skips the consumer fan-out entirely.

Start a bounded source-delta candidate with the source repair's exact first
parent and merged head:

```bash
gh workflow run maint-68-sync-consumer-repos.yml \
  --repo stranske/Workflows \
  --ref main \
  -f phase=canary \
  -f delivery_scope=source-delta \
  -f scope_base_sha=<repair-first-parent> \
  -f scope_head_sha=<repair-merge-commit>
```

Maint 71 writes that same scope, source commit, and immutable range into every
canary evidence row. Every `phase=promote` run recovers the exact source commit
from the evidence; a source-delta promotion also recovers its exact base. The
workflow checks out that historical source head and recompiles the same plan.
A later commit on `main` therefore cannot silently join an authorized delivery,
including a full-plan promotion. Do not substitute a moving branch name for
either source-delta SHA.
Before any checked-out source script runs, Maint 68 requires the resolved source
commit to be an ancestor of the workflow dispatch ref and the scope base to be
an ancestor of that source. New source-delta delivery commits also bind the full
plan ID, scope, range, and source commit into their immutable GitHub-signed
commit message; Maint 71 rejects canary evidence when PR-body metadata does not
match that commit and the validated delivery record.

An explicit `repos` input may narrow a canary run to a subset of those configured
canaries, but it cannot expand a canary run into non-canary repositories. The
selector fails closed with `canary_selection_contains_non_canary` if an operator
tries. Canary corrections refresh the stable `sync/workflows-candidate` branch
and its existing PR instead of opening another hash-named PR for every candidate
plan. Promotion likewise refreshes one stable `sync/workflows-delivery` PR per
non-canary; immutable plan and desired-tree identity live in the delivery
record instead of the branch name.

Do not wait for consumer CI in that workflow. Run Maint 71 later with
`active_sync_hash=candidate` to publish `sync-canary-evidence.json`, then invoke
Maint 68 with `phase=promote` and that artifact's JSON as
`canary_evidence_json`. Promotion rejects absent, stale or
mixed-plan evidence, failed required checks, and active non-outdated review
threads. A successful promotion targets all registered non-canary repositories
once every configured canary has current, green, review-clear evidence for the
same plan.

The normal chain is automatic: Maint 68 dispatches the candidate selector after
writing canary PRs; Maint 71 dispatches `phase=promote` only after the persisted
evidence is complete and every candidate exact head is prepared or safely
recovered. Candidate PRs stay open. A successful promotion dispatches the
`campaign` selector, which prepares the stable candidate and delivery PRs for
the same plan across the entire registered non-admin fleet. Maint 71 emits a
commit authorization only when every repository is exact-head ready or proven
unchanged, then rechecks the authorized heads and merges the batch. Generated-branch Gate
completions provide event-driven wakeups through the synced Gate-followups hub.
Maint 68 binds that handoff to the exact plan ID, plan scope, source range, and
source commit. A canary that already matches the plan contributes explicit
`no-change-canary` evidence containing its observed default-branch SHA; Maint 71
accepts it only while that SHA is still the live default-branch head and its
active-ruleset required checks are green. Recovery
from a previously merged candidate is likewise restricted to the dispatching
plan and source commit. Thus a no-diff run cannot silently recycle an older
merged candidate and promote stale content. If no open candidate, current
no-change evidence, or same-plan merged candidate exists, the evidence pass
fails closed. The remediation is to rerun Maint 68 for the intended immutable
full plan or source range, never to reuse an older evidence artifact. These
rules are enforced by `sync_run_contract.js`, `maint71_merge_sync_prs.js`, and
`sync_pr_merge_contract.js`, with the workflow carrying the immutable fields
between those boundaries.
Maint 82 retains every transient Maint 71 handoff with an immutable plan binding,
idempotency key, and due time and supplies a ten-minute fallback for
candidate/campaign evidence holds, delivery-review startup,
pending checks, changed heads, review windows, reviewer settlement, sealed Gate
checks, and stable candidate base refreshes, so an absent event cannot strand
the lifecycle. It does not retry actionable CI failures, unresolved review
findings, or a dry-run-only sealed-head mismatch as if they were timer states.
Promoted delivery commits carry their exact canary evidence in the verified
commit message so Maint 71 can replay the same promotion if a consumer base
advances during review; editable PR body fields never authorize that replay.

Maint 71 persists and validates the `sync-canary-evidence-premerge` artifact
before promotion is allowed to run. A GitHub pre-job approval hold, a cancelled
evidence step, or an artifact-upload failure therefore leaves the
candidate PRs open and recoverable. If an older operator merged the stable
candidate PRs before evidence was durable, Maint 71 may reconstruct evidence
only from the latest trusted, actually merged `sync/workflows-candidate` PR in
each configured canary, rechecking that exact head's required checks and live
review threads. Maint 68 still rejects a stale or mixed recovered plan.
Candidate mode derives its repository scope from
`config/consumer_sync_canaries.json`; non-canary delivery branches are excluded
and cannot create false `target_missing` failures.
Maint 71 reads required contexts from legacy branch protection when available,
then from active repository and inherited organization rulesets. It fails
closed if neither protection surface is visible. A successful ruleset query
that returns no required checks is authoritative, so cancelled informational
jobs do not become invented required failures.

Maint 68 creates stable deliveries as draft with `sync:delivery-staging` and
disables auto-merge before every real head update. If a later run computes the
same base and desired tree, it preserves the PR's current review/seal state;
metadata-only refreshes therefore cannot restart review forever.

Every real head update is fail-closed on commit identity. Maint 68 mints a
repository-scoped Workflows GitHub App installation token, uploads the staged
blobs/tree through GitHub's Git database API, and creates the commit without
custom author, committer, or signature fields. GitHub therefore signs the App
commit. Maint 68 compares the returned tree to `git write-tree`, requires a
`verified=true` / `reason=valid` signature, and only then atomically publishes
the stable branch with `--force-with-lease`. An existing exact-tree delivery
with an unsigned head is replaced rather than treated as a no-op. Maint 71
independently requires a valid cryptographic signature on the exact workflow-
sync PR head before merge. This accepts GitHub App, GPG, SSH, and S/MIME
signatures that GitHub validates while still rejecting unsigned generated
heads. The sibling dev-tool sync lane is excluded until its producer gains the
same signed-commit contract. This prevents synced workflow files from reaching
consumer `main` through an unsigned automation commit and avoids GitHub's
subsequent workflow trust approval hold.

Maint 71 marks the draft ready and starts bounded reviewer settlement. The
policy in `config/consumer_sync_review_policy.json` requires one response, not
all configured reviewers, after a seven-minute quiet period. If every reviewer
reports capacity unavailability, settlement degrades after the quiet period;
if nobody responds, it degrades after fifteen minutes. Active non-outdated
review threads are never waived by either fallback. Reviewer statuses and
comments that explicitly say a review was skipped, excluded, review-disabled,
or not performed are unavailable signals and cannot satisfy the one-response
quorum. A completed negative verdict with substantive review output still
counts as a response; settlement is evidence of reviewer participation, not
approval.
Maint 71 then seals the
exact head and applies `sync:delivery-ready`, which triggers a fresh Gate. The
Gate summary rejects an unsealed stable delivery, while the shared merge guard
rejects `sync:delivery-staging` for every merger except Maint 71's verified
sealed path. The staging hold remains until the merge succeeds.

For workflow syncs, a sealed candidate is not merged immediately: it remains
the stable delivery PR while promotion prepares the non-canaries. Only the
campaign-wide exact-head authorization releases the candidate and delivery PRs
for Maint 71's final per-PR merge gate. This preserves one update-in-place
review surface without letting ordinary PR minimization merge it before fleet
delivery is complete.

The standard Gate's generated-delivery job invokes the Workflows-owned
`generated-delivery-seal` action directly. It does not execute seal policy from
the consumer pull request checkout, so a candidate that changes the local path
classifier or lease-contract copy cannot redefine its own acceptance rule. The
local classifier retains its trusted-base and add-only bootstrap checks as
defense in depth, but it is not the authoritative seal boundary. Maint 71
remains the final boundary and independently requires the exact generated head
to carry a valid GitHub-recognized signature before merge.

Generated `sync/workflows-*` PRs are excluded from both the basic and agent
autofix lanes. Their intentional pre-seal Gate failure is a delivery hold, not
a request for a consumer-branch repair commit; Maint 71 advances the record and
shared defects return to Workflows source before the stable PR is refreshed.
Maint 68 also writes `autofix: false` into every generated PR body. The shared
reusable autofix workflow independently rejects `sync/workflows-*` heads, so an
older consumer caller cannot mutate the transition PR while the updated local
caller is still waiting to land. The body directive protects the agent lane;
the synced caller branch exclusion becomes the durable local guard after the
generated PR lands.

Maint 71 also enforces the seven-minute exact-head post-push window and performs a final
head plus active-review-thread query immediately before each generated merge.
Maint 68 records the exact head and its post-publication observation time in the
delivery record. That SHA-bound observation anchors the window; PR body edits,
labels, comments, and review-thread resolution do not restart it, while a
mismatched or missing observation fails back to the conservative PR timestamp.
Workflow-call, manual, and repository-dispatch candidate selectors normalize to
the same gate. The executor requires same-job campaign authorization bound to
every PR number, delivery generation, branch, and head SHA, so scheduled or
malformed paths cannot merge a candidate implicitly.

Campaign hold states have explicit recovery paths. For
`campaign_authorization_required`, rerun the prepare pass for the same immutable
plan and source commit, then authorize the exact prepared heads. A
`campaign_prepared` row is intentionally waiting for that authorization and
must not be merged by an unscoped pass. A `campaign_no_change_verified` row is
already terminal evidence and needs no PR mutation. For `target_missing` with
reason `campaign_pr_and_no_change_evidence_missing`, regenerate the stable
delivery for the same plan; if a partial commit pass already merged it, resume
the prepare pass so Maint 71 rebuilds authorization from trusted closed merged
history. `stranske/Collab-Admin` is excluded from campaign authorization because
it is the generated fleet dashboard/control repository, not a reviewed consumer
delivery target.

Active non-outdated review threads remain merge blockers. When a shared source
repair proves a finding obsolete on the current generated head, an authenticated
operator may pass `review_resolution_json` to Maint 71. Each
`workflows-sync-review-resolution/v1` proof names one thread, PR, exact head,
Workflows source-fix SHA, evidence URL, and reason. Maint 71 verifies that the
fix is contained in the delivery's recorded source commit and re-reads the
thread before resolving it. A source fix without this exact proof, a later
candidate plan, or a passing Gate never resolves the current PR's review debt.

A non-empty workflow-sync selector applies only to the `sync/workflows-*` lane.
An open sibling `deps/sync-dev-versions-*` delivery is therefore ignored for
the selector's expected-branch check instead of producing a false
`target_missing` system failure; an unscoped Maint 71 pass reconciles the
dev-tool lane independently.

Use `preview` to produce the plan/evidence artifact without a write matrix.
There is no direct-repository promotion bypass. Security and production-break
fixes may use an expedited canary run, but still require exact-plan evidence
before `phase=promote` can write to non-canaries.

To validate the manifest locally:

```bash
python scripts/sync_manifest_compiler.py \
  --manifest .github/sync-manifest.yml \
  --output-json /tmp/consumer-sync-plan.json
```

This is also run automatically as the first step of both `maint-68-sync-consumer-repos.yml`
(before any PR creation) and `health-70-validate-sync-manifest.yml` (on every PR
that touches the manifest).

Custom Gate repos are a special-case skip: their `pr-00-gate.yml` stays local,
but their Gate must retain the exact-synced path classifier or an equivalent
exact-head delivery-seal check.

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
also updates managed `.pre-commit-config.yaml` hook revisions and direct tool pins in a consumer's `requirements-dev.lock` when that
additional generated lockfile exists.

Consumer repos receive those pins through `maint-52-sync-dev-versions.yml`, not
the general `maint-68-sync-consumer-repos.yml` template sync. Keep
`.github/workflows/autofix-versions.env` out of `.github/sync-manifest.yml` so a
workflow-template sync PR cannot update the env file without the matching
`pyproject.toml`, managed `.pre-commit-config.yaml` hook revisions, `requirements.lock`, and supported `requirements-dev.lock`
changes.

Managed pre-commit revisions are an explicit Maint 52 propagation surface. The
workflow passes `sync_dev_dependencies.py --pre-commit`; the script's default
check intentionally omits that surface so a Maint 68 workflow-template candidate
does not fail while the separate canonical dependency wave is still pending.

Dependabot should not be merged when it only bumps one of those shared tool pins
in `pyproject.toml`; route that change through the Workflows source pin update
path instead. Runtime dependency bumps remain normal Dependabot work.

Consumer alignment must not wait for unrelated PyPI freshness. The
`maint-52-sync-dev-versions.yml` workflow reports whether newer PyPI versions
exist, but continues syncing the canonical pins from Workflows. The
`maint-auto-update-pypi-versions.yml` workflow is the sole source-proposal lane:
it batches routine updates into one Monday UTC PR and accepts a reviewed manual
security override when needed. Maint 50 reports freshness but never creates a
competing issue or proposal. Each consumer wave records the settled Workflows
source commit so propagation can be traced back to the validated source change.

### Renovate vs Maint 68 Path Ownership

Maint 68 overwrites every manifest-managed path in a consumer on each sync. If
that consumer's own Renovate opens a PR touching one of those paths, the change
is discarded on the next sync — consumer Renovate PRs against
`.github/workflows/agents-guard.yml` and
`.github/workflows/maint-76-claude-code-review.yml` (Inv-Man-Intake#838,
Manager-Database#1347) were both closed unmerged for exactly this reason.

`renovate-presets/consumer-managed-paths.json` encodes the boundary. It is
**generated** from `.github/sync-manifest.yml` and the registered consumer list,
and `renovate-presets/fleet.json` extends it, so every consumer inherits it
without a re-sync. Ownership follows the same rules Maint 68 applies:

| Manifest state | Owner | Renovate |
| --- | --- | --- |
| No `sync_mode` (overwrite-managed) | Workflows | disabled in consumers |
| `sync_mode: create_only` | consumer, after first seed | enabled |
| `sync_mode: create_only` + repo in `overwrite_repos` | Workflows | disabled in that repo |
| Repo listed in `skip_repos` | consumer | enabled in that repo |

The preset matches consumer repositories only. `stranske/Workflows` is the sync
source, so its canonical files stay fully Renovate-managed and dependency bumps
still land here first, then reach consumers through Maint 68.

Note that `.github/workflows/autofix.yml` has no `sync_mode`, which makes it
overwrite-managed and therefore disabled for consumer Renovate. `ci.yml` and
`pr-00-gate.yml` are `create_only` and stay consumer-owned.

Regenerate after any manifest change:

```bash
python scripts/generate_consumer_renovate_ownership.py          # rewrite the preset
python scripts/generate_consumer_renovate_ownership.py --check  # fail on drift
```

`scripts/dev_check.sh` runs `--check` (and regenerates under `--fix`), and
`tests/scripts/test_generate_consumer_renovate_ownership.py` fails when a new
overwrite-managed path becomes visible to consumer Renovate.

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
  -f phase=preview \
  -f repos="stranske/Travel-Plan-Permission" \
  -f dry_run=true
```

Omit `repos` for the normal configured canary run. A write run targeting any
non-canary must use `phase=promote` with Maint 71's exact-plan
`canary_evidence_json`; `phase=canary -f repos=<fleet>` is rejected. Reconcile
promoted PRs with Maint 71 using `active_sync_hash=delivery`.

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
